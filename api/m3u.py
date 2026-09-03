from http.server import BaseHTTPRequestHandler
import json
import os
from upstash_redis import Redis

def get_redis():
    try:
        url = os.environ.get("UPSTASH_REDIS_REST_URL")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            return Redis(url=url, token=token)
    except Exception:
        pass
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        all_items = []
        try:
            redis = get_redis()
            if redis:
                all_movies_raw = redis.get("data_json_db")
                if all_movies_raw:
                    all_movies_dict = json.loads(all_movies_raw)
                    all_items = list(all_movies_dict.values())
        except Exception:
            pass

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
        
