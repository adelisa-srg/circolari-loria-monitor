import json
import os
import textwrap
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "https://www.icsmoiseloria.edu.it"

CIRCOLARI_URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"
NEWS_URL = "https://www.icsmoiseloria.edu.it/archivio-news"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://adelisa-srg.github.io/circolari-loria-monitor/")

STATE_FILE = "last_circolare.json"
NEWS_STATE_FILE = "last_news.json"
DASHBOARD_FILE = "docs/data/dashboard.json"
CARD_FILE = "school_update_card.png"


def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()) if text else ""


def fetch_soup(url):
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


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
    attachment_name = ""
    link = ""

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


def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def draw_wrapped(draw, text, xy, font, fill, max_width, line_spacing=8):
    x, y = xy
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing

    return y


def generate_card(circular, new_news):
    width, height = 1080, 1350
    img = Image.new("RGB", (width, height), "#07111f")
    draw = ImageDraw.Draw(img)

    # Background accents
    draw.ellipse((720, -160, 1240, 360), fill="#123b3c")
    draw.ellipse((-180, -160, 360, 320), fill="#113a45")

    font_title = get_font(58, bold=True)
    font_subtitle = get_font(28)
    font_section = get_font(34, bold=True)
    font_body = get_font(30, bold=True)
    font_small = get_font(24)
    font_tiny = get_font(21)

    white = "#F8FAFC"
    muted = "#A7B3C5"
    accent = "#3DDC97"
    cyan = "#38BDF8"
    card_bg = "#162438"
    border = "#26364F"

    x = 56
    y = 56

    # Header
    draw.rounded_rectangle((x, y, x + 72, y + 72), radius=22, fill="#31d3b1")
    draw.text((x + 17, y + 14), "📊", font=get_font(36), fill=white)
    draw.text((x + 94, y - 2), "Scuola Loria", font=font_title, fill=white)
    draw.text((x + 96, y + 62), "Aggiornamento automatico circolari e news", font=font_subtitle, fill=muted)

    now_label = datetime.now().strftime("%d/%m/%Y · %H:%M")
    draw.rounded_rectangle((width - 360, y + 10, width - 56, y + 58), radius=24, fill="#07382f", outline="#1c7e69", width=2)
    draw.text((width - 335, y + 20), f"● Monitor attivo · {now_label}", font=font_tiny, fill="#BBF7D0")

    y = 170

    # Main card
    draw.rounded_rectangle((56, y, width - 56, y + 430), radius=28, fill=card_bg, outline=border, width=2)
    draw.rounded_rectangle((90, y + 36, 328, y + 80), radius=22, fill="#07382f", outline="#1c7e69", width=2)
    draw.text((112, y + 44), "📢 CIRCOLARE", font=font_tiny, fill="#BBF7D0")

    yy = y + 110
    yy = draw_wrapped(
        draw,
        circular.get("title", "Titolo non disponibile"),
        (90, yy),
        font_body,
        white,
        max_width=880,
        line_spacing=10,
    )

    meta_y = y + 300
    meta_w = 285
    gap = 18
    meta = [
        ("🗓️ Data", circular.get("circular_date") or "N/D"),
        ("📌 Pubblicata", circular.get("published_date") or "N/D"),
        ("🏷️ Tipo", circular.get("tipologia") or "N/D"),
    ]

    for idx, (label, value) in enumerate(meta):
        xx = 90 + idx * (meta_w + gap)
        draw.rounded_rectangle((xx, meta_y, xx + meta_w, meta_y + 92), radius=18, fill="#0F1B2D", outline=border)
        draw.text((xx + 18, meta_y + 16), label, font=font_tiny, fill=muted)
        draw.text((xx + 18, meta_y + 50), value[:26], font=font_tiny, fill=white)

    y += 480

    # News card
    news_count = len(new_news)
    draw.text((56, y), f"📰 Nuove news: {news_count}", font=font_section, fill=white)
    y += 60

    draw.rounded_rectangle((56, y, width - 56, y + 500), radius=28, fill=card_bg, outline=border, width=2)

    if new_news:
        yy = y + 42
        for idx, item in enumerate(new_news[:5], start=1):
            draw.rounded_rectangle((90, yy, 150, yy + 42), radius=18, fill="#0B3550", outline="#156B8A")
            draw.text((109, yy + 8), str(idx), font=font_tiny, fill="#BAE6FD")

            yy = draw_wrapped(
                draw,
                item.get("title", "News senza titolo"),
                (172, yy + 2),
                font_small,
                white,
                max_width=780,
                line_spacing=6,
            )
            yy += 20
    else:
        draw.text((90, y + 52), "Nessuna nuova news in questo controllo.", font=font_small, fill=muted)

    # Footer
    footer_y = height - 125
    draw.rounded_rectangle((56, footer_y, width - 56, footer_y + 70), radius=24, fill="#092D38", outline="#1C5870")
    draw.text((90, footer_y + 20), "📊 Dashboard aggiornata · usa i pulsanti Telegram per aprire i dettagli", font=font_small, fill=cyan)

    img.save(CARD_FILE, quality=95)
    return CARD_FILE


def telegram_buttons(has_circular, has_news):
    rows = []

    first_row = [{"text": "📊 Dashboard", "url": DASHBOARD_URL}]
    if has_circular:
        first_row.append({"text": "📄 Circolare", "url": CIRCOLARI_URL})
    rows.append(first_row)

    rows.append([{"text": "📰 Archivio news", "url": NEWS_URL}])

    return rows


def build_digest_caption(has_circular, new_news):
    pieces = []

    pieces.append("📚 <b>AGGIORNAMENTO SCUOLA LORIA</b>")
    pieces.append("")
    pieces.append("━━━━━━━━━━━━━━━━━━━━")
    pieces.append("")

    if has_circular:
        pieces.append("📢 <b>Nuova circolare disponibile</b>")

    if new_news:
        pieces.append(f"📰 <b>{len(new_news)} nuova/e news rilevate</b>")

    pieces.append("")
    pieces.append("Usa i pulsanti qui sotto 👇")

    return "\n".join(pieces)


def send_telegram_photo(image_path, caption, buttons=None):
    if not TELEGRAM_TOKEN:
        raise Exception("TELEGRAM_TOKEN mancante")
    if not TELEGRAM_CHAT_ID:
        raise Exception("TELEGRAM_CHAT_ID mancante")

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
    }

    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})

    with open(image_path, "rb") as photo:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data=payload,
            files={"photo": photo},
            timeout=30,
        )

    print("Telegram photo status:", response.status_code)
    print("Telegram photo response:", response.text)
    response.raise_for_status()


def send_telegram_text(text, buttons=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json=payload,
        timeout=20,
    )

    print("Telegram text status:", response.status_code)
    print("Telegram text response:", response.text)
    response.raise_for_status()


def build_text_fallback(circular, has_circular, new_news):
    lines = [
        "📚 <b>AGGIORNAMENTO SCUOLA LORIA</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if has_circular:
        lines.extend([
            "📢 <b>NUOVA CIRCOLARE</b>",
            f"📄 <b>{circular.get('title')}</b>",
            f"🗓️ {circular.get('circular_date') or 'N/D'}",
            f"📌 {circular.get('published_date') or 'N/D'}",
            f"🏷️ {circular.get('tipologia') or 'N/D'}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ])

    if new_news:
        lines.append("📰 <b>NUOVE NEWS</b>")
        for idx, n in enumerate(new_news[:5], start=1):
            lines.append(f"{idx}. {n.get('title')}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    lines.append("Usa i pulsanti qui sotto 👇")
    return "\n".join(lines)


def main():
    circular = extract_latest_circular()
    news = extract_news()

    print("=== CIRCOLARE ===")
    print(json.dumps(circular, indent=2, ensure_ascii=False))

    print("=== NEWS ===")
    print(json.dumps(news, indent=2, ensure_ascii=False))

    prev_circular = load_json(STATE_FILE, {})
    prev_news = load_json(NEWS_STATE_FILE, [])

    has_new_circular = circular["id"] != prev_circular.get("id")

    prev_news_ids = [n["id"] for n in prev_news]
    new_news = [n for n in news if n["id"] not in prev_news_ids]

    should_notify = has_new_circular or bool(new_news)

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "circular": circular,
        "news": news,
    }

    save_json(DASHBOARD_FILE, dashboard)

    if should_notify:
        buttons = telegram_buttons(has_new_circular, bool(new_news))
        caption = build_digest_caption(has_new_circular, new_news)

        try:
            image_path = generate_card(circular, new_news)
            send_telegram_photo(image_path, caption, buttons)
            print("Digest grafico Telegram inviato.")
        except Exception as e:
            print(f"Errore generazione/invio card. Uso fallback testuale: {e}")
            send_telegram_text(build_text_fallback(circular, has_new_circular, new_news), buttons)

    else:
        print("Nessun aggiornamento da notificare.")

    save_json(STATE_FILE, circular)
    save_json(NEWS_STATE_FILE, news)


if __name__ == "__main__":
    main()
