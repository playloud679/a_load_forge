# Stato database manufacturer driver

> File generato automaticamente: non modificare a mano i numeri.  
> Rigenerazione: `.venv/bin/python tools/generate_manufacturer_database_report.py`

Generato: **2026-07-22T18:06:43+02:00**  
Database letto: `data/manufacturer_drivers.json` (modificato 2026-07-22T16:34:07+02:00)

## Sintesi

Il catalogo contiene **4.424 driver** di **63 produttori**. I sette parametri fondamentali sono completi al **100.00%** dei record. I prezzi verificabili coprono il **64.65%**.

## Copertura parametri

| Parametro | Presenti | Mancanti | Copertura |
|---|---|---|---|
| Fs | 4.424 | 0 | 100.00% |
| Vas | 4.424 | 0 | 100.00% |
| Qts | 4.424 | 0 | 100.00% |
| Qms | 4.424 | 0 | 100.00% |
| Qes | 4.424 | 0 | 100.00% |
| Re | 4.424 | 0 | 100.00% |
| Sd | 4.424 | 0 | 100.00% |
| Mms | 4.421 | 3 | 99.93% |
| Cms | 4.423 | 1 | 99.98% |
| BL | 4.423 | 1 | 99.98% |
| Xmax | 4.206 | 218 | 95.07% |
| Potenza Pe | 4.260 | 164 | 96.29% |
| Le | 4.252 | 172 | 96.11% |
| Dimensione nominale | 4.424 | 0 | 100.00% |

## Prezzi

- Driver con prezzo: **2.860/4.424** (64.65%).
- Senza prezzo: **1.564**; marcati senza abbinamento commerciale affidabile: **1.564**.
- Prezzi con URL: **2.860**; con provenienza strutturata: **2.860**.
- Indice commerciale separato: **6.805** offerte; aggiornato `2026-07-22T13:28:45+00:00`.
- Valute: USD 1.443, EUR 1.109, GBP 308.

I record senza corrispondenza sicura restano intenzionalmente senza prezzo: il report non considera stime o medie inventate.

## Qualità e provenienza

- Record con almeno un parametro fondamentale non valido: **0**.
- Conflitti fisici `Qms <= Qts`: **0**.
- Vecchi valori Pe invalidati perché privi di unità W/kW: **88**.
- Provenienza esplicita da refresh: Xmax **188**, Pe **879**, Le **264**.
- Campi derivati tracciati: Qes **4.321**, Cms **2.654**, size_in **2.157**, BL **701**, Mms **176**, Sd **24**, Re **11**, Qms **3**, Qts **2**.

Le derivazioni vengono conteggiate solo quando memorizzate in `website_fields.derived_fields`; i valori pubblicati e quelli derivati restano distinguibili.

## Deduplicazione

Dry-run corrente: **4.424 → 4.424**, duplicati conservativi rimovibili **0**.

L'ultimo report applicato ha ridotto il catalogo da 4.697 a 4.424 record (273 rimossi).

## Principali fonti

| Fonte | Driver | Quota |
|---|---|---|
| Parts Express API | 1.168 | 26.40% |
| SoundImports retailer | 919 | 20.77% |
| Manufacturer website | 449 | 10.15% |
| SICA official | 146 | 3.30% |
| B&C Speakers Remix crawler | 140 | 3.16% |
| Eighteen Sound Catalog | 120 | 2.71% |
| Ciare crawler | 117 | 2.64% |
| Bomber official | 108 | 2.44% |
| FaitalPRO Official Excel | 103 | 2.33% |
| Eminence crawler | 96 | 2.17% |
| Visaton crawler | 93 | 2.10% |
| PHL Audio official PDF | 93 | 2.10% |
| SB Acoustics crawler | 87 | 1.97% |
| Beyma Catalog | 86 | 1.94% |
| P.Audio official | 86 | 1.94% |

## Lacune prioritarie per produttore

### Xmax

| Produttore | Record mancanti |
|---|---|
| DS18 | 49 |
| SICA | 42 |
| B&C Speakers | 27 |
| Fostex | 19 |
| Factory Buyouts | 16 |
| Visaton | 9 |
| Atohm | 7 |
| Supravox | 6 |
| Coast Buyouts | 6 |
| BMS | 4 |
| Pride | 4 |
| SB Acoustics | 3 |
| Wavecor | 3 |
| Timpano Audio | 3 |
| Scan-Speak | 3 |

### Potenza Pe

| Produttore | Record mancanti |
|---|---|
| Eminence | 69 |
| Fostex | 19 |
| Bomber | 16 |
| Beyma | 11 |
| BMS | 9 |
| Supravox | 9 |
| Atohm | 7 |
| SICA | 7 |
| Visaton | 3 |
| PURIFI | 3 |
| Accuton | 2 |
| Silver Flute | 2 |
| BlieSMa | 2 |
| CSS | 2 |
| Eighteen Sound | 1 |

### Le

| Produttore | Record mancanti |
|---|---|
| HiVi | 29 |
| Pride | 24 |
| Ciare | 14 |
| Markaudio | 14 |
| Visaton | 12 |
| Coast Buyouts | 12 |
| Bomber | 10 |
| BMS | 8 |
| Supravox | 7 |
| Factory Buyouts | 6 |
| Celestion | 5 |
| SB Acoustics | 5 |
| Pyle Audio | 4 |
| Adire Audio | 3 |
| Timpano Audio | 3 |

## Verifica software

Suite completa **superata**: 107 superati, 0 falliti, 0 saltati.

## Rigenerazione

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py
```

Per aggiornare anche l'esito della suite completa:

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py --run-tests
```

Il comando è di sola lettura sui database e sovrascrive atomicamente soltanto questo report.
