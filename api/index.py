from http.server import BaseHTTPRequestHandler
import cloudscraper
from bs4 import BeautifulSoup
import re
import json
from upstash_redis import Redis

# Vercel Free Storage/Database Connection
redis = Redis.from_env()

BASE_URL = "https://fibwatch.art"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

def get_resolution(text):
    match = re.search(r'(\d{3,4})p', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if '4k' in text.lower():
        return 2160
    return 0

def process_movie(watch_link, scraper):
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
        movie_id = re.sub(r'[^a-zA-Z0-9]', '_', file_name).lower()

        # আপনার দেওয়া জেসন অবজেক্ট ফরম্যাট
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
        # ১. আগে কত নম্বর পেজ সেভ হয়েছিল তা বের করা (১ থেকে ১৫০)
        current_page = redis.get("current_processing_page")
        current_page = int(current_page) if current_page else 1

        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        url = f"{BASE_URL}/videos/latest?page_id={current_page}"
        
        added_count = 0
        try:
            response = scraper.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            watch_links = [link['href'] for link in soup.find_all('a', href=True) if '/watch/' in link['href'] and link['endswith']('.html') if hasattr(link, 'endswith') or link['href'].endswith('.html')]
            
            # ২. পূর্বে সেভ হওয়া ডাটা লোড করা (যাতে ডিলিট না হয়)
            all_movies_raw = redis.get("data_json_db")
            all_movies = json.loads(all_movies_raw) if all_movies_raw else {}

            best_links = {}
            for link in set(watch_links):
                full_link = link if link.startswith('http') else f"{BASE_URL}{link}"
                filename = full_link.split('/')[-1]
                base_name = re.sub(r'[-_]?\d{3,4}p.*\.html$', '', filename, flags=re.IGNORECASE)
                
                res = get_resolution(full_link)
                if base_name not in best_links or res > get_resolution(best_links[base_name]):
                    best_links[base_name] = full_link

            # ৩. জেসন ফরম্যাট অনুযায়ী নতুন ডাটা অ্যাড করা
            for base_name, w_link in best_links.items():
                movie = process_movie(w_link, scraper)
                if movie and movie["id"] not in all_movies:
                    all_movies[movie["id"]] = movie
                    added_count += 1
            
            # ৪. জেসন ফাইল ডাটাবেজে স্থায়ীভাবে সেভ রাখা
            redis.set("data_json_db", json.dumps(all_movies))

            # ৫. পরবর্তী পেজে শিফট করা (১৫০ পেজ পার হলে আবার ১ থেকে শুরু হবে)
            next_page = current_page + 1 if current_page < 150 else 1
            redis.set("current_processing_page", next_page)

        except Exception as e:
            pass

        # রেসপন্স আউটপুট
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        res_data = {
            "status": "success",
            "page_processed": current_page,
            "new_items_added": added_count,
            "next_page": current_page + 1 if current_page < 150 else 1,
            "message": f"Page {current_page} data saved successfully to data.json format."
        }
        self.wfile.write(json.dumps(res_data, indent=2).encode('utf-8'))
        
