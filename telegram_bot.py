#!/usr/bin/env python3
"""
Telegram Bot v3
- 2 GitHub hesabı dönüşümlü kullanım (Actions limiti aşmamak için)
- Gemini API ile çalışır
- Her komutta hangi hesabın kullanıldığını bildirir
"""

import os, json, time, requests, logging, re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT_IDS   = os.environ.get("ALLOWED_CHAT_IDS","").split(",")

# ── 2 GitHub hesabı ──────────────────────────────────────────────────────────
# Hesap A (ana hesap)
GITHUB_TOKEN_A = os.environ["GITHUB_TOKEN_A"]
GITHUB_REPO_A  = os.environ["GITHUB_REPO_A"]   # kullanici_a/video-bot

# Hesap B (yedek hesap — 2. ücretsiz hesap)
GITHUB_TOKEN_B = os.environ.get("GITHUB_TOKEN_B","")
GITHUB_REPO_B  = os.environ.get("GITHUB_REPO_B","")

# Hangi hesabın sırası? Dosyaya yaz
STATE_FILE = "/tmp/account_state.json"

def get_state() -> dict:
    try:
        return json.loads(open(STATE_FILE).read())
    except:
        return {"current": "A", "a_count": 0, "b_count": 0, "total": 0}

def save_state(s: dict):
    open(STATE_FILE,"w").write(json.dumps(s))

def next_account(state: dict) -> tuple:
    """
    Dönüşüm mantığı:
    - A hesabı: 1700 dakika dolduysa (güvenli limit) → B'ye geç
    - B hesabı: 1700 dakika dolduysa → A'ya geç
    - B hesabı yoksa: her zaman A
    Her video Actions'ta ~50 dk sürer.
    1700 / 50 = 34 video per account per month
    """
    if not GITHUB_TOKEN_B:
        return "A", GITHUB_TOKEN_A, GITHUB_REPO_A

    # Basit dönüşüm: her 30 videoda bir hesap değiştir
    LIMIT = 30
    if state["current"] == "A" and state["a_count"] >= LIMIT:
        state["current"] = "B"
        state["a_count"] = 0
    elif state["current"] == "B" and state["b_count"] >= LIMIT:
        state["current"] = "A"
        state["b_count"] = 0

    if state["current"] == "A":
        state["a_count"] += 1
        return "A", GITHUB_TOKEN_A, GITHUB_REPO_A
    else:
        state["b_count"] += 1
        return "B", GITHUB_TOKEN_B, GITHUB_REPO_B
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HELP_TEXT = """🎬 <b>Video Bot v3 Komutları</b>

<b>Video oluştur:</b>
<code>Konu,Dakika,Resim,GG.AA.YYYY,SS:DD</code>

<b>Örnekler:</b>
<code>Vikingler,15,5,25.04.2026,18:00</code>
<code>Osmanlı İmparatorluğu,40,50,26.04.2026,20:00</code>
<code>Yapay Zeka,20,15,27.04.2026,12:00</code>

<b>Dikkat — 40 dk + 50 resim için:</b>
• Görsel üretimi: ~10 dakika (paralel)
• Video montajı: ~25 dakika
• Toplam: ~45-60 dakika Actions süresi

<b>Diğer:</b>
/help - Bu mesaj
/status - Son çalışma durumu
/quota - Kalan aylık kota tahmini"""

CMD_RE = re.compile(
    r"^.+,\s*\d+\s*,\s*\d+\s*,\s*\d{2}\.\d{2}\.\d{4}\s*,\s*\d{2}:\d{2}\s*$"
)

def send(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage",
        json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"}, timeout=10)

def trigger(token: str, repo: str, command: str) -> bool:
    r = requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/video_bot.yml/dispatches",
        headers={"Authorization":f"token {token}",
                 "Accept":"application/vnd.github.v3+json"},
        json={"ref":"main","inputs":{"command":command}},
        timeout=15
    )
    return r.status_code == 204

def get_run_status(token: str, repo: str) -> str:
    r = requests.get(
        f"https://api.github.com/repos/{repo}/actions/runs?per_page=1",
        headers={"Authorization":f"token {token}",
                 "Accept":"application/vnd.github.v3+json"},
        timeout=10
    )
    if r.status_code != 200: return "Durum alınamadı"
    runs = r.json().get("workflow_runs",[])
    if not runs: return "Henüz çalışma yok"
    run = runs[0]
    conclusion = run.get("conclusion") or "devam ediyor"
    created    = run.get("created_at","?")[:16].replace("T"," ")
    emoji = {"success":"✅","failure":"❌","cancelled":"⚠️"}.get(conclusion,"⏳")
    mins_used = run.get("run_duration_ms",0) // 60000
    return (f"{emoji} <b>Son çalışma</b>\n"
            f"Durum: {conclusion}\n"
            f"Tarih: {created}\n"
            f"Süre: {mins_used} dakika")

def handle(msg: dict):
    chat_id = str(msg["chat"]["id"])
    text    = msg.get("text","").strip()
    user    = msg["from"].get("first_name","?")

    if ALLOWED_CHAT_IDS and ALLOWED_CHAT_IDS[0] and chat_id not in ALLOWED_CHAT_IDS:
        send(chat_id,"⛔ Erişim yetkiniz yok.")
        return

    log.info(f"[{chat_id}] {user}: {text}")

    if text in ["/start","/help"]:
        send(chat_id, HELP_TEXT)

    elif text == "/status":
        state = get_state()
        cur   = state["current"]
        tok   = GITHUB_TOKEN_A if cur=="A" else GITHUB_TOKEN_B
        repo  = GITHUB_REPO_A  if cur=="A" else GITHUB_REPO_B
        send(chat_id, get_run_status(tok, repo))

    elif text == "/quota":
        state = get_state()
        a_used = state["a_count"]
        b_used = state["b_count"]
        total  = state["total"]
        b_info = f"\n🅱 Hesap B: {b_used}/30 video kullanıldı" if GITHUB_TOKEN_B else "\n⚠ İkinci hesap bağlı değil"
        send(chat_id,
            f"📊 <b>Kota Durumu</b>\n\n"
            f"🅰 Hesap A: {a_used}/30 video kullanıldı"
            f"{b_info}\n\n"
            f"📹 Bu ay toplam: {total} video yapıldı\n\n"
            f"{'✅ Kota yeterli' if total < 55 else '⚠ Kota dolmak üzere!'}")

    elif CMD_RE.match(text):
        parts = [p.strip() for p in text.split(",")]
        topic, dur, imgs, date_s, time_s = parts

        try:
            from datetime import datetime
            datetime.strptime(f"{date_s} {time_s}", "%d.%m.%Y %H:%M")
            assert int(dur) >= 1 and int(imgs) >= 1
        except:
            send(chat_id,"❌ Hatalı format!\nÖrnek: <code>Vikingler,15,5,25.04.2026,18:00</code>")
            return

        # Hesap seç
        state             = get_state()
        acc, tok, repo    = next_account(state)
        state["total"]   += 1
        save_state(state)

        send(chat_id,
            f"⚙️ <b>Komut alındı!</b>\n\n"
            f"📌 Konu  : <b>{topic}</b>\n"
            f"⏱ Süre  : {dur} dakika\n"
            f"🖼 Görsel: {imgs} adet\n"
            f"📅 Yayın : {date_s} {time_s}\n\n"
            f"🔀 Aktif hesap: <b>Hesap {acc}</b>\n"
            f"🚀 GitHub Actions başlatılıyor...")

        if trigger(tok, repo, text):
            est = int(imgs)//5 + int(dur)//2 + 10
            send(chat_id,
                f"✅ <b>Başlatıldı!</b>\n\n"
                f"Her adımda buraya bildirim gelecek.\n"
                f"⏳ Tahmini toplam süre: ~{est} dakika\n\n"
                f"🔗 İzlemek için:\n"
                f"github.com/{repo}/actions")
        else:
            send(chat_id,
                "❌ GitHub Actions tetiklenemedi!\n"
                "Token veya repo adresini kontrol et.\n"
                "/status ile durumu kontrol edebilirsin.")
    else:
        send(chat_id,
            "❓ Komut tanınmadı.\n\n"
            "Format: <code>Konu,Dakika,Resim,GG.AA.YYYY,SS:DD</code>\n"
            "Yardım: /help")

def run():
    log.info("Telegram Bot v3 başladı...")
    offset = 0
    while True:
        try:
            r = requests.get(f"{BASE_URL}/getUpdates",
                params={"offset":offset,"timeout":30}, timeout=40)
            if r.status_code == 200:
                for upd in r.json().get("result",[]):
                    offset = upd["update_id"] + 1
                    if "message" in upd:
                        handle(upd["message"])
        except Exception as e:
            log.error(f"Polling hata: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
