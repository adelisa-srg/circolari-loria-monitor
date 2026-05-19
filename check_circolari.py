import hashlib
import html
import json
import os
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
import resend
from bs4 import BeautifulSoup


# =========================
# CONFIG
# =========================

BASE_URL = "https://www.icsmoiseloria.edu.it"

CIRCOLARI_URL = "https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on"
NEWS_URL = "https://www.icsmoiseloria.edu.it/archivio-news"

COMUNE_MILANO_URL = "https://www.comune.milano.it/servizi/scuola/pre-scuola-e-giochi-serali-scuole-primarie"
COMUNE_TITLE = "Pre-scuola e giochi serali - Scuole primarie"

DASHBOARD_URL = os.getenv(
    "DASHBOARD_URL",
    "https://adelisa-srg.github.io/circolari-loria-monitor/"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_EXTRA_TO = os.getenv("EMAIL_EXTRA_TO", "tittytraversa@libero.it")

resend.api_key = RESEND_API_KEY

IFTTT_KEY = os.getenv("IFTTT_KEY")
IFTTT_EVENT = "school_loria_update"

SCHOOL_NAME = "I.C.S Moisè Loria"

STATE_FILE = "last_circolare.json"
NEWS_STATE_FILE = "last_news.json"
COMUNE_STATE_FILE = "last_comune_milano.json"

DASHBOARD_FILE = "docs/data/dashboard.json"

RESEND_FROM = "I.C.S Moisè Loria <notifiche@mail.aldevialabs.com>"


# =========================
# UTILS
# =========================

def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()) if text else ""


def esc(value):
    return html.escape(str(value or ""))


def fetch_soup(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        },
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


def unique_list(values):
    result = []
    seen = set()

    for value in values:
        if not value:
            continue

        item = value.strip()

        if not item:
            continue

        key = item.lower()

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


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
# MONITOR COMUNE MILANO
# =========================

def extract_comune_milano_state():
    soup = fetch_soup(COMUNE_MILANO_URL)

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    main = (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find("article")
        or soup.body
        or soup
    )

    text = normalize(main.get_text(" ", strip=True))

    noise_tokens = [
        "cookie",
        "privacy",
        "preferenze",
        "accessibilità",
        "menu",
        "cerca",
        "accedi",
        "login",
        "facebook",
        "twitter",
        "linkedin",
        "instagram",
    ]

    words = []

    for word in text.split():
        if word.lower() not in noise_tokens:
            words.append(word)

    clean_text = normalize(" ".join(words))

    if len(clean_text) < 200:
        raise Exception("Contenuto Comune Milano troppo corto: possibile pagina non caricata correttamente")

    content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

    return {
        "id": content_hash,
        "type": "external_page",
        "source": "Comune di Milano",
        "title": COMUNE_TITLE,
        "url": COMUNE_MILANO_URL,
        "hash": content_hash,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preview": clean_text[:700],
    }


# =========================
# TELEGRAM - SOLO TESTO
# =========================

def telegram_buttons(has_circular, has_comune_update=False):
    rows = []

    main_row = [{"text": "📊 Dashboard", "url": DASHBOARD_URL}]

    if has_circular:
        main_row.append({"text": "📄 Circolare", "url": CIRCOLARI_URL})

    rows.append(main_row)
    rows.append([{"text": "📰 News scuola", "url": NEWS_URL}])

    if has_comune_update:
        rows.append([{"text": "🏛️ Comune Milano", "url": COMUNE_MILANO_URL}])

    return rows


def build_telegram_message(has_circular, circular, new_news, has_comune_update, comune_state):
    now_label = datetime.now().strftime("%d/%m/%Y · %H:%M")

    lines = [
        "🚀 <b>Monitor Scuola aggiornato</b>",
        f"🕒 {now_label}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if has_circular:
        lines.extend([
            "",
            "📄 <b>Nuova circolare</b>",
            f"<b>{esc(circular.get('title'))}</b>",
            "",
            f"🗓️ Data: {esc(circular.get('circular_date') or 'N/D')}",
            f"🏷️ Tipologia: {esc(circular.get('tipologia') or 'N/D')}",
        ])

    if new_news:
        lines.extend([
            "",
            f"📰 <b>{len(new_news)} nuova/e news scuola</b>",
        ])

        for idx, item in enumerate(new_news[:5], start=1):
            lines.append(f"{idx}. {esc(item.get('title'))[:90]}")

    if has_comune_update and comune_state:
        lines.extend([
            "",
            "🏛️ <b>Comune di Milano aggiornato</b>",
            f"📌 {esc(COMUNE_TITLE)}",
            "⚠️ Controlla subito eventuali scadenze o avvisi.",
        ])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "👇 Apri i dettagli dai pulsanti qui sotto",
    ])

    return "\n".join(lines)


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
# WHATSAPP VIA IFTTT - PREMIUM BREVE / OPZIONALE
# =========================

def build_whatsapp_title(has_circular, new_news, has_comune_update):
    if has_comune_update:
        return "🏛️ Alert Comune Milano"

    if has_circular:
        return "📄 Nuova circolare Loria"

    if new_news:
        return "📰 News I.C.S. Loria"

    return "🚀 Monitor Scuola"


def build_whatsapp_message(has_circular, circular, new_news, has_comune_update):
    lines = []

    if has_circular:
        title = circular.get("title", "")
        date = circular.get("circular_date") or "N/D"

        lines.extend([
            "Aggiornamento rilevato ✅",
            "",
            f"📄 {title[:180]}",
            f"🗓️ {date}",
        ])

    if new_news:
        lines.extend([
            "",
            f"📰 {len(new_news)} nuova/e news",
        ])

        for idx, item in enumerate(new_news[:3], start=1):
            lines.append(f"{idx}. {item.get('title', '')[:80]}")

    if has_comune_update:
        lines.extend([
            "Aggiornamento rilevato ✅",
            "",
            "🏛️ Comune di Milano",
            "Pre-scuola e giochi serali",
            "",
            "Verifica eventuali scadenze o avvisi.",
        ])

    if not lines:
        lines.append("Monitor aggiornato ✅")

    return "\n".join(lines).strip()


def build_whatsapp_url(has_circular, circular, has_comune_update):
    if has_comune_update:
        return COMUNE_MILANO_URL

    if has_circular and circular.get("link"):
        return circular["link"]

    return DASHBOARD_URL


def send_ifttt_whatsapp(title, message, url):
    """
    Canale opzionale/best effort.
    Se IFTTT non è configurato, trial scaduta, key invalida o applet non disponibile,
    il monitor NON fallisce.
    """

    if not IFTTT_KEY:
        print("IFTTT_KEY mancante: salto invio WhatsApp.")
        return

    payload = {
        "value1": title[:250],
        "value2": message[:700],
        "value3": url,
    }

    endpoint = f"https://maker.ifttt.com/trigger/{IFTTT_EVENT}/with/key/{IFTTT_KEY}"

    print("Invio WhatsApp via IFTTT...")

    try:
        response = requests.post(endpoint, json=payload, timeout=20)

        print("IFTTT status:", response.status_code)
        print("IFTTT response:", response.text)

        if response.status_code >= 400:
            print("Errore IFTTT: WhatsApp non inviato, ma il monitor continua.")
            return

        print("WhatsApp IFTTT inviato correttamente.")

    except Exception as e:
        print("Errore invio IFTTT WhatsApp:", repr(e))
        print("WhatsApp saltato, ma il monitor continua.")
        return


# =========================
# EMAIL RESEND - HTML WOW
# =========================

def build_email_subject(has_circular, new_news, has_comune_update):
    parts = []

    if has_circular:
        parts.append("nuova circolare")

    if new_news:
        parts.append(f"{len(new_news)} news")

    if has_comune_update:
        parts.append("Comune Milano aggiornato")

    if not parts:
        return "Monitor Scuola aggiornato"

    return "🚀 Monitor Scuola — " + ", ".join(parts)


def build_stat_badge(label, value):
    return f"""
    <td style="padding:8px;">
      <div style="background:rgba(15,23,42,.74);border:1px solid rgba(148,163,184,.22);border-radius:18px;padding:16px 14px;text-align:center;">
        <div style="font-size:24px;font-weight:900;color:#f8fafc;line-height:1;">{esc(value)}</div>
        <div style="margin-top:8px;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8;">{esc(label)}</div>
      </div>
    </td>
    """


def build_email_html(has_circular, circular, new_news, has_comune_update, comune_state):
    now_label = datetime.now().strftime("%d/%m/%Y · %H:%M")

    circular_block = ""

    if has_circular:
        circular_block = f"""
        <div style="margin-top:22px;background:linear-gradient(135deg,rgba(16,185,129,.18),rgba(56,189,248,.10));border:1px solid rgba(74,222,128,.38);border-radius:24px;padding:24px;">
          <div style="display:inline-block;padding:8px 13px;border-radius:999px;background:rgba(6,78,59,.88);border:1px solid rgba(74,222,128,.65);color:#bbf7d0;font-size:12px;font-weight:900;letter-spacing:.08em;">
            📄 NUOVA CIRCOLARE
          </div>

          <h2 style="margin:18px 0 10px;color:#f8fafc;font-size:24px;line-height:1.24;letter-spacing:-.02em;">
            {esc(circular.get("title"))}
          </h2>

          <div style="margin-top:16px;background:rgba(2,6,23,.34);border-radius:18px;padding:16px 18px;color:#cbd5e1;font-size:15px;line-height:1.75;">
            <div><strong style="color:#f8fafc;">Data circolare:</strong> {esc(circular.get("circular_date") or "N/D")}</div>
            <div><strong style="color:#f8fafc;">Pubblicata il:</strong> {esc(circular.get("published_date") or "N/D")}</div>
            <div><strong style="color:#f8fafc;">Tipologia:</strong> {esc(circular.get("tipologia") or "N/D")}</div>
          </div>

          <div style="margin-top:20px;">
            <a href="{esc(circular.get("link"))}" style="display:inline-block;background:linear-gradient(135deg,#4ade80,#22c55e);color:#052e16;text-decoration:none;padding:14px 18px;border-radius:14px;font-weight:900;font-size:14px;">
              Apri circolare →
            </a>
          </div>
        </div>
        """

    news_rows = ""

    if new_news:
        for idx, item in enumerate(new_news[:6], start=1):
            news_rows += f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid rgba(148,163,184,.14);">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td width="42" valign="top">
                      <div style="width:32px;height:32px;border-radius:999px;background:rgba(56,189,248,.16);border:1px solid rgba(56,189,248,.42);color:#bae6fd;text-align:center;line-height:32px;font-weight:900;font-size:13px;">
                        {idx}
                      </div>
                    </td>
                    <td valign="top">
                      <div style="font-size:15px;line-height:1.42;color:#f8fafc;font-weight:750;">
                        {esc(item.get("title"))}
                      </div>
                      <div style="margin-top:8px;">
                        <a href="{esc(item.get("link"))}" style="color:#38bdf8;text-decoration:none;font-size:13px;font-weight:800;">
                          Apri news →
                        </a>
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """
    else:
        news_rows = """
        <tr>
          <td style="padding:14px 0;color:#94a3b8;font-size:14px;">
            Nessuna nuova news scuola rilevata in questo controllo.
          </td>
        </tr>
        """

    comune_block = ""

    if has_comune_update and comune_state:
        comune_block = f"""
        <div style="margin-top:22px;background:linear-gradient(135deg,rgba(251,191,36,.18),rgba(249,115,22,.10));border:1px solid rgba(251,191,36,.44);border-radius:24px;padding:24px;">
          <div style="display:inline-block;padding:8px 13px;border-radius:999px;background:rgba(113,63,18,.85);border:1px solid rgba(251,191,36,.68);color:#fde68a;font-size:12px;font-weight:900;letter-spacing:.08em;">
            🏛️ COMUNE DI MILANO
          </div>

          <h2 style="margin:18px 0 10px;color:#f8fafc;font-size:24px;line-height:1.24;letter-spacing:-.02em;">
            {esc(COMUNE_TITLE)}
          </h2>

          <p style="margin:0;color:#d6d3d1;font-size:15px;line-height:1.7;">
            La pagina monitorata è cambiata. Verifica subito eventuali aggiornamenti su iscrizioni, scadenze o avvisi.
          </p>

          <div style="margin-top:20px;">
            <a href="{esc(COMUNE_MILANO_URL)}" style="display:inline-block;background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1c1917;text-decoration:none;padding:14px 18px;border-radius:14px;font-weight:900;font-size:14px;">
              Apri pagina Comune →
            </a>
          </div>
        </div>
        """

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#020617;font-family:Arial,Helvetica,sans-serif;color:#f8fafc;">
        <div style="padding:36px 14px;background:
          radial-gradient(circle at 12% 0%,rgba(20,184,166,.24),transparent 30%),
          radial-gradient(circle at 92% 6%,rgba(56,189,248,.18),transparent 30%),
          radial-gradient(circle at 50% 100%,rgba(74,222,128,.10),transparent 34%),
          #020617;">

          <div style="max-width:760px;margin:0 auto;border-radius:30px;overflow:hidden;border:1px solid rgba(148,163,184,.22);box-shadow:0 32px 90px rgba(0,0,0,.42);background:rgba(15,23,42,.94);">

            <div style="padding:30px 30px 26px;background:
              linear-gradient(135deg,rgba(15,118,110,.28),rgba(15,23,42,.0)),
              rgba(15,23,42,.96);border-bottom:1px solid rgba(148,163,184,.14);">

              <div style="display:inline-block;padding:9px 14px;border-radius:999px;background:rgba(6,78,59,.76);border:1px solid rgba(74,222,128,.52);color:#bbf7d0;font-size:12px;font-weight:900;letter-spacing:.08em;">
                ● MONITOR ATTIVO
              </div>

              <h1 style="margin:22px 0 8px;color:#f8fafc;font-size:36px;line-height:1.04;letter-spacing:-.05em;">
                Monitor Scuola<br>
                <span style="color:#67e8f9;">I.C.S. Moisè Loria</span>
              </h1>

              <p style="margin:0;color:#cbd5e1;font-size:16px;line-height:1.6;">
                Circolari, news scolastiche e aggiornamenti dal Comune di Milano.
              </p>

              <div style="margin-top:18px;color:#94a3b8;font-size:13px;">
                Ultimo controllo: <strong style="color:#e2e8f0;">{esc(now_label)}</strong>
              </div>
            </div>

            <div style="padding:22px 22px 8px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  {build_stat_badge("Circolari", "1" if has_circular else "0")}
                  {build_stat_badge("News", str(len(new_news)))}
                  {build_stat_badge("Comune", "1" if has_comune_update else "0")}
                </tr>
              </table>

              {circular_block}
              {comune_block}

              <div style="margin-top:22px;background:rgba(15,23,42,.76);border:1px solid rgba(148,163,184,.18);border-radius:24px;padding:24px;">
                <div style="display:inline-block;padding:8px 13px;border-radius:999px;background:rgba(8,47,73,.8);border:1px solid rgba(56,189,248,.46);color:#bae6fd;font-size:12px;font-weight:900;letter-spacing:.08em;">
                  📰 NEWS SCUOLA
                </div>

                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px;">
                  {news_rows}
                </table>
              </div>

              <div style="margin:28px 0 22px;text-align:center;">
                <a href="{esc(DASHBOARD_URL)}" style="display:inline-block;background:linear-gradient(135deg,#22c55e,#38bdf8);color:#020617;text-decoration:none;padding:15px 22px;border-radius:16px;font-weight:900;font-size:15px;">
                  Apri dashboard →
                </a>
              </div>

              <p style="margin:0 0 24px;color:#64748b;font-size:12px;text-align:center;line-height:1.5;">
                Aggiornamento generato automaticamente.
              </p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """


def send_email(has_circular, circular, new_news, has_comune_update, comune_state):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY mancante: salto invio email.")
        return

    base_recipients = EMAIL_TO.split(",") if EMAIL_TO else []
    extra_recipients = EMAIL_EXTRA_TO.split(",") if EMAIL_EXTRA_TO else []

    recipients = unique_list(base_recipients + extra_recipients)

    if not recipients:
        print("Nessun destinatario email valido: salto invio email.")
        return

    payload = {
        "from": RESEND_FROM,
        "to": recipients,
        "subject": build_email_subject(has_circular, new_news, has_comune_update),
        "html": build_email_html(has_circular, circular, new_news, has_comune_update, comune_state),
    }

    print("Invio email Resend...")
    print(f"Mittente email: {RESEND_FROM}")
    print(f"Numero destinatari email: {len(recipients)}")

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
    print("EMAIL_EXTRA_TO presente:", bool(EMAIL_EXTRA_TO))
    print("IFTTT_KEY presente:", bool(IFTTT_KEY))
    print("RESEND_FROM:", RESEND_FROM)

    circular = extract_latest_circular()
    news = extract_news()

    comune_state = None
    comune_error = None

    try:
        comune_state = extract_comune_milano_state()
    except Exception as e:
        comune_error = str(e)
        print("Errore monitor Comune Milano:", comune_error)

    print("=== CIRCOLARE ===")
    print(json.dumps(circular, indent=2, ensure_ascii=False))

    print("=== NEWS ===")
    print(json.dumps(news, indent=2, ensure_ascii=False))

    print("=== COMUNE MILANO ===")
    print(json.dumps(comune_state, indent=2, ensure_ascii=False) if comune_state else comune_error)

    prev_circular = load_json(STATE_FILE, {})
    prev_news = load_json(NEWS_STATE_FILE, [])
    prev_comune = load_json(COMUNE_STATE_FILE, {})

    has_new_circular = circular["id"] != prev_circular.get("id")

    prev_news_ids = [n["id"] for n in prev_news]
    new_news = [n for n in news if n["id"] not in prev_news_ids]

    has_comune_update = False

    if comune_state:
        if not prev_comune.get("id"):
            print("Prima baseline Comune Milano: salvo stato senza inviare alert.")
        elif comune_state["id"] != prev_comune.get("id"):
            has_comune_update = True
            print("Aggiornamento rilevato su pagina Comune Milano.")
        else:
            print("Nessun aggiornamento Comune Milano.")

    dashboard = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "site": "Istituto Comprensivo via Moisè Loria",
        "circulars_url": CIRCOLARI_URL,
        "news_url": NEWS_URL,
        "circular": circular,
        "news": news,
        "external_sources": {
            "comune_milano": {
                "url": COMUNE_MILANO_URL,
                "title": COMUNE_TITLE,
                "status": "ok" if comune_state else "error",
                "last_state": comune_state,
                "last_error": comune_error,
            }
        },
    }

    save_json(DASHBOARD_FILE, dashboard)

    has_school_update = has_new_circular or bool(new_news)
    has_any_update = has_school_update or has_comune_update

    if has_any_update:
        telegram_message = build_telegram_message(
            has_new_circular,
            circular,
            new_news,
            has_comune_update,
            comune_state,
        )

        send_telegram_text(
            telegram_message,
            telegram_buttons(has_new_circular, has_comune_update),
        )

        send_email(
            has_new_circular,
            circular,
            new_news,
            has_comune_update,
            comune_state,
        )

        whatsapp_title = build_whatsapp_title(
            has_new_circular,
            new_news,
            has_comune_update,
        )

        whatsapp_message = build_whatsapp_message(
            has_new_circular,
            circular,
            new_news,
            has_comune_update,
        )

        whatsapp_url = build_whatsapp_url(
            has_new_circular,
            circular,
            has_comune_update,
        )

        send_ifttt_whatsapp(
            whatsapp_title,
            whatsapp_message,
            whatsapp_url,
        )

        print("Aggiornamento Telegram testo + Email wow + WhatsApp opzionale completato.")
    else:
        print("Nessun aggiornamento da notificare.")

    save_json(STATE_FILE, circular)
    save_json(NEWS_STATE_FILE, news)

    if comune_state:
        save_json(COMUNE_STATE_FILE, comune_state)


if __name__ == "__main__":
    main()
