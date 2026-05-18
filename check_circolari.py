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


def find_latest_circular_card(soup):
    marker = soup.find(string=lambda t: t and "Circolare del" in t)

    if not marker:
        raise Exception("Nessuna circolare trovata: marker 'Circolare del' assente")

    card = marker.parent

    for _ in range(20):
        if not card:
            break

        text = card.get_text(" ", strip=True)

        if "Pubblicato il:" in text and "Tipologia:" in text:
            return card

        card = card.parent

    raise Exception("Card circolare trovata, ma struttura HTML non riconosciuta")


def extract_latest_circular():
    soup = fetch_soup(CIRCOLARI_URL)
    card = find_latest_circular_card(soup)

    full_text = card.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [normalize(line) for line in full_text.split("\n") if normalize(line)]

    print("=== DEBUG CIRCULAR LINES ===")
    for i, line in enumerate(lines):
        print(f"{i}: {line}")

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    attachment_name = ""
    attachment_link = ""

    for i, line in enumerate(lines):
        if line.startswith("Circolare del"):
            circular_date = normalize(line.replace("Circolare del", ""))
            if i + 1 < len(lines):
                title = lines[i + 1]

        elif line.startswith("Pubblicato il:"):
            value = normalize(line.replace("Pubblicato il:", ""))
            if value:
                published_date = value
            elif i + 1 < len(lines):
                published_date = lines[i + 1]

        elif line.startswith("Tipologia:"):
            value = normalize(line.replace("Tipologia:", ""))
            if value:
                tipologia = value
            elif i + 1 < len(lines):
                tipologia = lines[i + 1]

        elif line.startswith("Allegati:") and i + 1 < len(lines):
            attachment_name = lines[i + 1]

    if not title:
        for line in lines:
            if "CIRCOLARE" in line.upper() and not line.startswith("Circolare del"):
                title = line
                break

    links = card.find_all("a", href=True)
    candidates = []

    for a in links:
        href = a.get("href", "")
        text = normalize(a.get_text(" ", strip=True))
        absolute_link = urljoin(BASE_URL, href)

        if not href:
            continue

        if href.lower().startswith("javascript:"):
            continue

        if href.startswith("#"):
            continue

        score = 0

        if ".pdf" in href.lower():
            score += 50

        if ".pdf" in text.lower():
            score += 50

        if "download" in href.lower():
            score += 20

        if "download" in text.lower():
            score += 20

        if "allegat" in href.lower() or "allegat" in text.lower():
            score += 20

        if "Circ" in text or "CIRC" in text:
            score += 30

        if text and not re.fullmatch(r"\d+\.pdf", text, re.IGNORECASE):
            score += 10

        candidates.append(
            {
                "score": score,
                "text": text,
                "href": href,
                "absolute_link": absolute_link,
            }
        )

    print("=== DEBUG LINK CANDIDATES ===")
    print(json.dumps(candidates, ensure_ascii=False, indent=2))

    if candidates:
        candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
        chosen = candidates[0]

        attachment_link = chosen["absolute_link"]

        if not attachment_name:
            attachment_name = chosen["text"] or chosen["href"].split("/")[-1]

    if not title:
        raise Exception("Titolo circolare non estratto")

    if not attachment_link:
        raise Exception("Link allegato/circolare non estratto")

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

    bad_titles = [
        "salta al contenuto",
        "italiano",
        "privacy",
        "cookie",
        "accessibilità",
        "amministrazione trasparente",
        "albo online",
        "registro elettronico",
        "mad",
        "pon",
        "pcto",
        "consigli di classe",
        "consigli di istituto",
        "istituto",
        "organigramma",
        "presidenza",
        "regolamento d'istituto",
        "scuola primaria",
        "scuola secondaria",
    ]

    for a in soup.find_all("a", href=True):
        title = normalize(a.get_text(" ", strip=True))
        href = a.get("href", "")
        link = urljoin(BASE_URL, href)
        lower_title = title.lower()

        if not title or len(title) < 8:
            continue

        if any(bad in lower_title for bad in bad_titles):
            continue

        if "icsmoiseloria.edu.it" not in link:
            continue

        if "#maincontent" in link or "/cerca?tag=" in link:
            continue

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
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_circular_message(item):
    return f"""📢 <b>Nuova circolare - Scuola Primaria</b>

📄 <b>{item.get("title") or "Titolo non disponibile"}</b>

🗓️ <b>Data circolare:</b> {item.get("circular_date") or "N/D"}
📌 <b>Pubblicata il:</b> {item.get("published_date") or "N/D"}
🏷️ <b>Tipologia:</b> {item.get("tipologia") or "N/D"}

📎 <b>Documento disponibile</b>

👉 <a href="{item.get("link")}">Apri circolare</a>
"""


def main():
    latest_circular = extract_latest_circular()
    news = extract_news(limit=10)

    print("=== Ultima circolare ===")
    print(json.dumps(latest_circular, ensure_ascii=False, indent=2))

    print("=== News estratte ===")
    print(json.dumps(news, ensure_ascii=False, indent=2))

    previous_state = load_json(STATE_FILE, default={})
    previous_circular_id = previous_state.get("latest_circular_id")

    dashboard = {
        "last_check_utc": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "latest_circular": latest_circular,
        "news": news,
    }

    save_json(DASHBOARD_FILE, dashboard)

    should_notify = FORCE_NOTIFY or latest_circular["id"] != previous_circular_id

    if should_notify:
        send_telegram(build_circular_message(latest_circular))
        print("Notifica Telegram inviata.")
    else:
        print("Nessuna nuova circolare.")

    save_json(
        STATE_FILE,
        {
            "latest_circular_id": latest_circular["id"],
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


if __name__ == "__main__":
    main()
