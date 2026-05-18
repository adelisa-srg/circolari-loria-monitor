import json
import os
import re
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
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def fetch_soup(url):
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    print(response.text)


# =========================
# CIRCOLARI
# =========================

def find_latest_circular_card(soup):
    marker = soup.find(string=lambda t: t and "Circolare del" in t)
    card = marker.parent

    for _ in range(20):
        if not card:
            break
        text = card.get_text(" ", strip=True)
        if "Pubblicato il:" in text and "Tipologia:" in text:
            return card
        card = card.parent

    raise Exception("Card circolare non trovata")


def extract_latest_circular():
    soup = fetch_soup(CIRCOLARI_URL)
    card = find_latest_circular_card(soup)

    full_text = card.get_text("\n", strip=True)
    lines = [normalize(l) for l in full_text.split("\n") if normalize(l)]

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

    links = card.find_all("a", href=True)

    for a in links:
        href = a["href"]
        if "spaggiari" in href:
            attachment_link = href if href.startswith("http") else urljoin(BASE_URL, href)

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
# NEWS (FIX DEFINITIVO)
# =========================

def extract_news(limit=10):
    soup = fetch_soup(NEWS_URL)

    items = []

    # prende SOLO articoli veri (card news)
    articles = soup.find_all("article")

    for art in articles:
        a = art.find("a", href=True)
        if not a:
            continue

        title = normalize(a.get_text())
        link = urljoin(BASE_URL, a["href"])

        if not title or len(title) < 10:
            continue

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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


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
