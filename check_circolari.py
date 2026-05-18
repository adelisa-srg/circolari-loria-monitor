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
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "false").lower() == "true"

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


def find_latest_card(soup):
    marker = soup.find(string=lambda t: t and "Circolare del" in t)

    if not marker:
        raise Exception("Nessuna circolare trovata: marker 'Circolare del' assente")

    card = marker.parent

    for _ in range(15):
        if not card:
            break

        text = card.get_text(" ", strip=True)

        if (
            "Pubblicato il:" in text
            and "Tipologia:" in text
            and "Allegati:" in text
        ):
            return card

        card = card.parent

    raise Exception("Card circolare trovata, ma struttura HTML non riconosciuta")


def extract_label_value(full_text, label):
    """
    Estrae valori tipo:
    Pubblicato il: 18/05/2026
    Tipologia: Tutto il personale, Riservata
    anche se HTML mette label e valore su nodi diversi.
    """
    pattern = rf"{re.escape(label)}\s*([^\n]+)"
    match = re.search(pattern, full_text, re.IGNORECASE)

    if match:
        return normalize(match.group(1))

    return ""


def get_latest():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    card = find_latest_card(soup)

    full_text = card.get_text("\n", strip=True)
    full_text = full_text.replace("\xa0", " ")

    lines = [normalize(line) for line in full_text.split("\n") if normalize(line)]

    print("=== DEBUG LINES ===")
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

        if line.startswith("Pubblicato il:"):
            published_date = normalize(line.replace("Pubblicato il:", ""))

        if line.startswith("Tipologia:"):
            tipologia = normalize(line.replace("Tipologia:", ""))

    if not published_date:
        published_date = extract_label_value(full_text, "Pubblicato il:")

    if not tipologia:
        tipologia = extract_label_value(full_text, "Tipologia:")

    # Se il titolo per qualche motivo non è stato preso dalla riga successiva
    if not title:
        for line in lines:
            if "CIRCOLARE" in line.upper() and not line.startswith("Circolare del"):
                title = line
                break

    links = card.find_all("a", href=True)

    pdf_candidates = []

    for a in links:
        href = a.get("href", "")
        link_text = normalize(a.get_text(" ", strip=True))
        absolute_link = urljoin(BASE_URL, href)

        if ".pdf" in href.lower() or ".pdf" in link_text.lower():
            pdf_candidates.append(
                {
                    "text": link_text,
                    "href": href,
                    "absolute_link": absolute_link,
                }
            )

    if pdf_candidates:
        # Preferisce il link con testo leggibile, non solo id numerico
        readable = [
            c for c in pdf_candidates
            if c["text"] and not re.fullmatch(r"\d+\.pdf", c["text"].strip(), re.IGNORECASE)
        ]

        chosen = readable[0] if readable else pdf_candidates[0]

        attachment_name = chosen["text"] or chosen["href"].split("/")[-1]
        attachment_link = chosen["absolute_link"]

    else:
        # fallback: prova a leggere il nome allegato dalle righe dopo "Allegati:"
        for i, line in enumerate(lines):
            if line.startswith("Allegati:") and i + 1 < len(lines):
                attachment_name = lines[i + 1]
                break

        first_link = links[0] if links else None
        if first_link:
            attachment_link = urljoin(BASE_URL, first_link.get("href", ""))

    if not title:
        raise Exception("Titolo circolare non estratto")

    if not attachment_link:
        raise Exception("Link allegato/circolare non estratto")

    return {
        "id": attachment_link,
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

📄 <b>{latest.get("title") or "Titolo non disponibile"}</b>

🗓️ <b>Data circolare:</b> {latest.get("circular_date") or "N/D"}
📌 <b>Pubblicata il:</b> {latest.get("published_date") or "N/D"}
🏷️ <b>Tipologia:</b> {latest.get("tipologia") or "N/D"}

📎 <b>Allegato:</b>
{latest.get("attachment_name") or "N/D"}

👉 <a href="{latest.get("link")}">Apri documento</a>
"""


def main():
    latest = get_latest()

    print("=== Ultima circolare estratta ===")
    print(json.dumps(latest, ensure_ascii=False, indent=2))

    last = load_last()

    if FORCE_NOTIFY:
        print("FORCE_NOTIFY=true: invio notifica forzata")
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


if __name__ == "__main__":
    main()
