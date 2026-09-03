from http.server import BaseHTTPRequestHandler
import json
from upstash_redis import Redis

redis = Redis.from_env()
GROUP_NAME = "Fibwatch Latest"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        all_movies_raw = redis.get("all_movies_db")
        all_movies_dict = json.loads(all_movies_raw) if all_movies_raw else {}
        
        m3u_content = "#EXTM3U\n# Playlist Generated Automatically - All Pages Data\n\n"
        
        for movie in all_movies_dict.values():
            m3u_content += f'#EXTINF:-1 tvg-logo="{movie["poster"]}" group-title="{GROUP_NAME}", {movie["title"]}\n{movie["stream_url"]}|Referer={movie["headers"]["Referer"]}\n'

        self.send_response(200)
        self.send_header('Content-Type', 'audio/x-mpegurl')
        self.send_header('Content-Disposition', 'inline; filename="latest.m3u"')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(m3u_content.encode('utf-8'))
        
