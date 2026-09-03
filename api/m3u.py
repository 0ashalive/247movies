from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import cloudscraper
from bs4 import BeautifulSoup
import re

BASE_URL = "https://fibwatch.art"
GROUP_NAME = "Fibwatch Latest"
IMAGE_PROXY = "https://srhady-live-stream.hf.space/image?url="

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
        
        return f'#EXTINF:-1 tvg-logo="{poster}" group-title="{GROUP_NAME}", {file_name}\n{actual_link}|Referer={BASE_URL}/\n'
    except Exception:
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        page = int(query_params.get('page', [1])[0])

        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        
        url = f"{BASE_URL}/videos/latest?page_id={page}"
        m3u_content = "#EXTM3U\n"
        
        try:
            response = scraper.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            watch_links = [link['href'] for link in soup.find_all('a', href=True) if '/watch/' in link['href'] and link['href'].endswith('.html')]
            
            for link in set(watch_links):
                full_link = link if link.startswith('http') else f"{BASE_URL}{link}"
                entry = process_movie(full_link, scraper)
                if entry:
                    m3u_content += entry
        except Exception:
            pass

        self.send_response(200)
        self.send_header('Content-Type', 'audio/x-mpegurl')
        self.send_header('Content-Disposition', 'inline; filename="latest.m3u"')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(m3u_content.encode('utf-8'))
      
