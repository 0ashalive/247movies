from http.server import BaseHTTPRequestHandler
import json
import re
import urllib.request


class handler(BaseHTTPRequestHandler):

  def do_GET(self):
    m3u_url = "https://raw.githubusercontent.com/srhady/join_telegram_chennal-livesportsplay/refs/heads/main/latest_movies.m3u"

    try:
      # M3U ফাইল ডাউনলোড (User-Agent সহ)
      req = urllib.request.Request(
          m3u_url, headers={"User-Agent": "Mozilla/5.0"}
      )
      with urllib.request.urlopen(req) as response:
        content = response.read().decode("utf-8")

      lines = content.splitlines()
      all_items = []
      i = 0
      total_lines = len(lines)

      while i < total_lines:
        line = lines[i].strip()

        # #EXTINF লাইন শনাক্ত করা
        if line.startswith("#EXTINF:"):
          # Title বের করা
          title = ""
          title_match = re.search(r",([^,]+)$", line)
          if title_match:
            title = title_match.group(1).strip()

          # Poster (tvg-logo) বের করা
          poster = ""
          logo_match = re.search(r'tvg-logo="([^"]+)"', line)
          if logo_match:
            poster = logo_match.group(1)

          # পরের লাইনে Stream URL ও Headers থাকে
          i += 1
          if i < total_lines:
            url_line = lines[i].strip()
            stream_url = url_line
            headers = {}

            # URL এবং Referer আলাদা করা (যদি pipe '|' থাকে)
            if "|" in url_line:
              parts = url_line.split("|", 1)
              stream_url = parts[0]

              if "Referer=" in parts[1]:
                referer_parts = parts[1].split("Referer=")
                headers = {"Referer": referer_parts[1]}

            # আইটেম অবজেক্ট তৈরি
            item = {
                "id": title,
                "title": title,
                "poster": poster,
                "stream_url": stream_url,
                "headers": headers,
            }

            all_items.append(item)

        i += 1

      # প্রথম ৫টি আইটেম Hero-তে রাখা
      hero_items = all_items[:5]

      # বাকি সব আইটেম Movies-এ রাখা
      movie_items = all_items[5:]

      # ফাইনাল JSON স্ট্রাকচার
      final_data = {
          "hero": hero_items,
          "categories": [{"name": "MOVIES", "items": movie_items}],
      }

      # Vercel JSON Response পাঠানো
      self.send_response(200)
      self.send_header("Content-Type", "application/json")
      self.send_header("Access-Control-Allow-Origin", "*")
      self.end_headers()

      json_output = json.dumps(final_data, ensure_ascii=False, indent=2)
      self.wfile.write(json_output.encode("utf-8"))

    except Exception as e:
      self.send_response(500)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      error_response = json.dumps({"error": str(e)})
      self.wfile.write(error_response.encode("utf-8"))
        
