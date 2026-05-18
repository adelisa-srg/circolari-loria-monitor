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


# =========================
# SCRAPING CIRCOLARI
# =========================

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


# =========================
# SCRAPING NEWS
# =========================

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


# =========================
# FONT / DRAW HELPERS
# =========================

def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def truncate_text(draw, text, font, max_width):
    if text_width(draw, text, font) <= max_width:
        return text

    ellipsis = "..."
    while text and text_width(draw, text + ellipsis, font) > max_width:
        text = text[:-1]

    return text.strip() + ellipsis


def draw_wrapped(draw, text, xy, font, fill, max_width, max_lines=None, line_spacing=8):
    x, y = xy
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        if text_width(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate_text(draw, lines[-1], font, max_width)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing

    return y


def rounded_panel(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# =========================
# CARD GRAFICA PRO
# =========================

def generate_card(circular, new_news):
    width, height = 1080, 1350
    img = Image.new("RGB", (width, height), "#06101D")
    draw = ImageDraw.Draw(img)

    # palette
    bg = "#06101D"
    panel = "#111E31"
    panel_2 = "#0C1728"
    panel_3 = "#0A1423"
    border = "#24354D"
    border_green = "#22C55E"
    green = "#4ADE80"
    green_soft = "#0D3B2F"
    cyan = "#38BDF8"
    cyan_soft = "#0B3550"
    white = "#F8FAFC"
    muted = "#A7B3C5"
    muted_2 = "#7C8AA0"

    # fonts
    font_hero = get_font(58, bold=True)
    font_title = get_font(42, bold=True)
    font_section = get_font(34, bold=True)
    font_body = get_font(28, bold=True)
    font_normal = get_font(25)
    font_small = get_font(22)
    font_tiny = get_font(18)
    font_badge = get_font(24, bold=True)

    # background glow
    draw.ellipse((-240, -220, 430, 390), fill="#0B3B42")
    draw.ellipse((650, -240, 1290, 420), fill="#0B3A32")
    draw.ellipse((760, 650, 1270, 1220), fill="#071F2E")

    # outer border
    rounded_panel(draw, (38, 38, width - 38, height - 38), 42, bg, "#105E46", 3)

    x = 78
    y = 82

    # logo
    rounded_panel(draw, (x, y, x + 82, y + 82), 24, "#34D399", "#74F7C5", 2)
    draw.text((x + 28, y + 23), "L", font=get_font(34, bold=True), fill="#042116")

    draw.text((x + 108, y - 3), "Scuola Loria", font=font_hero, fill=white)
    draw.text((x + 112, y + 61), "Monitor automatico", font=get_font(30), fill=green)
    draw.text((x + 112, y + 101), "Circolari e News", font=get_font(28), fill=muted)

    today_label = datetime.now().strftime("%d/%m/%Y · %H:%M")
    pill_x = width - 395
    pill_y = y + 12
    rounded_panel(draw, (pill_x, pill_y, width - 78, pill_y + 58), 26, "#0B2C26", "#2F9D74", 2)
    draw.ellipse((pill_x + 22, pill_y + 21, pill_x + 36, pill_y + 35), fill=green)
    draw.text((pill_x + 48, pill_y + 16), "MONITOR ATTIVO", font=font_small, fill="#BBF7D0")
    draw.text((pill_x, pill_y + 72), today_label, font=font_small, fill=muted)

    y = 235

    # main circular panel
    rounded_panel(draw, (78, y, width - 78, y + 430), 30, panel, border, 2)

    # badge circolare
    rounded_panel(draw, (116, y + 32, 318, y + 78), 22, "#0B2F29", "#20B678", 2)
    draw.text((140, y + 43), "CIRCOLARE", font=font_tiny, fill="#BBF7D0")

    # decorative document icon
    icon_x = width - 290
    icon_y = y + 72
    draw.ellipse((icon_x, icon_y, icon_x + 150, icon_y + 150), outline=green, width=4)
    draw.rectangle((icon_x + 52, icon_y + 42, icon_x + 101, icon_y + 108), outline=green, width=4)
    draw.line((icon_x + 64, icon_y + 66, icon_x + 90, icon_y + 66), fill=green, width=3)
    draw.line((icon_x + 64, icon_y + 82, icon_x + 90, icon_y + 82), fill=green, width=3)
    rounded_panel(draw, (icon_x + 90, icon_y + 118, icon_x + 168, icon_y + 158), 20, "#16803E", "#7DF29B", 1)
    draw.text((icon_x + 111, icon_y + 126), "NUOVA", font=font_tiny, fill="#DCFCE7")

    # title
    title = circular.get("title", "Titolo non disponibile")
    draw.text((116, y + 115), "NUOVA CIRCOLARE", font=font_small, fill=green)
    draw_wrapped(
        draw,
        title,
        (116, y + 155),
        font_title,
        white,
        max_width=720,
        max_lines=3,
        line_spacing=10,
    )

    # meta boxes
    meta_y = y + 305
    meta_w = 280
    gap = 20
    meta = [
        ("DATA CIRCOLARE", circular.get("circular_date") or "N/D"),
        ("PUBBLICATA IL", circular.get("published_date") or "N/D"),
        ("TIPOLOGIA", circular.get("tipologia") or "N/D"),
    ]

    for idx, (label, value) in enumerate(meta):
        xx = 116 + idx * (meta_w + gap)
        rounded_panel(draw, (xx, meta_y, xx + meta_w, meta_y + 95), 18, panel_2, border, 1)
        draw.text((xx + 22, meta_y + 18), label, font=font_tiny, fill=muted)
        value_text = truncate_text(draw, value, font_normal, meta_w - 44)
        draw.text((xx + 22, meta_y + 50), value_text, font=font_normal, fill=white)

    y += 485

    # news header
    news_count = len(new_news)
    draw.text((78, y), "NEWS", font=font_section, fill=white)

    if news_count > 0:
        badge_text = f"+{news_count} NEWS"
        bx = width - 300
        by = y - 10

        # glow
        draw.rounded_rectangle((bx - 8, by - 8, bx + 216, by + 68), radius=34, fill="#0B2F22")
        draw.rounded_rectangle((bx, by, bx + 200, by + 60), radius=30, fill="#102E24", outline=green, width=2)
        draw.text((bx + 32, by + 15), badge_text, font=font_badge, fill="#86EFAC")

    y += 60

    # news panel
    rounded_panel(draw, (78, y, width - 78, y + 390), 30, panel, border, 2)

    if new_news:
        yy = y + 42
        draw.text((116, yy), "NUOVE NEWS RILEVATE", font=font_small, fill=cyan)
        yy += 52

        for idx, item in enumerate(new_news[:5], start=1):
            rounded_panel(draw, (116, yy, 160, yy + 44), 22, cyan_soft, "#156B8A", 1)
            draw.text((131, yy + 8), str(idx), font=font_tiny, fill="#BAE6FD")

            draw_wrapped(
                draw,
                item.get("title", "News senza titolo"),
                (184, yy + 2),
                font_normal,
                white,
                max_width=760,
                max_lines=2,
                line_spacing=5,
            )
            yy += 66
    else:
        yy = y + 70
        draw.text((116, yy), "Sistema aggiornato", font=font_body, fill=white)
        draw.text((116, yy + 45), "Nessuna nuova news rilevata in questo controllo.", font=font_normal, fill=muted)
        draw.line((116, yy + 105, width - 116, yy + 105), fill=border, width=2)
        draw.text((116, yy + 140), "La dashboard resta disponibile per consultare lo storico recente.", font=font_small, fill=muted_2)

    y += 440

    # footer panel
    rounded_panel(draw, (78, y, width - 78, y + 105), 26, "#0B2C26", "#1B8A68", 2)
    draw.text((116, y + 25), "Dashboard aggiornata", font=font_body, fill=white)
    draw.text((116, y + 62), "Tutti i dati sono sincronizzati e disponibili online.", font=font_small, fill=muted)
    rounded_panel(draw, (width - 245, y + 25, width - 116, y + 80), 18, "#0E382B", "#4ADE80", 1)
    draw.line((width - 213, y + 62, width - 195, y + 44), fill=green, width=4)
    draw.line((width - 195, y + 44, width - 175, y + 55), fill=green, width=4)
    draw.line((width - 175, y + 55, width - 150, y + 30), fill=green, width=4)

    img.save(CARD_FILE, quality=95)
    return CARD_FILE


# =========================
# TELEGRAM
# =========================

def telegram_buttons(has_circular, has_news):
    rows = []

    first_row = [{"text": "📊 Dashboard", "url": DASHBOARD_URL}]

    if has_circular:
        first_row.append({"text": "📄 Circolare", "url": CIRCOLARI_URL})

    rows.append(first_row)
    rows.append([{"text": "📰 Archivio news", "url": NEWS_URL}])

    return rows


def build_summary_message(has_circular, circular, new_news):
    lines = [
        "🚀 <b>AGGIORNAMENTO SCUOLA LORIA</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if has_circular:
        lines.extend([
            "",
            "📢 <b>Nuova circolare</b>",
            f"📄 {circular.get('title', '')[:95]}",
            f"🗓️ {circular.get('circular_date') or 'N/D'}",
            f"🏷️ {circular.get('tipologia') or 'N/D'}",
        ])

    if new_news:
        lines.extend([
            "",
            f"📰 <b>{len(new_news)} nuova/e news rilevate</b>",
        ])

        for idx, n in enumerate(new_news[:5], start=1):
            lines.append(f"{idx}. {n.get('title', '')[:75]}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "👇 Apri i dettagli dai pulsanti qui sotto",
    ])

    return "\n".join(lines)


def send_telegram_photo(image_path):
    if not TELEGRAM_TOKEN:
        raise Exception("TELEGRAM_TOKEN mancante")
    if not TELEGRAM_CHAT_ID:
        raise Exception("TELEGRAM_CHAT_ID mancante")

    with open(image_path, "rb") as photo:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID},
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


# =========================
# MAIN
# =========================

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

        # 1. Card grafica
        try:
            image_path = generate_card(circular, new_news)
            send_telegram_photo(image_path)
            print("Card grafica Telegram inviata.")
        except Exception as e:
            print(f"Errore card grafica: {e}")

        # 2. Sintesi testuale con bottoni
        summary = build_summary_message(has_new_circular, circular, new_news)
        send_telegram_text(summary, buttons)
        print("Sintesi Telegram inviata.")
    else:
        print("Nessun aggiornamento da notificare.")

    save_json(STATE_FILE, circular)
    save_json(NEWS_STATE_FILE, news)


if __name__ == "__main__":
    main()
