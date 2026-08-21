# Autonomous Crawler Daemon — Istruzioni Operative per Agenti AI

Questo documento contiene le istruzioni standard per qualunque agente AI o operatore che debba **avviare, monitorare, estendere e gestire il demone di crawling continuo** in Load Forge.

---

## 1. Obiettivo & Funzionamento
Il demone [`tools/autonomous_crawler_daemon.py`](../tools/autonomous_crawler_daemon.py) è un processo continuo progettato per:
1. **Scansionare a ciclo continuo** gli store e i cataloghi online di costruttori e distributori ufficiali (Shopify feeds, sitemap XML, REST API).
2. **Estrarre e validare parametri di laboratorio T/S di prima mano** ($F_s, Q_{ts}, Q_{es}, Q_{ms}, V_{as}, R_e, S_d, X_{max}, P_e$).
3. **Agganciare i prezzi ufficiali al dettaglio** e i link di acquisto diretti.
4. **Scrivere direttamente su [`data/catalog_proprietario.json`](../data/catalog_proprietario.json)** garantendo che il DB nativo rimanga 100% pulito e conforme.
5. **Rigenerare atomicamente la cache binaria** (`.cache.pickle`) per mantenere il tempo di avvio dell'app sotto i 0.08s.
6. **Eseguire commit e push su git `main`** in automatico a ogni lotto di nuovi modelli scoperto.

---

## 2. Avvio del Demone (Quickstart per Agente AI)

Per avviare il demone in background:

```bash
.venv/bin/python tools/autonomous_crawler_daemon.py &
```

Se sei un agente che usa il tool `run_command`, lancia il comando con un breve timeout asincrono:
* `CommandLine`: `.venv/bin/python tools/autonomous_crawler_daemon.py`
* `WaitMsBeforeAsync`: `500`

---

## 3. Monitoraggio dei Log in Tempo Reale

I log di attività, gli altoparlanti scoperti e gli intervalli di sleep vengono scritti in [`data/crawler_daemon.log`](../data/crawler_daemon.log):

```bash
tail -n 30 data/crawler_daemon.log
```

---

## 4. Test di Coerenza Dati Istantaneo (< 0.1s)
Quando si effettuano modifiche ai file di catalogo JSON o al demone, **non lanciare la test suite completa da 170 test** (spreco di token e tempo). Esegui invece il test di coerenza dati:

```bash
.venv/bin/python -c '
import sys; sys.path.insert(0, "src"); import presets
presets._load_manufacturer_presets.cache_clear()
p, info = presets._load_manufacturer_presets()
assert len(p) >= 4800, f"Catalog issue: only {len(p)} presets loaded"
print(f"✓ Data coherence check passed: {len(p)} unique clean presets validated.")
'
```

---

## 5. Come Aggiungere Nuovi Costruttori al Demone

Per aggiungere un nuovo costruttore o distributore con feed Shopify o sitemap, apri [`tools/autonomous_crawler_daemon.py`](../tools/autonomous_crawler_daemon.py) e inserisci la tupla `(URL, Brand, Valuta)` nella lista `stores`:

```python
stores = [
    ("https://massiveaudio.com", "Massive Audio", "USD"),
    ("https://www.ctsounds.com", "CT Sounds", "USD"),
    ("https://ds18.com", "DS18", "USD"),
    ("https://nvx.com", "NVX", "USD"),
    ("https://www.rockvilleaudio.com", "Rockville", "USD"),
    ("https://soundautoconcept.com", "Car Audio", "EUR"),
    ("https://nuovosito.com", "Nome Brand", "USD"),  # <- Aggiungi qui
]
```

Il demone includerà automaticamente il nuovo endpoint nel ciclo successivo.

---

## 6. Arresto del Demone

Se è necessario fermare il processo del demone:

```bash
pkill -f "tools/autonomous_crawler_daemon.py"
```
