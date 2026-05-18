import html
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import requests
import resend
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps


# =========================
# CONFIG
# =========================

BASE_URL = "https://www.icsmoiseloria.edu.it"

CIRCOLARI_URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"
NEWS_URL = "https://www.icsmoiseloria.edu.it/archivio-news"

DASHBOARD_URL = os.getenv(
    "DASHBOARD_URL",
    "https://adelisa-srg.github.io/circolari-loria-monitor/"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")

resend.api_key = RESEND_API_KEY

SCHOOL_NAME = "I.C.S Moisè Loria"

LOGO_FILE = "assets/logo.png"
LOGO_URL = os.getenv("LOGO_URL", "https://www.icsmoiseloria.edu.it/favicon.ico")

STATE_FILE = "last_circolare.json"
NEWS_STATE_FILE = "last_news.json"
DASHBOARD_FILE = "docs/data/dashboard.json"
CARD_FILE = "school_loria_card.png"

RESEND_FROM = "I.C.S Moisè Loria <notifiche@mail.aldevialabs.com>"


# =========================
# UTILS
# =========================

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
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def truncate(draw, text, font, max_width):
    if text_width(draw, text, font) <= max_width:
        return text

    while text and text_width(draw, text + "...", font) > max_width:
        text = text[:-1]

    return text.strip() + "..."


def wrap_lines(draw, text, font, max_width, max_lines=None):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate(draw, lines[-1], font, max_width)

    return lines


def rounded_rect(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_wrapped(draw, text, xy, font, fill, max_width, max_lines=None, spacing=8):
    x, y = xy
    lines = wrap_lines(draw, text, font, max_width, max_lines)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + spacing

    return y


def paste_rounded(base, img, box, radius):
    x1, y1, x2, y2 = box
    size = (x2 - x1, y2 - y1)

    img = ImageOps.fit(img, size, method=Image.LANCZOS).convert("RGBA")

    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)

    base.paste(img, (x1, y1), mask)


def load_logo(size=96):
    try:
        if os.path.exists(LOGO_FILE):
            print(f"Logo locale trovato: {LOGO_FILE}")
            img = Image.open(LOGO_FILE).convert("RGBA")
            return img.resize((size, size), Image.LANCZOS)
        else:
            print(f"Logo locale non trovato: {LOGO_FILE}")
    except Exception as e:
        print(f"Errore caricamento logo locale: {e}")

    try:
        print(f"Provo caricamento logo da URL: {LOGO_URL}")
        r = requests.get(LOGO_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        return img.resize((size, size), Image.LANCZOS)
    except Exception as e:
        print(f"Errore caricamento logo URL: {e}")

    img = Image.new("RGBA", (size, size), (52, 211, 153, 255))
    d = ImageDraw.Draw(img)
    d.text((size // 2 - 14, size // 2 - 24), "L", font=get_font(42, True), fill="#04111f")
    return img


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

    raw_text = card.get_text("\n", strip=True)
    lines = [normalize(line) for line in raw_text.split("\n") if normalize(line)]

    title = ""
    circular_date = ""
    published_date = ""
    tipologia = ""
    attachment_name = ""
    link = ""

    for i, line in enumerate(lines):
        if line.startswith("Circolare del"):
            circular_date = normalize(line.replace("Circolare del", ""))
            if i + 1 < len(lines):
                title = lines[i + 1]

        elif line.startswith("Pubblicato il:"):
            value = normalize(line.replace("Pubblicato il:", ""))
            published_date = value or (lines[i + 1] if i + 1 < len(lines) else "")

        elif line.startswith("Tipologia:"):
            value = normalize(line.replace("Tipologia:", ""))
            tipologia = value or (lines[i + 1] if i + 1 < len(lines) else "")

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


# =========================
# CARD TELEGRAM
# =========================

def generate_card(circular, new_news):
    width, height = 1080, 1600

    bg = Image.new("RGB", (width, height), "#06101d")
    draw = ImageDraw.Draw(bg)

    blobs = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    b = ImageDraw.Draw(blobs)
    b.ellipse((-240, -180, 450, 430), fill=(20, 184, 166, 95))
    b.ellipse((700, -220, 1330, 420), fill=(34, 197, 94, 80))
    b.ellipse((640, 680, 1290, 1400), fill=(56, 189, 248, 55))
    b.ellipse((-250, 940, 420, 1700), fill=(16, 185, 129, 45))
    blobs = blobs.filter(ImageFilter.GaussianBlur(80))
    bg = Image.alpha_composite(bg.convert("RGBA"), blobs).convert("RGB")
    draw = ImageDraw.Draw(bg)

    for i in range(0, width, 26):
        for j in range(0, height, 26):
            if (i + j) % 78 == 0:
                draw.point((i, j), fill="#102034")

    white = "#F8FAFC"
    muted = "#A7B3C5"
    muted_dark = "#718096"
    green = "#4ADE80"
    cyan = "#38BDF8"
    cyan_soft = "#0B3550"
    panel = "#101D30"
    panel_soft = "#0B1628"
    border = "#2B3E58"
    border_green = "#23C783"

    font_hero = get_font(44, True)
    font_sub = get_font(27)
    font_title = get_font(36, True)
    font_section = get_font(34, True)
    font_body = get_font(26, True)
    font_regular = get_font(24)
    font_small = get_font(20)
    font_tiny = get_font(17)

    rounded_rect(draw, (36, 36, width - 36, height - 36), 46, "#06101d", "#145c46", 3)

    x = 78
    y = 82

    rounded_rect(draw, (x, y, x + 104, y + 104), 30, "#12362f", "#39E6A4", 2)
    logo = load_logo(86)
    paste_rounded(bg, logo, (x + 9, y + 9, x + 95, y + 95), 22)
    draw = ImageDraw.Draw(bg)

    title_x = x + 132
    title_y = y - 2
    max_title_width = 560

    title_lines = wrap_lines(draw, SCHOOL_NAME, font_hero, max_title_width, max_lines=2)
    current_y = title_y
    for line in title_lines:
        draw.text((title_x, current_y), line, font=font_hero, fill=white)
        current_y += 50

    draw.text((title_x, y + 82), "Monitor automatico", font=get_font(29), fill=green)
    draw.text((title_x, y + 120), "Circolari e News", font=font_sub, fill=muted)

    now_label = datetime.now().strftime("%d/%m/%Y · %H:%M")
    pill_x = width - 388
    pill_y = y + 122

    rounded_rect(draw, (pill_x, pill_y, width - 78, pill_y + 58), 28, "#0B2D26", "#29966F", 2)
    draw.ellipse((pill_x + 22, pill_y + 21, pill_x + 36, pill_y + 35), fill=green)
    draw.text((pill_x + 50, pill_y + 17), "MONITOR ATTIVO", font=font_small, fill="#BBF7D0")
    draw.text((pill_x + 6, pill_y + 72), now_label, font=font_small, fill=muted)

    y = 300

    rounded_rect(draw, (70, y, width - 70, y + 455), 34, panel, border, 2)

    highlight = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle((82, y + 10, width - 82, y + 445), 30, outline=(255, 255, 255, 24), width=1)
    bg = Image.alpha_composite(bg.convert("RGBA"), highlight).convert("RGB")
    draw = ImageDraw.Draw(bg)

    rounded_rect(draw, (112, y + 34, 322, y + 82), 24, "#0B2F29", border_green, 2)
    draw.text((142, y + 46), "CIRCOLARE", font=font_tiny, fill="#BFF7D2")

    draw.text((112, y + 116), "NUOVA CIRCOLARE", font=font_small, fill=green)

    draw_wrapped(
        draw,
        circular.get("title", "Titolo non disponibile"),
        (112, y + 158),
        font_title,
        white,
        max_width=850,
        max_lines=3,
        spacing=8,
    )

    meta_y = y + 330
    meta_w = 280
    gap = 22

    meta = [
        ("DATA CIRCOLARE", circular.get("circular_date") or "N/D"),
        ("PUBBLICATA IL", circular.get("published_date") or "N/D"),
        ("TIPOLOGIA", circular.get("tipologia") or "N/D"),
    ]

    for idx, (label, value) in enumerate(meta):
        xx = 112 + idx * (meta_w + gap)
        rounded_rect(draw, (xx, meta_y, xx + meta_w, meta_y + 96), 20, panel_soft, border, 1)
        draw.text((xx + 22, meta_y + 18), label, font=font_tiny, fill=muted)
        draw.text(
            (xx + 22, meta_y + 52),
            truncate(draw, value, font_regular, meta_w - 44),
            font=font_regular,
            fill=white,
        )

    y += 525

    visible_news = new_news[:5]
    news_count = len(new_news)

    draw.text((78, y), "News", font=font_section, fill=white)

    if news_count > 0:
        badge_text = f"+{news_count} NEWS"
        bx = width - 310
        by = y - 10

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.rounded_rectangle((bx - 20, by - 18, bx + 230, by + 82), 42, fill=(74, 222, 128, 90))
        glow = glow.filter(ImageFilter.GaussianBlur(20))
        bg = Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(bg)

        rounded_rect(draw, (bx, by, bx + 208, by + 64), 32, "#102E24", green, 2)
        draw.text((bx + 34, by + 17), badge_text, font=get_font(24, True), fill="#BBF7D0")

    y += 72

    news_top = y
    news_h = 500
    rounded_rect(draw, (70, news_top, width - 70, news_top + news_h), 34, panel, border, 2)

    if visible_news:
        yy = news_top + 44
        draw.text((112, yy), "NUOVE NEWS RILEVATE", font=font_small, fill=cyan)
        yy += 58

        for idx, item in enumerate(visible_news, start=1):
            rounded_rect(draw, (112, yy, 160, yy + 48), 24, cyan_soft, "#156B8A", 1)
            draw.text((130, yy + 10), str(idx), font=font_tiny, fill="#BAE6FD")

            yy = draw_wrapped(
                draw,
                item.get("title", "News senza titolo"),
                (184, yy + 2),
                font_regular,
                white,
                max_width=760,
                max_lines=2,
                spacing=5,
            )
            yy += 28
    else:
        yy = news_top + 90
        draw.text((112, yy), "Sistema aggiornato", font=font_body, fill=white)
        draw.text((112, yy + 48), "Nessuna nuova news rilevata in questo controllo.", font=font_regular, fill=muted)
        draw.line((112, yy + 124, width - 112, yy + 124), fill=border, width=2)
        draw.text((112, yy + 160), "La dashboard resta disponibile per consultare lo storico recente.", font=font_small, fill=muted_dark)

    y = news_top + news_h + 42

    rounded_rect(draw, (70, y, width - 70, y + 128), 30, "#0B2C26", "#1B8A68", 2)
    draw.text((112, y + 30), "Dashboard aggiornata", font=font_body, fill=white)
    draw.text((112, y + 75), "Dati sincronizzati e disponibili online.", font=font_regular, fill=muted)

    rounded_rect(draw, (width - 260, y + 34, width - 112, y + 94), 20, "#0E382B", green, 1)
    draw.line((width - 226, y + 76, width - 204, y + 54), fill=green, width=5)
    draw.line((width - 204, y + 54, width - 180, y + 66), fill=green, width=5)
    draw.line((width - 180, y + 66, width - 148, y + 36), fill=green, width=5)

    bg.save(CARD_FILE, quality=95)
    return CARD_FILE


# =========================
# TELEGRAM
# =========================

def telegram_buttons(has_circular):
    first_row = [{"text": "📊 Dashboard", "url": DASHBOARD_URL}]

    if has_circular:
        first_row.append({"text": "📄 Circolare", "url": CIRCOLARI_URL})

    return [
        first_row,
        [{"text": "📰 Archivio news", "url": NEWS_URL}],
    ]


def build_summary_message(has_circular, circular, new_news):
    lines = [
        "🚀 <b>AGGIORNAMENTO I.C.S MOISÈ LORIA</b>",
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
# EMAIL RESEND
# =========================

def esc(value):
    return html.escape(str(value or ""))


def build_email_html(has_circular, circular, new_news):
    news_items = ""

    for idx, item in enumerate(new_news[:5], start=1):
        title = esc(item.get("title"))
        link = esc(item.get("link"))

        news_items += f"""
        <tr>
          <td style="padding:14px 0;border-bottom:1px solid rgba(148,163,184,.16);">
            <div style="font-size:15px;line-height:1.35;color:#f8fafc;font-weight:700;">
              {idx}. {title}
            </div>
            <div style="margin-top:7px;">
              <a href="{link}" style="color:#38BDF8;text-decoration:none;font-size:13px;font-weight:700;">
                Apri news
              </a>
            </div>
          </td>
        </tr>
        """

    if not news_items:
        news_items = """
        <tr>
          <td style="padding:14px 0;color:#94a3b8;">
            Nessuna nuova news rilevata in questo controllo.
          </td>
        </tr>
        """

    circular_block = ""

    if has_circular:
        circular_block = f"""
        <div style="margin-top:24px;padding:22px;border-radius:22px;background:rgba(16,29,48,.92);border:1px solid rgba(148,163,184,.18);">
          <div style="display:inline-block;padding:7px 12px;border-radius:999px;background:#0B2F29;border:1px solid #23C783;color:#BBF7D0;font-size:12px;font-weight:800;letter-spacing:.06em;">
            CIRCOLARE
          </div>

          <h2 style="margin:18px 0 10px;color:#f8fafc;font-size:22px;line-height:1.25;">
            {esc(circular.get("title"))}
          </h2>

          <p style="margin:0;color:#a7b3c5;font-size:15px;line-height:1.7;">
            <b style="color:#f8fafc;">Data circolare:</b> {esc(circular.get("circular_date") or "N/D")}<br>
            <b style="color:#f8fafc;">Pubblicata il:</b> {esc(circular.get("published_date") or "N/D")}<br>
            <b style="color:#f8fafc;">Tipologia:</b> {esc(circular.get("tipologia") or "N/D")}
          </p>

          <div style="margin-top:18px;">
            <a href="{esc(circular.get("link"))}" style="display:inline-block;background:#4ADE80;color:#06101d;padding:12px 16px;border-radius:12px;text-decoration:none;font-weight:900;">
              Apri circolare
            </a>
          </div>
        </div>
        """

    return f"""
    <!doctype html>
    <html>
    <body style="margin:0;padding:0;background:#06101d;font-family:Arial,Helvetica,sans-serif;color:#f8fafc;">
      <div style="padding:36px 16px;background:radial-gradient(circle at top left,rgba(20,184,166,.25),transparent 35%),radial-gradient(circle at top right,rgba(34,197,94,.22),transparent 34%),#06101d;">
        <div style="max-width:720px;margin:0 auto;border-radius:28px;background:rgba(15,29,48,.94);border:1px solid rgba(74,222,128,.28);overflow:hidden;box-shadow:0 28px 70px rgba(0,0,0,.35);">

          <div style="padding:30px 30px 18px;">
            <div style="display:inline-block;padding:9px 14px;border-radius:999px;background:#0B2D26;border:1px solid #29966F;color:#BBF7D0;font-size:13px;font-weight:900;">
              ● MONITOR ATTIVO
            </div>

            <h1 style="margin:22px 0 6px;color:#f8fafc;font-size:34px;letter-spacing:-.04em;">
              {SCHOOL_NAME}
            </h1>

            <p style="margin:0;color:#a7b3c5;font-size:16px;">
              Aggiornamento automatico circolari e news
            </p>

            {circular_block}

            <div style="margin-top:24px;padding:22px;border-radius:22px;background:rgba(16,29,48,.92);border:1px solid rgba(148,163,184,.18);">
              <div>
                <h2 style="margin:0;color:#f8fafc;font-size:22px;">News</h2>
                <div style="display:inline-block;margin-top:10px;background:#102E24;border:1px solid #4ADE80;color:#BBF7D0;padding:8px 12px;border-radius:999px;font-weight:900;">
                  +{len(new_news)} NEWS
                </div>
              </div>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px;">
                {news_items}
              </table>
            </div>

            <div style="margin-top:28px;text-align:center;">
              <a href="{esc(DASHBOARD_URL)}" style="display:inline-block;background:linear-gradient(135deg,#4ADE80,#38BDF8);color:#06101d;padding:14px 22px;border-radius:14px;text-decoration:none;font-weight:900;">
                Apri dashboard scuola
              </a>
            </div>

            <p style="margin:28px 0 0;color:#718096;font-size:12px;text-align:center;">
              Generato automaticamente da GitHub Actions · Telegram Bot · Resend
            </p>
          </div>

        </div>
      </div>
    </body>
    </html>
    """


def send_email(has_circular, circular, new_news):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY mancante: salto invio email.")
        return

    if not EMAIL_TO:
        print("EMAIL_TO mancante: salto invio email.")
        return

    recipients = [email.strip() for email in EMAIL_TO.split(",") if email.strip()]

    if not recipients:
        print("EMAIL_TO valorizzato ma nessun destinatario valido: salto invio email.")
        return

    payload = {
        "from": RESEND_FROM,
        "to": recipients,
        "subject": "Aggiornamento I.C.S Moisè Loria",
        "html": build_email_html(has_circular, circular, new_news),
    }

    print("Invio email Resend...")
    print(f"Mittente email: {RESEND_FROM}")
    print(f"Destinatari email: {recipients}")

    try:
        response = resend.Emails.send(payload)
        print("Resend response:", response)
    except Exception as e:
        print("Errore invio email Resend:", repr(e))
        raise


# =========================
# MAIN
# =========================

def main():
    print("=== CONFIG CHECK ===")
    print("TELEGRAM_TOKEN presente:", bool(TELEGRAM_TOKEN))
    print("TELEGRAM_CHAT_ID presente:", bool(TELEGRAM_CHAT_ID))
    print("RESEND_API_KEY presente:", bool(RESEND_API_KEY))
    print("EMAIL_TO presente:", bool(EMAIL_TO))
    print("RESEND_FROM:", RESEND_FROM)
    print("LOGO_FILE:", LOGO_FILE)
    print("LOGO_FILE exists:", os.path.exists(LOGO_FILE))

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

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "circular": circular,
        "news": news,
    }

    save_json(DASHBOARD_FILE, dashboard)

    if has_new_circular or new_news:
        image_path = generate_card(circular, new_news)
        send_telegram_photo(image_path)

        summary = build_summary_message(has_new_circular, circular, new_news)
        send_telegram_text(summary, telegram_buttons(has_new_circular))

        send_email(has_new_circular, circular, new_news)

        print("Aggiornamento Telegram + Email completato.")
    else:
        print("Nessun aggiornamento da notificare.")

    save_json(STATE_FILE, circular)
    save_json(NEWS_STATE_FILE, news)


if __name__ == "__main__":
    main()
