import json
import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"
BASE_URL = "https://www.icsmoiseloria.edu.it"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "last_circolare.json"


def normalize(text):
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


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


def extract_first_circular_card(soup):
    marker = soup.find(string=lambda t: t and "Circolare del" in t)
    if not marker:
        raise Exception("Nessuna card circolare trovata: marker 'Circolare del' assente")

    card = marker.parent

    # Risale il DOM finché trova un blocco che contiene anche allegati/link
    for _ in range(10):
        if not card:
            break

        card_text = normalize(card.get_text(" ", strip=True))
        has_date = "Pubblicato il:" in card_text
        has_type = "Tipologia:" in card_text
        has_link = card.find("a", href=True) is not None

        if has_date and has_type and has_link:
            return card

        card = card.parent

    raise Exception("Card circolare trovata, ma struttura HTML non riconosciuta")


def get_latest():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    card = extract_first_circular_card(soup)

    full_text = card.get_text("\n", strip=True)
    lines = [normalize(line) for line in full_text.split("\n") if normalize(line)]

    circular_date = ""
    title = ""
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
            published_date = line.replace("Pubblicato il:", "").strip()

        elif line.startswith("Tipologia:"):
            tipologia = line.replace("Tipologia:", "").strip()

    # Cerca preferibilmente un PDF, altrimenti il primo link utile
    links = card.find_all("a", href=True)
    pdf_link = None

    for a in links:
        href = a.get("href", "")
        text = normalize(a.get_text(" ", strip=True))
        if ".pdf" in href.lower() or ".pdf" in text.lower():
            pdf_link = a
            break

    if not pdf_link and links:
        pdf_link = links[0]

    if pdf_link:
        attachment_name = normalize(pdf_link.get_text(" ", strip=True))
        href = pdf_link["href"]
        attachment_link = urljoin(BASE_URL, href)

    if not title:
        raise Exception("Titolo circolare non estratto")

    if not attachment_link:
        raise Exception("Link allegato/circolare non estratto")

    # ID stabile: meglio il link allegato; se cambia quello, è nuova circolare
    circular_id = attachment_link

    return {
        "id": circular_id,
        "title": title,
        "circular_date": circular_date,
        "published_date": published_date,
        "tipologia": tipologia,
        "attachment_name": attachment_name,
        "link": attachment_link,
    }


def load_last():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_last(item):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)


def build_message(latest):
    return f"""📢 <b>Nuova circolare - Scuola Primaria</b>

📄 <b>{latest.get('title', 'Titolo non disponibile')}</b>

🗓️ <b>Data circolare:</b> {latest.get('circular_date') or 'N/D'}
📌 <b>Pubblicata il:</b> {latest.get('published_date') or 'N/D'}
🏷️ <b>Tipologia:</b> {latest.get('tipologia') or 'N/D'}

📎 <b>Allegato:</b>
{latest.get('attachment_name') or 'N/D'}

👉 <a href="{latest.get('link')}">Apri documento</a>
"""


latest = get_latest()

print("=== Ultima circolare estratta ===")
print(json.dumps(latest, ensure_ascii=False, indent=2))

# TEST MODE: imposta FORCE_NOTIFY=true nei Secrets/Variables o nel workflow per forzare l'invio
force_notify = os.getenv("FORCE_NOTIFY", "false").lower() == "true"

last = load_last()

if force_notify:
    print("FORCE_NOTIFY=true: invio test forzato")
    send_telegram(build_message(latest))
    save_last(latest)

elif last is None:
    save_last(latest)
    print("Prima esecuzione: salvo stato iniziale senza inviare notifica.")

elif latest["id"] != last.get("id"):
    send_telegram(build_message(latest))
    save_last(latest)
    print("Nuova circolare notificata.")

else:
    print("Nessuna nuova circolare.")
