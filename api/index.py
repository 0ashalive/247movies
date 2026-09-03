from flask import Flask, Response, jsonify, request
import cloudscraper
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import concurrent.futures
from urllib.parse import urlparse
import vercel_blob

app = Flask(__name__)

BASE_URL = "https://fibwatch.art"
FILE_NAME = "latest_movies.m3u"
GROUP_NAME = "Fibwatch Latest"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

def get_resolution(text):
    match = re.search(r'(\d{3,4})p', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if '4k' in text.lower():
        return 2160
    return 0

def get_domain(url):
    parsed_uri = urlparse(url)
    return f"{parsed_uri.scheme}://{parsed_uri.netloc}"

def process_movie(base_name, watch_link, scraper):
    try:
        res = scraper.get(watch_link, timeout=10)
        watch_soup = BeautifulSoup(res.text, 'html.parser')
        
        actual_link = None
        for a in watch_soup.find_all('a', href=True):
            href = a['href']
            if 'urlshortlink.top' in href and 'url=' in href:
                match = re.search(r'url=(.*)', href)
                if match:
                    decoded = match.group(1).replace('%3A', ':').replace('%2F', '/')
                    if '.mkv' in decoded or '.mp4' in decoded:
                        actual_link = decoded
                        break
            elif ('.mkv' in href or '.mp4' in href) and 'urlshortlink.top' not in href:
                actual_link = href
                if actual_link.startswith('/'):
                    actual_link = f"{BASE_URL}{actual_link}"
                break
        
        if not actual_link:
            return None
            
        poster_tag = watch_soup.find('meta', property='og:image')
        poster = poster_tag['content'] if poster_tag else ""
        if poster:
            poster = f"{IMAGE_PROXY}{poster}"
        
        file_name = actual_link.split('/')[-1]
        file_name = re.sub(r'\[Fibwatch\.Com\]|\.mkv|\.mp4', '', file_name, flags=re.IGNORECASE).replace('.', ' ').strip()
        final_video_link = f"{actual_link}|Referer={BASE_URL}/"
        
        m3u_entry = f'#EXTINF:-1 tvg-logo="{poster}" group-title="{GROUP_NAME}", {file_name}\n{final_video_link}\n'
        return m3u_entry, get_domain(actual_link)
    except Exception:
        return None

def get_total_pages(scraper):
    """Detects total available page count from the site pagination."""
    try:
        res = scraper.get(f"{BASE_URL}/videos/latest?page_id=1", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        pages = []
        for a in soup.find_all('a', href=True):
            match = re.search(r'page_id=(\d+)', a['href'])
            if match:
                pages.append(int(match.group(1)))
        return max(pages) if pages else 5
    except Exception:
        return 5

def scan_page(page_num, scraper):
    url = f"{BASE_URL}/videos/latest?page_id={page_num}"
    found_movies = []
    try:
        response = scraper.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        watch_links = [link['href'] for link in soup.find_all('a', href=True) if '/watch/' in link['href'] and link['href'].endswith('.html')]
        
        for link in set(watch_links):
            full_link = link if link.startswith('http') else f"{BASE_URL}{link}"
            filename = full_link.split('/')[-1]
            base_name = re.sub(r'[-_]?\d{3,4}p.*\.html$', '', filename, flags=re.IGNORECASE)
            found_movies.append((base_name, full_link))
        return found_movies
    except Exception:
        return []

def load_existing_blob_data():
    """Retrieves existing file from Vercel Blob storage."""
    try:
        blobs = vercel_blob.list()
        target_blob = next((b for b in blobs['blobs'] if FILE_NAME in b['pathname']), None)
        if target_blob:
            scraper = cloudscraper.create_scraper()
            res = scraper.get(target_blob['url'])
            lines = res.text.splitlines(keepends=True)
            entries = [line for line in lines if not line.startswith('#EXTM3U') and not line.startswith('# Playlist') and not line.startswith('# Last')]
            
            old_domain = None
            for line in entries:
                if '.mkv' in line or '.mp4' in line:
                    old_domain = get_domain(line.split('|')[0])
                    break
            return entries, old_domain
    except Exception:
        pass
    return [], None

@app.route('/api/scrape', methods=['GET', 'POST'])
def run_scraper():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    
    # 1. Check max available pages dynamically
    max_pages = get_total_pages(scraper)
    # Target parameter allows specifying pages via ?pages=all or ?pages=10
    requested_pages = request.args.get('pages', 'all')
    pages_to_scan = max_pages if requested_pages == 'all' else min(int(requested_pages), max_pages)

    # 2. Retrieve old entries from Vercel Blob Storage
    old_entries, old_domain = load_existing_blob_data()

    # 3. Parallel scan all requested pages
    new_movies_links = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(scan_page, p, scraper): p for p in range(1, pages_to_scan + 1)}
        for future in concurrent.futures.as_completed(futures):
            for base_name, full_link in future.result():
                current_res = get_resolution(full_link)
                if base_name in new_movies_links:
                    if current_res > get_resolution(new_movies_links[base_name]):
                        new_movies_links[base_name] = full_link
                else:
                    new_movies_links[base_name] = full_link

    # 4. Extract direct watch links
    new_entries = []
    new_domain = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(process_movie, b_name, w_link, scraper) for b_name, w_link in new_movies_links.items()]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                entry, domain = result
                if not any(entry.split('\n')[0] in old_line for old_line in old_entries):
                    new_entries.append(entry)
                    if not new_domain:
                        new_domain = domain

    # 5. Handle domain replacement
    if old_domain and new_domain and old_domain != new_domain:
        old_entries_text = "".join(old_entries)
        old_entries_text = old_entries_text.replace(old_domain, new_domain)
        old_entries = [old_entries_text]

    # 6. Format and save directly back into Vercel Blob storage
    bd_time = datetime.utcnow() + timedelta(hours=6)
    now = bd_time.strftime("%Y-%m-%d %I:%M:%S %p (BD Time)")
    
    header = f"#EXTM3U\n# Playlist Generated Automatically\n# Last Updated: {now}\n\n"
    final_content = header + "".join(new_entries) + "".join(old_entries)

    # Automatically saves file into Vercel's cloud bucket under the exact same filename
    blob_res = vercel_blob.put(FILE_NAME, final_content.encode('utf-8'), add_random_suffix=False)

    return jsonify({
        "status": "success",
        "scanned_pages": pages_to_scan,
        "new_entries_added": len(new_entries),
        "playlist_url": blob_res['url']
    })

@app.route('/playlist.m3u', methods=['GET'])
@app.route('/', methods=['GET'])
def serve_playlist():
    """Serves the latest saved .m3u playlist directly."""
    entries, _ = load_existing_blob_data()
    if entries:
        return Response("".join(entries), mimetype='text/plain')
    return Response("#EXTM3U\n# No playlist cached yet. Trigger /api/scrape first.", mimetype='text/plain')

if __name__ == "__main__":
    app.run()
    return Response(content, mimetype='text/plain')

if __name__ == "__main__":
    app.run()
  
