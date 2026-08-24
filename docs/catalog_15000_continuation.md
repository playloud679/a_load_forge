# Continuazione catalogo proprietario verso 15.000

## Stato esatto della pausa

- Catalogo: `data/catalog_proprietario.json`
- Versione catalogo: `1.0.0`
- Record grezzi: **7.379**
- Record visibili nell'app: **6.375**
- Ultimo commit pubblicato: `3b8a20a` — `Add Hertz DS 250.3 official datasheet driver`
- Branch: `main`, push completato su `origin/main`
- Test catalogo: passati (`CATALOG PASS`, `CRAWLER REGISTRY PASS`)

## Ultimo blocco completato

Aggiunto `Hertz DIECI3_TechSheet_DS-250_3` dal datasheet ufficiale, con Fs 36 Hz,
Vas 29 L, Mms 120 g, Re 3,4 ohm, Qts 0,62, Qes 0,69, Qms 6,35, BL 11,8 T·m e
Xmax 10 mm. Le righe preesistenti non sono state modificate.

## Fonti controllate senza nuove aggiunte

- FaitalPRO ufficiale: 212 modelli completi, 0 nuovi
- SICA/Jensen official Store API: 145 modelli completi, 0 nuovi
- Monacor PA bass: 17 completi, 0 nuovi
- Monacor PA midrange: 8 completi, 0 nuovi
- Monacor Hi-Fi: 44 completi, 0 nuovi
- Peerless/Tymphany API: 429 dopo l'enumerazione di 107 modelli; nessun dato parziale importato

## Checkpoint disponibili

- `data/faitalpro_official_checkpoint.json`
- `data/sica_official_checkpoint.json`
- `data/monacor_bass_official.json`
- `data/monacor_midrange_official.json`
- `data/monacor_hifi_official.json`

## Ripresa consigliata

Continuare Monacor per categorie isolate, poi deduplicare e pubblicare solo record
ufficiali completi:

- `pa-coaxial-speakers-and-full-range-speakers-`
- `hi-fi-midrange-speakers-`
- `hi-fi-full-range-speakers-`
- `miniature-speakers-`

Comando modello:

```bash
.venv/bin/python - <<'PY'
import sys
import tools.harvest_monacor_official as m
m.CATEGORY_SLUGS=('pa-coaxial-speakers-and-full-range-speakers-',)
sys.argv=['harvest_monacor_official.py','--output','data/monacor_coax_official.json',
          '--workers','24','--timeout','15','--retries','1']
raise SystemExit(m.main())
PY
```

Per ogni blocco usare `identity()` e `runtime_identity()` di
`tools/publish_reviewed_catalog_additions.py`, poi `make test-catalog`. Aggiornare
`data/catalog_additions_latest_report.json` e `CHANGELOG.md` solo quando vengono
pubblicati nuovi record, quindi commit e push.

## Vincoli

- Le librerie esterne sono solo radar, mai import diretto.
- Catalogo proprietario append-only: non cancellare o riscrivere righe esistenti.
- Distinguere sempre record grezzi da record visibili nell'app.
- L'obiettivo resta 15.000: questa è una pausa operativa, non la chiusura del lavoro.
