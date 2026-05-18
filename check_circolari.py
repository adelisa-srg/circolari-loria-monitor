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
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://adelisa-srg.github.io/circolari-loria-monitor/")

STATE_FILE = "last_circolare.json"
NEWS_STATE_FILE = "last_news.json"
DASHBOARD_FILE = "docs/data/dashboard.json"


def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()) if text else ""


def fetch_soup(url):
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def send_telegram(text, buttons=None):
    if not TELEGRAM_TOKEN:
        raise Exception("TELEGRAM_TOKEN mancante")
    if not TELEGRAM_CHAT_ID:
        raise Exception("TELEGRAM_CHAT_ID mancante")

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": buttons
        }

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json=payload,
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
        if "Pubblicato il:" in card.get_text():
            break
        card = card.parent

    if not card:
        raise Exception("Card circolare non trovata")

    text = card.get_text("\n", strip=True)
    lines = [normalize(l) for l in text.split("\n") if normalize(l)]

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    link = ""
    attachment_name = ""

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
            link = href if href.startswith("http") else urljoin(BASE_URL, href)

    if not title:
        raise Exception("Titolo circolare non estratto")
    if not link:
        raise Exception("Link circolare non estratto")

    return {
        "id": link,
        "type": "circular",
        "title": title,
        "circular_date": circular_date,
        "published_date": published_date,
        "tipologia": tipologia,
        "attachment_name": attachment_name,
        "link": link,
        "source_url": CIRCOLARI_URL,
    }


def extract_news(limit=10):
    soup = fetch_soup(NEWS_URL)

    items = []
    seen = set()

    blacklist = [
        "numeri",
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
        title = normalize(a.get_text())
        href = a["href"]
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

        items.append({
            "id": link,
            "type": "news",
            "title": title,
            "date": "",
            "link": link,
            "source_url": NEWS_URL,
        })

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


def circular_buttons(c):
    return [
        [
            {"text": "📄 Apri circolare", "url": c["link"]},
            {"text": "📊 Dashboard", "url": DASHBOARD_URL},
        ],
        [
            {"text": "🏫 Tutte le circolari", "url": CIRCOLARI_URL},
        ],
    ]


def news_buttons(n):
    return [
        [
            {"text": "📰 Apri news", "url": n["link"]},
            {"text": "📊 Dashboard", "url": DASHBOARD_URL},
        ],
        [
            {"text": "🏫 Archivio news", "url": NEWS_URL},
        ],
    ]


def build_circular_message(c):
    return f"""📢 <b>NUOVA CIRCOLARE · SCUOLA PRIMARIA</b>

━━━━━━━━━━━━━━━━━━━━

📄 <b>{c["title"]}</b>

🗓️ <b>Data circolare:</b> {c.get("circular_date") or "N/D"}
📌 <b>Pubblicata il:</b> {c.get("published_date") or "N/D"}
🏷️ <b>Tipologia:</b> {c.get("tipologia") or "N/D"}

━━━━━━━━━━━━━━━━━━━━

Usa i pulsanti qui sotto 👇
"""


def build_news_message(n):
    return f"""📰 <b>NUOVA NEWS · SCUOLA LORIA</b>

━━━━━━━━━━━━━━━━━━━━

📄 <b>{n["title"]}</b>

━━━━━━━━━━━━━━━━━━━━

Usa i pulsanti qui sotto 👇
"""


def main():
    circular = extract_latest_circular()
    news = extract_news()

    print("=== CIRCOLARE ===")
    print(json.dumps(circular, indent=2, ensure_ascii=False))

    print("=== NEWS ===")
    print(json.dumps(news, indent=2, ensure_ascii=False))

    prev_circular = load_json(STATE_FILE, {})
    prev_news = load_json(NEWS_STATE_FILE, [])

    if circular["id"] != prev_circular.get("id"):
        send_telegram(build_circular_message(circular), circular_buttons(circular))
        print("Nuova circolare inviata")
    else:
        print("Nessuna nuova circolare.")

    save_json(STATE_FILE, circular)

    prev_ids = [n["id"] for n in prev_news]
    new_news = [n for n in news if n["id"] not in prev_ids]

    if new_news:
        print(f"Nuove news: {len(new_news)}")

        for n in new_news[:3]:
            send_telegram(build_news_message(n), news_buttons(n))
    else:
        print("Nessuna nuova news.")

    save_json(NEWS_STATE_FILE, news)

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "circular": circular,
        "news": news,
    }

    save_json(DASHBOARD_FILE, dashboard)


if __name__ == "__main__":
    main()
