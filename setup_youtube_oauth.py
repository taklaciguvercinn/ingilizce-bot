#!/usr/bin/env python3
"""
YouTube OAuth Kurulum - Bir kere çalıştır, refresh token al.
Hangi Google hesabıyla giriş yaparsan o kanalın kanalına video yüklenir.
"""
import json, urllib.parse, urllib.request, http.server, threading, webbrowser, sys

print("""
╔══════════════════════════════════════════════════════════╗
║         YouTube OAuth Kurulum (Tek Seferlik)             ║
╠══════════════════════════════════════════════════════════╣
║  Adımlar:                                                ║
║  1. console.cloud.google.com → Yeni proje                ║
║  2. YouTube Data API v3 → Enable                         ║
║  3. OAuth consent screen → External → Kaydet             ║
║  4. Credentials → OAuth Client ID → Desktop App          ║
║  5. Client ID ve Secret'ı buraya yaz                     ║
╚══════════════════════════════════════════════════════════╝
""")

CLIENT_ID     = input("Client ID     : ").strip()
CLIENT_SECRET = input("Client Secret : ").strip()

REDIRECT = "http://localhost:8080"
SCOPE    = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"

url = (f"https://accounts.google.com/o/oauth2/auth?"
       f"client_id={CLIENT_ID}&redirect_uri={urllib.parse.quote(REDIRECT)}"
       f"&scope={urllib.parse.quote(SCOPE)}&response_type=code"
       f"&access_type=offline&prompt=consent")

code = None

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global code
        code = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code",[None])[0]
        self.send_response(200); self.send_header("Content-type","text/html"); self.end_headers()
        self.wfile.write(b"<h1>Tamam! Bu pencereyi kapat.</h1>")
    def log_message(self, *a): pass

srv = http.server.HTTPServer(("localhost",8080), H)
t = threading.Thread(target=srv.handle_request); t.start()

print("\n🌐 Tarayıcı açılıyor... YouTube kanalına giriş yap ve izin ver.")
try: webbrowser.open(url)
except: print(f"Manuel aç:\n{url}")

t.join(120)
if not code: print("❌ Zaman aşımı!"); sys.exit(1)

data = urllib.parse.urlencode({
    "code":CLIENT_ID and code, "client_id":CLIENT_ID,
    "client_secret":CLIENT_SECRET, "redirect_uri":REDIRECT,
    "grant_type":"authorization_code"
}).encode()
# düzelt
data = urllib.parse.urlencode({
    "code":code, "client_id":CLIENT_ID,
    "client_secret":CLIENT_SECRET, "redirect_uri":REDIRECT,
    "grant_type":"authorization_code"
}).encode()

req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
req.add_header("Content-Type","application/x-www-form-urlencoded")
with urllib.request.urlopen(req) as r:
    tokens = json.loads(r.read())

rt = tokens.get("refresh_token")
if not rt: print("❌ Refresh token yok! OAuth consent'te prompt=consent olduğundan emin ol."); sys.exit(1)

print(f"""
╔══════════════════════════════════════════════════════════╗
║  ✅ Başarılı! Bunları GitHub Secrets'a kaydet:           ║
╚══════════════════════════════════════════════════════════╝

YOUTUBE_CLIENT_ID     = {CLIENT_ID}
YOUTUBE_CLIENT_SECRET = {CLIENT_SECRET}
YOUTUBE_REFRESH_TOKEN = {rt}

⚠️  Bu bilgileri güvenli tut, kimseyle paylaşma!
""")
