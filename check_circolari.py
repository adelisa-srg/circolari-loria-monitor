import requests
from bs4 import BeautifulSoup
import json
import os

URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "last_circolare.json"

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        },
        timeout=20
    )

def get_latest():
    html = requests.get(URL, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = soup.find_all("a", href=True)

    for a in links:
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a["href"]

        if title and ("comunicat" in href.lower() or "circolare" in title.lower()):
            if href.startswith("/"):
                href = "https://www.icsmoiseloria.edu.it" + href
            elif not href.startswith("http"):
                href = "https://www.icsmoiseloria.edu.it/pvw2/app/default/" + href

            return {
                "title": title,
                "link": href
            }

    raise Exception("Nessuna circolare trovata")

def load_last():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_last(item):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

latest = get_latest()

message = f"📢 <b>TEST notifiche attive</b>\n\n{latest['title']}\n\n{latest['link']}"
send_telegram(message)

print("Test Telegram forzato inviato.")
