from http.server import BaseHTTPRequestHandler
import json
from upstash_redis import Redis

redis = Redis.from_env()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        all_movies_raw = redis.get("data_json_db")
        all_movies_dict = json.loads(all_movies_raw) if all_movies_raw else {}
        
        all_items = list(all_movies_dict.values())

        # আপনার চাহিদামতো JSON ফরম্যাট
        output = {
            "hero": all_items[:5] if len(all_items) >= 5 else all_items,
            "categories": [
                {
                    "name": "MOVIES",
                    "items": all_items
                }
            ]
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(output, indent=4).encode('utf-8'))
        
