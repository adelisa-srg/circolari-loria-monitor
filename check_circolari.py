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
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def send_telegram(text):
    if not TELEGRAM_TOKEN:
        raise Exception("TELEGRAM_TOKEN mancante")
    if not TELEGRAM_CHAT_ID:
        raise Exception("TELEGRAM_CHAT_ID mancante")

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)
    response.raise_for_status()


def extract_latest_circular():
    soup = fetch_soup(CIRCOLARI_URL)

    marker = soup.find(string=lambda t: t and "Circolare del" in t)
    if not marker:
        raise Exception("Nessuna circolare trovata")

    card = marker.parent

    for _ in range(20):
        if not card:
            break

        text = card.get_text(" ", strip=True)
        if "Pubblicato il:" in text and "Tipologia:" in text:
            break

        card = card.parent

    if not card:
        raise Exception("Card circolare non trovata")

    full_text = card.get_text("\n", strip=True)
    lines = [normalize(line) for line in full_text.split("\n") if normalize(line)]

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    attachment_name = ""
    attachment_link = ""

    for i, line in enumerate(lines):
        if line.startswith("Circolare del"):
            circular_date = line.replace("Circolare del", "").strip()
            if i + 1 < len(lines):
                title = lines[i + 1]

        elif line.startswith("Pubblicato il:"):
            if i + 1 < len(lines):
                published_date = lines[i + 1]

        elif line.startswith("Tipologia:"):
            if i + 1 < len(lines):
                tipologia = lines[i + 1]

        elif line.startswith("Allegati:"):
            if i + 1 < len(lines):
                attachment_name = lines[i + 1]

    for a in card.find_all("a", href=True):
        href = a["href"]
        if "spaggiari" in href.lower():
            attachment_link = href if href.startswith("http") else urljoin(BASE_URL, href)

    if not title:
        raise Exception("Titolo circolare non estratto")

    if not attachment_link:
        raise Exception("Link circolare non estratto")

    return {
        "id": attachment_link,
        "type": "circular",
        "title": title,
        "circular_date": circular_date,
        "published_date": published_date,
        "tipologia": tipologia,
        "attachment_name": attachment_name,
        "link": attachment_link,
        "source_url": CIRCOLARI_URL,
    }


def extract_news(limit=10):
    soup = fetch_soup(NEWS_URL)

    items = []
    seen = set()

    blacklist = [
        "i numeri",
        "calendario",
        "offerta",
        "progetti delle classi",
        "panoramica",
        "presentazione",
        "la storia",
        "le persone",
        "i luoghi",
        "organizzazione",
        "le carte",
        "scuola primaria",
        "scuola secondaria",
        "registro elettronico",
        "amministrazione",
        "privacy",
        "cookie",
        "accessibilità",
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = normalize(a.get_text())
        lower_title = title.lower()

        if not title or len(title) < 15:
            continue

        if "/pagine/" not in href:
            continue

        if any(bad in lower_title for bad in blacklist):
            continue

        link = urljoin(BASE_URL, href)

        if link in seen:
            continue

        seen.add(link)

        items.append(
            {
                "id": link,
                "type": "news",
                "title": title,
                "date": "",
                "link": link,
                "source_url": NEWS_URL,
            }
        )

        if len(items) >= limit:
            break

    return items


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


def build_message(item):
    return f"""📢 <b>Nuova circolare - Scuola Primaria</b>

📄 <b>{item["title"]}</b>

🗓️ <b>Data circolare:</b> {item.get("circular_date") or "N/D"}
📌 <b>Pubblicata il:</b> {item.get("published_date") or "N/D"}
🏷️ <b>Tipologia:</b> {item.get("tipologia") or "N/D"}

👉 <a href="{item["link"]}">Apri circolare</a>
"""


def main():
    latest = extract_latest_circular()
    news = extract_news()

    print("=== CIRCOLARE ===")
    print(json.dumps(latest, indent=2, ensure_ascii=False))

    print("=== NEWS ===")
    print(json.dumps(news, indent=2, ensure_ascii=False))

    previous = load_json(STATE_FILE, {})

    should_notify = FORCE_NOTIFY or latest["id"] != previous.get("id")

    if should_notify:
        send_telegram(build_message(latest))
        print("Notifica Telegram inviata.")
    else:
        print("Nessuna nuova circolare.")

    save_json(STATE_FILE, latest)

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "circular": latest,
        "news": news,
    }

    save_json(DASHBOARD_FILE, dashboard)


if __name__ == "__main__":
    main()
