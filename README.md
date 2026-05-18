# Circolari Loria Monitor

<p align="center">
  <strong>Monitor automatico per circolari scolastiche, news e aggiornamenti esterni</strong>
</p>

<p align="center">
  <em>Python · GitHub Actions · GitHub Pages · Telegram · Email · WhatsApp opzionale</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-active-brightgreen?style=for-the-badge" />
  <img src="https://img.shields.io/badge/python-3.11-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/GitHub%20Actions-automated-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" />
  <img src="https://img.shields.io/badge/GitHub%20Pages-dashboard-222222?style=for-the-badge&logo=githubpages&logoColor=white" />
</p>

<p align="center">
  <a href="https://adelisa-srg.github.io/circolari-loria-monitor/">
    <strong>Apri la dashboard</strong>
  </a>
</p>

---

## Overview

**Circolari Loria Monitor** è un sistema leggero di monitoraggio automatico pensato per controllare fonti scolastiche e istituzionali rilevanti, rilevare nuovi aggiornamenti e inviare notifiche tempestive su più canali.

Il progetto nasce per evitare controlli manuali quotidiani su pagine web scolastiche e comunali, trasformando il controllo delle comunicazioni in un flusso automatico, tracciato e consultabile.

---

## Cosa monitora

Il sistema controlla tre fonti principali:

| Fonte | Tipo controllo | Output |
|---|---|---|
| Circolari scuola primaria | Ultima circolare pubblicata | Alert se cambia |
| News scolastiche | Nuove news rispetto allo stato precedente | Alert se ci sono nuove news |
| Comune di Milano | Variazione contenuto pagina | Alert se cambia la pagina |

---

## Fonti monitorate

### Circolari scuola primaria

Pagina monitorata:

```text
https://www.icsmoiseloria.edu.it/pvw2/app/default/index.php?cerca=primaria&categoria=0&tipo=comunicati&storico=on
```

Il monitor estrae:

- titolo della circolare;
- data della circolare;
- data di pubblicazione;
- tipologia;
- allegato;
- link al documento;
- URL sorgente.

Lo stato viene salvato in:

```text
last_circolare.json
```

---

### News scolastiche

Pagina monitorata:

```text
https://www.icsmoiseloria.edu.it/archivio-news
```

Il monitor analizza le news pubblicate e filtra link generici o pagine non rilevanti, così da concentrarsi sugli aggiornamenti utili.

Lo stato viene salvato in:

```text
last_news.json
```

---

### Comune di Milano — Pre-scuola e giochi serali

Pagina monitorata:

```text
https://www.comune.milano.it/servizi/scuola/pre-scuola-e-giochi-serali-scuole-primarie
```

Per questa fonte il sistema usa una logica di **change detection**.

Non viene cercata una singola news, ma viene monitorato il contenuto testuale principale della pagina.

Il processo è:

```text
Scarica pagina
   ↓
Pulisce HTML tecnico
   ↓
Normalizza testo
   ↓
Calcola hash SHA-256
   ↓
Confronta con lo stato precedente
   ↓
Invia alert se cambia
```

Lo stato viene salvato in:

```text
last_comune_milano.json
```

Al primo run viene creata una baseline senza inviare notifiche, così da evitare falsi positivi.

---

## Dashboard

Il progetto aggiorna una dashboard pubblica tramite GitHub Pages.

```text
https://adelisa-srg.github.io/circolari-loria-monitor/
```

La dashboard legge i dati generati automaticamente da:

```text
docs/data/dashboard.json
```

La dashboard mostra:

- ultima circolare rilevata;
- news recenti;
- stato delle fonti monitorate;
- ultimo aggiornamento;
- eventuali errori sulle fonti esterne.

---

## Canali di notifica

Il sistema supporta più canali di notifica.

```text
Aggiornamento rilevato
   ↓
Telegram
   ↓
Email
   ↓
WhatsApp opzionale
   ↓
Dashboard aggiornata
```

### Telegram

Telegram è il canale principale.

Il monitor può inviare:

- card grafica generata automaticamente;
- messaggio riepilogativo;
- pulsanti inline per aprire dashboard, circolari, news o pagina Comune.

---

### Email

Il monitor invia una email HTML riepilogativa con:

- eventuale nuova circolare;
- eventuali nuove news;
- eventuale variazione sulla pagina del Comune;
- pulsanti di accesso rapido alle fonti.

---

### WhatsApp via IFTTT

WhatsApp è supportato tramite IFTTT Webhooks.

È configurato come canale **best effort**:

- se disponibile, viene inviato anche il messaggio WhatsApp;
- se non disponibile, il sistema continua;
- un errore WhatsApp non blocca la GitHub Action;
- Telegram, email e dashboard restano operativi.

---

## Architettura

```text
┌──────────────────────────────┐
│          Web Sources          │
│  Scuola · News · Comune       │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│       check_circolari.py      │
│ Scraping · Diff · Hash · JSON │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│        State Management       │
│ last_*.json · dashboard.json  │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│        Notification Layer     │
│ Telegram · Email · WhatsApp   │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│        GitHub Pages           │
│        Public Dashboard       │
└──────────────────────────────┘
```

---

## Flusso di esecuzione

```text
GitHub Actions
   ↓
Installa dipendenze Python
   ↓
Esegue check_circolari.py
   ↓
Scarica le fonti monitorate
   ↓
Confronta con lo stato precedente
   ↓
Aggiorna dashboard.json
   ↓
Invia notifiche se necessario
   ↓
Aggiorna i file last_*.json
   ↓
Esegue commit automatico
```

---

## Struttura repository

```text
circolari-loria-monitor/
│
├── .github/
│   └── workflows/
│       └── check-circolari.yml
│
├── assets/
│   └── logo.png
│
├── docs/
│   ├── index.html
│   └── data/
│       └── dashboard.json
│
├── check_circolari.py
├── last_circolare.json
├── last_news.json
├── last_comune_milano.json
├── .gitignore
└── README.md
```

---

## Componenti principali

### `check_circolari.py`

È il cuore del progetto.

Responsabilità principali:

- scraping delle circolari;
- scraping delle news;
- monitoraggio della pagina Comune;
- confronto con lo stato precedente;
- generazione card grafica;
- invio notifiche;
- aggiornamento dashboard;
- salvataggio stato.

---

### `.github/workflows/check-circolari.yml`

Workflow GitHub Actions.

Responsabilità:

- esecuzione pianificata;
- installazione dipendenze;
- lancio dello script Python;
- aggiornamento automatico dei file JSON;
- commit dei dati aggiornati.

---

### `docs/index.html`

Dashboard statica pubblicata tramite GitHub Pages.

---

### `docs/data/dashboard.json`

File dati generato automaticamente.

Contiene lo stato più recente del monitor.

---

### `last_circolare.json`

Memoria dell’ultima circolare rilevata.

---

### `last_news.json`

Memoria delle news già viste.

---

### `last_comune_milano.json`

Memoria dell’ultimo stato della pagina Comune.

---

### `assets/logo.png`

Logo usato per la card grafica inviata su Telegram.

---

## Scheduling

Il monitor viene eseguito due volte al giorno tramite GitHub Actions.

```yaml
on:
  schedule:
    - cron: '0 5,16 * * *'
  workflow_dispatch:
```

GitHub Actions interpreta il cron in UTC.

Durante l’ora legale italiana, la schedulazione corrisponde indicativamente a:

```text
07:00 Italia
18:00 Italia
```

Il workflow può essere avviato anche manualmente dalla tab **Actions**.

---

## Dipendenze

Il progetto usa Python 3.11.

Dipendenze principali:

```bash
pip install requests beautifulsoup4 pillow resend
```

| Libreria | Utilizzo |
|---|---|
| `requests` | Chiamate HTTP |
| `beautifulsoup4` | Parsing HTML |
| `pillow` | Generazione card grafica |
| `resend` | Invio email |
| `hashlib` | Calcolo hash pagina Comune |
| `json` | Lettura e scrittura stato |
| `datetime` | Timestamp |

---

## State management

Il progetto usa file JSON versionati per mantenere memoria degli ultimi contenuti rilevati.

```text
last_circolare.json
last_news.json
last_comune_milano.json
```

Questi file permettono al monitor di distinguere tra contenuti già notificati e aggiornamenti nuovi.

---

## Reset controllato

È possibile forzare una nuova baseline o una nuova notifica modificando i file di stato.

### Reset circolari

```text
last_circolare.json
```

Se eliminato o svuotato, la circolare corrente verrà trattata come nuova.

---

### Reset news

```text
last_news.json
```

Se eliminato o svuotato, le news correnti verranno trattate come nuove.

---

### Reset Comune Milano

```text
last_comune_milano.json
```

Se eliminato, il monitor ricreerà la baseline della pagina Comune al run successivo.

---

## Comportamento notifiche

### Nuova circolare

Quando viene rilevata una nuova circolare:

```text
Dashboard aggiornata
Telegram inviato
Email inviata
WhatsApp tentato
Stato aggiornato
```

---

### Nuove news

Quando vengono rilevate nuove news:

```text
Dashboard aggiornata
Telegram inviato
Email inviata
WhatsApp tentato
Stato aggiornato
```

---

### Aggiornamento Comune Milano

Quando cambia la pagina monitorata:

```text
Dashboard aggiornata
Telegram inviato
Email inviata
WhatsApp tentato
Stato aggiornato
```

---

## Gestione errori

Il progetto distingue tra canali principali e canali opzionali.

### WhatsApp

WhatsApp è opzionale.

Un errore su IFTTT non blocca l’esecuzione.

Esempio:

```text
Invio WhatsApp via IFTTT...
IFTTT status: 401
Errore IFTTT: WhatsApp non inviato, ma il monitor continua.
```

---

### Comune di Milano

La pagina del Comune è una fonte esterna e può cambiare struttura o rispondere in modo non previsto.

Se il controllo fallisce:

- il monitor scuola continua;
- l’errore viene registrato nei log;
- la dashboard può riportare lo stato della fonte;
- non viene generato un falso alert.

---

## Log attesi

A inizio esecuzione il workflow stampa un riepilogo di configurazione senza mostrare valori riservati.

```text
=== CONFIG CHECK ===
TELEGRAM_TOKEN presente: True
TELEGRAM_CHAT_ID presente: True
RESEND_API_KEY presente: True
EMAIL_TO presente: True
IFTTT_KEY presente: True
LOGO_FILE: assets/logo.png
LOGO_FILE exists: True
```

Se non ci sono aggiornamenti:

```text
Nessun aggiornamento da notificare.
```

Se ci sono aggiornamenti:

```text
Telegram photo status: 200
Telegram text status: 200
Invio email Resend...
Invio WhatsApp via IFTTT...
Aggiornamento Telegram + Email + WhatsApp opzionale completato.
```

---

## Sicurezza operativa

Il progetto è compatibile con un repository pubblico.

Le configurazioni riservate non devono essere salvate nel codice sorgente o nei file versionati.

Il codice legge le configurazioni dall’ambiente di esecuzione e nei log mostra solo informazioni booleane o diagnostiche non sensibili.

---

## Costi e consumi

Il progetto esegue due controlli al giorno.

```text
2 run/giorno
circa 60 run/mese
```

Il carico computazionale è molto basso.

La dashboard è statica.

WhatsApp tramite IFTTT è opzionale e può dipendere dal piano IFTTT attivo.

---

## Roadmap

### Dashboard evoluta

Possibili miglioramenti:

- stato per singola fonte;
- timestamp ultimo controllo;
- timestamp ultimo aggiornamento rilevato;
- badge OK/Errore;
- storico notifiche;
- sezione eventi recenti;
- link diretti alle fonti;
- evidenza dell’ultimo alert inviato.

---

### Storico notifiche

Possibile aggiunta di:

```text
docs/data/history.json
```

Esempio struttura:

```json
[
  {
    "timestamp": "2026-05-19T06:00:00Z",
    "source": "school_circular",
    "title": "Titolo circolare",
    "url": "https://..."
  }
]
```

---

### Configurazione multi-fonte

Possibile spostamento delle fonti monitorate in:

```text
config/monitors.json
```

Esempio:

```json
{
  "external_sources": [
    {
      "key": "comune_milano_prescuola",
      "title": "Pre-scuola e giochi serali",
      "url": "https://www.comune.milano.it/servizi/scuola/pre-scuola-e-giochi-serali-scuole-primarie"
    }
  ]
}
```

---

### Nuove fonti esterne

Il monitor può essere esteso ad altre pagine:

- servizi scolastici comunali;
- pagine istituzionali;
- bandi o avvisi;
- calendario scolastico;
- servizi mensa;
- iscrizioni e scadenze.

---

### Differenziazione canali

Possibile evoluzione:

| Fonte | Telegram | Email | WhatsApp |
|---|---:|---:|---:|
| Circolare scuola | Sì | Sì | Sì |
| News scuola | Sì | Sì | Opzionale |
| Comune Milano | Sì | Sì | Sì |
| Errore fonte | No | Sì | No |

---

### Riduzione falsi positivi

Per le pagine esterne si può migliorare la change detection:

- selezione di un contenitore HTML specifico;
- esclusione di sezioni dinamiche;
- salvataggio di un diff testuale;
- alert solo su parole chiave rilevanti;
- distinzione tra modifiche tecniche e modifiche informative.

---

## Context pack per evoluzioni future

Questo blocco può essere usato come contesto da passare a un assistente AI per future modifiche.

```text
Repository: adelisa-srg/circolari-loria-monitor

Il progetto è un monitor automatico basato su Python, GitHub Actions e GitHub Pages.

Fonti monitorate:
- circolari scuola primaria I.C.S. Moisè Loria;
- archivio news del sito scolastico;
- pagina Comune Milano "Pre-scuola e giochi serali - Scuole primarie".

File principali:
- check_circolari.py: scraping, confronto stato, generazione dashboard JSON, notifiche.
- .github/workflows/check-circolari.yml: workflow schedulato.
- docs/index.html: dashboard GitHub Pages.
- docs/data/dashboard.json: dati generati automaticamente.
- assets/logo.png: logo per card grafica.
- last_circolare.json, last_news.json, last_comune_milano.json: stato persistente.

Canali:
- Telegram: canale principale.
- Email: riepilogo HTML.
- WhatsApp: opzionale via IFTTT, best effort, non deve bloccare la GitHub Action.

Vincoli:
- Non inserire configurazioni riservate nel codice.
- Non cancellare .github/workflows.
- Non cancellare docs/, usato da GitHub Pages.
- Non cancellare i file last_*.json salvo reset consapevole.
- La pagina Comune deve creare una baseline al primo run e notificare solo cambiamenti successivi.
- WhatsApp deve restare opzionale e non bloccante.
- Il workflow deve aggiornare dashboard.json e i file di stato.
- Mantenere il progetto semplice, economico e facilmente manutenibile.

Obiettivo:
migliorare robustezza, dashboard, gestione multi-fonte, storico notifiche e qualità degli alert.
```

---

## Stato attuale

```text
Monitor circolari scuola          OK
Monitor news scuola               OK
Monitor pagina Comune Milano      OK
Dashboard GitHub Pages            OK
Telegram                          OK
Email                             OK
WhatsApp IFTTT                    Opzionale / best effort
Schedulazione GitHub Actions      2 volte al giorno
```

---

## Convenzioni di commit

Esempi:

```text
Update monitor workflow
Improve notification handling
Add external page monitoring
Update dashboard data model
Make WhatsApp notification optional
Improve README documentation
Fix Comune Milano page detection
```

---

## Filosofia del progetto

Il progetto è pensato per essere:

- semplice;
- economico;
- automatico;
- leggibile;
- estendibile;
- resiliente agli errori non critici.

L’idea è trasformare un controllo manuale ripetitivo in un piccolo sistema di monitoraggio personale, mantenendo il codice accessibile e facilmente evolvibile.
