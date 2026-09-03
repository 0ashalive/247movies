from flask import Flask, Response
import cloudscraper
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import concurrent.futures
from urllib.parse import urlparse

app = Flask(__name__)

BASE_URL = "https://fibwatch.art"
PAGES_TO_SCAN = 2  # Keep page count low to avoid Vercel Function timeouts
GROUP_NAME = "Fibwatch Latest"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

def get_resolution(text):
    match = re.search(r'(\d{3,4})p', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if '4k' in text.lower():
        return 2160
    return 0

def process_movie(base_name, watch_link, scraper):
    try:
        res = scraper.get(watch_link, timeout=8)
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
        
        return f'#EXTINF:-1 tvg-logo="{poster}" group-title="{GROUP_NAME}", {file_name}\n{final_video_link}\n'
    except Exception:
        return None

def scan_page(page_num, scraper):
    url = f"{BASE_URL}/videos/latest?page_id={page_num}"
    found_movies = []
    try:
        response = scraper.get(url, timeout=8)
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

@app.route('/', methods=['GET'])
@app.route('/api/index', methods=['GET'])
def generate_m3u():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    new_movies_links = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scan_page, p, scraper): p for p in range(1, PAGES_TO_SCAN + 1)}
        for future in concurrent.futures.as_completed(futures):
            for base_name, full_link in future.result():
                current_res = get_resolution(full_link)
                if base_name in new_movies_links:
                    if current_res > get_resolution(new_movies_links[base_name]):
                        new_movies_links[base_name] = full_link
                else:
                    new_movies_links[base_name] = full_link

    m3u_entries = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_movie, b_name, w_link, scraper) for b_name, w_link in new_movies_links.items()]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                m3u_entries.append(res)

    bd_time = datetime.utcnow() + timedelta(hours=6)
    now = bd_time.strftime("%Y-%m-%d %I:%M:%S %p (BD Time)")
    
    header = "#EXTM3U\n# Playlist Generated Automatically\n" + f"# Last Updated: {now}\n\n"
    content = header + "".join(m3u_entries)

    return Response(content, mimetype='text/plain')

if __name__ == "__main__":
    app.run()
  
