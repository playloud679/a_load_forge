# Strategia Social Share, Headless API & Hosting Low-Cost

Questo documento definisce la visione strategica e l'architettura tecnica per tre evoluzioni chiave di **Load Forge**:
1. **Social Sharing Ibrido (Facebook, Reddit, Forum)**: Generazione di schede progetto e marketing virale senza i costi di gestione di un social network proprietario.
2. **Architettura Headless API (FastAPI) per App Mobile**: Esposizione del motore di calcolo per client nativi Android e iOS.
3. **Infrastruttura di Hosting a Costo Minimo / Zero**: Alternative sostenibili ed economiche ai servizi serverless (Cloud Run).

---

## 1. Social Sharing Ibrido & Scheda Progetto ("Project Card")

### A. Perché l'Approccio Ibrido è Vincente
Creare un social network proprietario (feed, commenti, storage foto, moderazione) comporta costi infrastrutturali e di conformità legale (GDPR) elevati. 
L'approccio **ibrido** sfrutta le community e i gruppi già esistenti (Facebook DIY Audio, AVSForum, Reddit `r/diyaudio`), fornendo all'utente una **scheda grafica professionale e un link interattivo al progetto**.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        GENERATORE SCHEDA SOCIAL & BUNDLE                               │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│ 1. INFOGRAFICA SOCIAL (1200x630 PNG)     │ 2. CONTROLLI & TESTO CONDIVISIONE           │
│                                          │                                             │
│  ┌────────────────────────────────────┐  │ • Titolo Progetto: [ Subwoofer 12" DCCAV ]  │
│  │ 🔈 LOAD FORGE  •  Dayton RSS315HO  │  │ • Note autore: [ Mobile reflex da 45L per ] │
│  │ ────────────────────────────────── │  │   [ uso Home Cinema accordato a 24 Hz...  ] │
│  │ [ Grafico SPL ]   [ Badge Dati ]   │  │                                             │
│  │   Curva Totale     • Vb: 45 L      │  │ [ 📥 Scarica Scheda Immagine (PNG) ]        │
│  │   F3: 24.2 Hz      • Fb: 23.5 Hz   │  │ [ 📋 Copia Testo Formattato per Post ]      │
│  │   MOL @ F3: 112dB  • Vent: 8x32cm  │  │ [ 🔗 Condividi su Facebook ]                │
│  │                    • Qts: 0.38     │  │                                             │
│  │ [ QR Code / Link per aprire l'app] │  │ ☑ Includi file .lfp nel download            │
│  └────────────────────────────────────┘  │                                             │
└──────────────────────────────────────────┴─────────────────────────────────────────────┘
```

### B. Funzionalità del Modulo
1. **Infografica ad Alto Contrasto (1200 × 630 px PNG)**:
   * Header branded Load Forge, driver e allineamento acustico.
   * Grafico della risposta in frequenza ad alta leggibilità.
   * Griglia delle metriche chiave ($V_b / V_h / V_l$, $F_b / f_h / f_l$, $F_3 / F_6$, $X_{\max}$, diametro e velocità condotto).
   * QR-Code e short-link per ricaricare istantaneamente il progetto interattivo nel browser.
2. **Snippet Testuale Pre-Formattato**:
   * Testo pronto per il copia-incolla con emoji, specifiche tecniche e link all'app.
3. **Pulsante Diretto "Condividi su Facebook"**:
   * Dialog nativo Facebook con passaggio dei tag Open Graph (`og:image`, `og:title`, `og:description`).
4. **Project Bundle Download**:
   * Archivio ZIP contenente: immagine PNG, file di progetto `.lfp`, file di risposta `.frd` e impedenza `.zma`.

---

## 2. Headless API (FastAPI) per App Mobile Android & iOS

### A. Perché Streamlit Non è Adatto come Backend API
* **Streamlit**: Architettura a sessioni persistenti WebSocket, pensata per rendering reattivo di componenti React su browser web. Non espone endpoint stateless JSON conformi agli standard OpenAPI/REST.
* **Soluzione**: Affiancare un microservizio leggero basato su **FastAPI** che importa direttamente i moduli Python puri di `src/`.

### B. Architettura del Sistema
Il motore di calcolo è già completamente disaccoppiato dall'interfaccia:

```
                          ┌───────────────────────────┐
                          │   CORE FISICO & MOTORE    │
                          │        (src/*.py)         │
                          └─────────────┬─────────────┘
                                        │ (import puro)
                     ┌──────────────────┴──────────────────┐
                     │                                     │
           ┌─────────▼─────────┐                 ┌─────────▼─────────┐
           │ Streamlit Server  │                 │  FastAPI Server   │
           │   (ui_app.py)     │                 │   (api_app.py)    │
           └─────────┬─────────┘                 └─────────┬─────────┘
                     │ (Web Browser)                       │ (REST / JSON)
              💻 Desktop / Web                    📱 App iOS & Android
                                                 (Flutter / React Native)
```

### C. Specifiche Endpoint REST (`/api/v1`)
* `POST /api/v1/simulate`: Calcola curve SPL, escursione, impedenza, velocità condotto e metriche $F_3/F_6/F_10$, MIL/MOL e Forge Score.
* `POST /api/v1/optimize`: Esegue l'algoritmo di ottimizzazione allineamento dato un driver e vincoli di volume/estensione.
* `POST /api/v1/bass-match`: Esegue la scansione e il ranking del catalogo altoparlanti sui criteri specificati nel brief.
* `GET /api/v1/drivers`: Restituisce l'elenco dei driver con parametri T/S filtrabili per marca, diametro e fascia di prezzo.

### D. Client Mobile Consigliato
* **Flutter o React Native**: Sviluppo di una singola codebase per iOS e Android, con supporto a grafici vettoriali touch interattivi a 60/120 Hz (es. `fl_chart` per Flutter o Victory Native).

---

## 3. Strategia di Hosting Low-Cost & Zero-Cost

### A. Il Problema dei Costi con Google Cloud Run
Google Cloud Run fattura il tempo di calcolo e memoria in base all'attività. Con Streamlit, le connessioni WebSocket rimangono aperte, impedendo al container di scalare a zero ("scale to zero"). Mantenere 1 istanza sempre attiva o con sessioni prolungate genera costi fissi non trascurabili.

### B. Alternative Economiche e a Costo Fisso

| Piattaforma | Costo Mensile | CPU / RAM | Vantaggi Chiave | Ideale Per |
|---|:---:|:---:|---|---|
| **Hetzner Cloud (CX22 / CAX11)** | **~3,80 €** | 2 vCPU, 4 GB RAM, 40 GB NVMe | Prezzo fisso garantito, traffico 20 TB, controllo totale Linux/Docker | Web App + FastAPI + DB su unico server |
| **Streamlit Community Cloud** | **0,00 €** | Risorse condivise | Deploy automatico da GitHub, zero gestione sistemistica, SSL incluso | Web App pubblica / Open Beta |
| **Oracle Cloud Always Free** | **0,00 €** | Fino a 4 core ARM, 24 GB RAM | Il tier gratuito più generoso al mondo, 100% gratis per sempre | Web App + API + Crawler 24/7 a costo zero |
| **Render / Fly.io** | **0,00 – 5,00 $** | Tier Starter / Hobby | Deploy moderno da Git con isolamento container | Test rapidi e staging |

### C. Configurazione di Produzione Raccomandata (Docker Compose + Caddy)
Un singolo server VPS Hetzner (o VM Oracle Free) può gestire l'intero stack tramite **Docker Compose** e **Caddy** (reverse proxy con emissione automatica di certificati SSL Let's Encrypt):

```yaml
version: '3.8'

services:
  caddy:
    image: caddy:latest
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

  streamlit_app:
    build: .
    restart: always
    command: .venv/bin/streamlit run ui_app.py --server.port=8501 --server.headless=true

  fastapi_app:
    build: .
    restart: always
    command: .venv/bin/uvicorn api_app:app --host 0.0.0.0 --port 8000

volumes:
  caddy_data:
  caddy_config:
```

#### Esempio `Caddyfile`:
```caddyfile
loadforge.tuodominio.it {
    reverse_proxy streamlit_app:8501
}

api.tuodominio.it {
    reverse_proxy fastapi_app:8000
}
```

Questo setup garantisce:
1. Spesa mensile minima e prevedibile (**0 € - 3,80 € / mese**).
2. Manutenzione quasi nulla grazie a Caddy e Docker.
3. Coesistenza perfetta tra Web App interattiva e API REST per l'app mobile.
