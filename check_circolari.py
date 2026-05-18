import json
import os
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.icsmoiseloria.edu.it"

CIRCOLARI_URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"
NEWS_URL = "https://www.icsmoiseloria.edu.it/archivio-news"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
IFTTT_KEY = os.getenv("IFTTT_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL")

STATE_FILE = "last_circolare.json"
NEWS_STATE_FILE = "last_news.json"
DASHBOARD_FILE = "docs/data/dashboard.json"


def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()) if text else ""


def fetch_soup(url):
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


# =========================
# TELEGRAM
# =========================

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        },
    )


# =========================
# WHATSAPP via IFTTT
# =========================

def send_whatsapp(text):
    if not IFTTT_KEY:
        return

    url = f"https://maker.ifttt.com/trigger/school_loria_update/with/key/{IFTTT_KEY}"

    requests.post(url, json={
        "value1": text
    })


# =========================
# CIRCOLARI
# =========================

def extract_latest_circular():
    soup = fetch_soup(CIRCOLARI_URL)

    marker = soup.find(string=lambda t: t and "Circolare del" in t)
    card = marker.parent

    for _ in range(20):
        if "Pubblicato il:" in card.get_text():
            break
        card = card.parent

    text = card.get_text("\n", strip=True)
    lines = [normalize(l) for l in text.split("\n") if normalize(l)]

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    link = ""

    for i, line in enumerate(lines):
        if "Circolare del" in line:
            circular_date = line.replace("Circolare del", "").strip()
            title = lines[i + 1]

        elif "Pubblicato il:" in line:
            published_date = lines[i + 1]

        elif "Tipologia:" in line:
            tipologia = lines[i + 1]

    for a in card.find_all("a", href=True):
        if "spaggiari" in a["href"]:
            link = a["href"]

    return {
        "id": link,
        "title": title,
        "circular_date": circular_date,
        "published_date": published_date,
        "tipologia": tipologia,
        "link": link,
    }


# =========================
# NEWS
# =========================

def extract_news(limit=10):
    soup = fetch_soup(NEWS_URL)

    items = []
    seen = set()

    blacklist = ["numeri", "calendario", "offerta"]

    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text())
        href = a["href"]

        if len(title) < 15:
            continue

        if "/pagine/" not in href:
            continue

        if any(b in title.lower() for b in blacklist):
            continue

        link = urljoin(BASE_URL, href)

        if link in seen:
            continue

        seen.add(link)

        items.append({
            "id": link,
            "title": title,
            "link": link
        })

        if len(items) >= limit:
            break

    return items


# =========================
# STORAGE
# =========================

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# =========================
# MESSAGES
# =========================

def build_circular_message(c):
    return f"""📢 NUOVA CIRCOLARE

📄 {c["title"]}

🗓️ {c["circular_date"]}
📌 {c["published_date"]}
🏷️ {c["tipologia"]}

👉 Apri:
{c["link"]}

📊 Dashboard:
{DASHBOARD_URL}
"""


def build_news_message(n):
    return f"""📰 NUOVA NEWS

📄 {n["title"]}

👉 Apri:
{n["link"]}

📊 Dashboard:
{DASHBOARD_URL}
"""


# =========================
# MAIN
# =========================

def main():
    circular = extract_latest_circular()
    news = extract_news()

    prev_circular = load_json(STATE_FILE, {})
    prev_news = load_json(NEWS_STATE_FILE, [])

    # ===== CIRCOLARE =====
    if circular["id"] != prev_circular.get("id"):
        msg = build_circular_message(circular)

        send_telegram(msg)
        send_whatsapp(msg)

        print("Nuova circolare inviata")

    save_json(STATE_FILE, circular)

    # ===== NEWS =====
    prev_ids = [n["id"] for n in prev_news]
    new_news = [n for n in news if n["id"] not in prev_ids]

    if new_news:
        print(f"Nuove news: {len(new_news)}")

        for n in new_news[:3]:
            msg = build_news_message(n)

            send_telegram(msg)
            send_whatsapp(msg)

    save_json(NEWS_STATE_FILE, news)

    # ===== DASHBOARD =====
    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "circular": circular,
        "news": news,
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
    }

    save_json(DASHBOARD_FILE, dashboard)


if __name__ == "__main__":
    main()
