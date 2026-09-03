from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import cloudscraper
from bs4 import BeautifulSoup
import re
import json

BASE_URL = "https://fibwatch.art"
GROUP_NAME = "Fibwatch Latest"
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
        final_video_link = f"{actual_link}|Referer={BASE_URL}/"
        
        return {
            "title": file_name,
            "poster": poster,
            "url": final_video_link,
            "m3u_entry": f'#EXTINF:-1 tvg-logo="{poster}" group-title="{GROUP_NAME}", {file_name}\n{final_video_link}\n'
        }
    except Exception:
        return None

def scan_single_page(page_num, scraper):
    url = f"{BASE_URL}/videos/latest?page_id={page_num}"
    movies = []
    try:
        response = scraper.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        watch_links = [link['href'] for link in soup.find_all('a', href=True) if '/watch/' in link['href'] and link['href'].endswith('.html')]
        
        seen_base_names = {}
        for link in set(watch_links):
            full_link = link if link.startswith('http') else f"{BASE_URL}{link}"
            filename = full_link.split('/')[-1]
            base_name = re.sub(r'[-_]?\d{3,4}p.*\.html$', '', filename, flags=re.IGNORECASE)
            
            res = get_resolution(full_link)
            if base_name not in seen_base_names or res > seen_base_names[base_name][1]:
                seen_base_names[base_name] = (full_link, res)

        for base_name, (w_link, _) in seen_base_names.items():
            movie_data = process_movie(w_link, scraper)
            if movie_data:
                movies.append(movie_data)
        return movies
    except Exception:
        return []

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        # Default Page 1, Max Page 150
        page = int(query_params.get('page', [1])[0])
        if page < 1: page = 1
        if page > 150: page = 150

        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        
        # Scan requested page
        page_data = scan_single_page(page, scraper)
        
        next_page = page + 1 if page < 150 else None

        response_payload = {
            "status": "success",
            "current_page": page,
            "next_page": next_page,
            "total_movies_found": len(page_data),
            "data": page_data
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response_payload, indent=2).encode('utf-8'))
