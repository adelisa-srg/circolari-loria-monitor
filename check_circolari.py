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
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "false").lower() == "true"

STATE_FILE = "last_circolare.json"
DASHBOARD_FILE = "data/dashboard.json"


def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()) if text else ""


def fetch_soup(url):
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=20,
    )


# =========================
# CIRCOLARI
# =========================

def extract_latest_circular():
    soup = fetch_soup(CIRCOLARI_URL)

    marker = soup.find(string=lambda t: t and "Circolare del" in t)
    card = marker.parent

    for _ in range(20):
        if not card:
            break
        if "Pubblicato il:" in card.get_text():
            break
        card = card.parent

    text = card.get_text("\n", strip=True)
    lines = [normalize(l) for l in text.split("\n") if normalize(l)]

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    attachment_name = ""
    attachment_link = ""

    for i, line in enumerate(lines):
        if line.startswith("Circolare del"):
            circular_date = line.replace("Circolare del", "").strip()
            title = lines[i + 1]

        elif line.startswith("Pubblicato il:"):
            published_date = lines[i + 1]

        elif line.startswith("Tipologia:"):
            tipologia = lines[i + 1]

        elif line.startswith("Allegati:"):
            attachment_name = lines[i + 1]

    for a in card.find_all("a", href=True):
        if "spaggiari" in a["href"]:
            attachment_link = a["href"]

    return {
        "id": attachment_link,
        "title": title,
        "circular_date": circular_date,
        "published_date": published_date,
        "tipologia": tipologia,
        "attachment_name": attachment_name,
        "link": attachment_link,
    }


# =========================
# NEWS (FIX VERO)
# =========================

def extract_news(limit=10):
    soup = fetch_soup(NEWS_URL)

    items = []

    # prende SOLO link che puntano a pagine interne "pagine/"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = normalize(a.get_text())

        if not title or len(title) < 15:
            continue

        # filtro chiave: le news vere stanno sotto /pagine/
        if "/pagine/" not in href:
            continue

        link = urljoin(BASE_URL, href)

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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =========================
# MESSAGE
# =========================

def build_message(item):
    return f"""📢 <b>Nuova circolare - Scuola Primaria</b>

📄 <b>{item["title"]}</b>

🗓️ {item["circular_date"]}
📌 {item["published_date"]}
🏷️ {item["tipologia"]}

👉 <a href="{item["link"]}">Apri circolare</a>
"""


# =========================
# MAIN
# =========================

def main():
    latest = extract_latest_circular()
    news = extract_news()

    print("=== NEWS ===")
    print(json.dumps(news, indent=2, ensure_ascii=False))

    prev = load_json(STATE_FILE, {})

    if FORCE_NOTIFY or latest["id"] != prev.get("id"):
        send_telegram(build_message(latest))

    save_json(STATE_FILE, latest)

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "circular": latest,
        "news": news
    }

    save_json(DASHBOARD_FILE, dashboard)


if __name__ == "__main__":
    main()
