from http.server import BaseHTTPRequestHandler
import cloudscraper
from bs4 import BeautifulSoup
import re
import json
import os
from upstash_redis import Redis

BASE_URL = "https://fibwatch.art"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

def get_redis():
    try:
        url = os.environ.get("UPSTASH_REDIS_REST_URL")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            return Redis(url=url, token=token)
    except Exception:
        pass
    return None

def get_resolution(text):
    match = re.search(r'(\d{3,4})p', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if '4k' in text.lower():
        return 2160
    return 0

def process_movie(watch_link, scraper):
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
        movie_id = re.sub(r'[^a-zA-Z0-9]', '_', file_name).lower()

        return {
            "id": movie_id,
            "title": file_name,
            "poster": poster,
            "stream_url": actual_link,
            "headers": {
                "Referer": f"{BASE_URL}/"
            }
        }
    except Exception:
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            redis = get_redis()
            current_page = 1
            
            if redis:
                stored_page = redis.get("current_processing_page")
                current_page = int(stored_page) if stored_page else 1

            scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
            url = f"{BASE_URL}/videos/latest?page_id={current_page}"
            
            added_count = 0
            response = scraper.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            watch_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/watch/' in href and href.endswith('.html'):
                    watch_links.append(href)
            
            all_movies = {}
            if redis:
                all_movies_raw = redis.get("data_json_db")
                if all_movies_raw:
                    all_movies = json.loads(all_movies_raw)

            best_links = {}
            for link in set(watch_links):
                full_link = link if link.startswith('http') else f"{BASE_URL}{link}"
                filename = full_link.split('/')[-1]
                base_name = re.sub(r'[-_]?\d{3,4}p.*\.html$', '', filename, flags=re.IGNORECASE)
                
                res = get_resolution(full_link)
                if base_name not in best_links or res > get_resolution(best_links[base_name]):
                    best_links[base_name] = full_link

            for base_name, w_link in best_links.items():
                movie = process_movie(w_link, scraper)
                if movie and movie["id"] not in all_movies:
                    all_movies[movie["id"]] = movie
                    added_count += 1
            
            if redis:
                redis.set("data_json_db", json.dumps(all_movies))
                next_page = current_page + 1 if current_page < 150 else 1
                redis.set("current_processing_page", next_page)

            res_data = {
                "status": "success",
                "page_processed": current_page,
                "new_items_added": added_count,
                "next_page": current_page + 1 if current_page < 150 else 1
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(res_data, indent=2).encode('utf-8'))

        except Exception as e:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            
