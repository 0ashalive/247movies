import cloudscraper
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime, timedelta
import concurrent.futures
from urllib.parse import urlparse

# --- Configuration ---
BASE_URL = "https://fibwatch.art"
TOTAL_PAGES = 150
JSON_FILE = "data.json"
M3U_FILE = "latest.m3u"
GROUP_NAME = "Fibwatch Latest"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

def get_resolution(text):
    """Extracts resolution from the link to prioritize higher quality."""
    match = re.search(r'(\d{3,4})p', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if '4k' in text.lower():
        return 2160
    return 0

def load_existing_data():
    """Loads existing JSON data to prevent overwriting/deleting old records."""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"⚠️ Error loading {JSON_FILE}: {e}")
            return {}
    return {}

def save_data(data):
    """Saves updated dictionary to data.json and regenerates latest.m3u."""
    # 1. Save to data.json
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 2. Re-generate latest.m3u from all cumulative data
    bd_time = datetime.utcnow() + timedelta(hours=6)
    now = bd_time.strftime("%Y-%m-%d %I:%M:%S %p (BD Time)")
    
    with open(M3U_FILE, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        f.write('# Playlist Generated Automatically by Incremental Automation\n')
        f.write(f'# Total Items: {len(data)}\n')
        f.write(f'# Last Updated: {now}\n\n')
        
        for key, item in data.items():
            f.write(item['m3u_entry'])
            
    print(f"💾 Updated {JSON_FILE} & {M3U_FILE} | Total Movies Saved: {len(data)}")

def process_movie(watch_link, scraper):
    """Extracts raw video link, title, and poster for a single movie."""
    try:
        res = scraper.get(watch_link, timeout=15)
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
        
        return {
            "title": file_name,
            "poster": poster,
            "stream_url": final_video_link,
            "m3u_entry": m3u_entry,
            "watch_link": watch_link
        }
        
    except Exception:
        return None

def scan_page(page_num, scraper):
    """Scans a specific page to find movie watch links."""
    url = f"{BASE_URL}/videos/latest?page_id={page_num}"
    found_movies = []
    try:
        response = scraper.get(url, timeout=15)
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

def main():
    print("🚀 Starting 1-150 Page Incremental Auto-Accumulating Scraper...")
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    
    # Load existing cumulative database
    database = load_existing_data()
    print(f"📁 Existing records in database: {len(database)}")

    # Iterate page by page (1 to 150)
    for page in range(1, TOTAL_PAGES + 1):
        print(f"\n🔎 Processing Page {page}/{TOTAL_PAGES}...")
        
        movies_on_page = scan_page(page, scraper)
        if not movies_on_page:
            print(f"⚠️ Page {page} yielded no links or failed. Moving to next page...")
            continue
            
        best_links = {}
        for base_name, full_link in movies_on_page:
            current_res = get_resolution(full_link)
            if base_name in best_links:
                if current_res > get_resolution(best_links[base_name]):
                    best_links[base_name] = full_link
            else:
                best_links[base_name] = full_link

        new_added = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_movie, w_link, scraper): b_name for b_name, w_link in best_links.items()}
            for future in concurrent.futures.as_completed(futures):
                movie_info = future.result()
                if movie_info:
                    movie_id = movie_info['title']
                    
                    # Store without deleting existing items
                    if movie_id not in database:
                        database[movie_id] = movie_info
                        new_added += 1
                        print(f"   ➕ Added: {movie_info['title']}")

        # Save after completing each page
        if new_added > 0:
            save_data(database)
            print(f"✅ Page {page} complete! {new_added} new items added.")
        else:
            print(f"ℹ️ Page {page} complete! No new items found.")

    print("\n🎉 Scraping Completed! All 1-150 pages processed without losing any data.")

if __name__ == "__main__":
    main()
    
