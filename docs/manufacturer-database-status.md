# Stato database manufacturer driver

> File generato automaticamente: non modificare a mano i numeri.  
> Rigenerazione: `.venv/bin/python tools/generate_manufacturer_database_report.py`

Generato: **2026-08-04T23:41:44+02:00**
Database letto: `data/manufacturer_drivers.json` (modificato 2026-08-04T23:41:37+02:00)

## Sintesi

Il catalogo contiene **5.277 driver** di **80 produttori**. L'app ne espone **5.194** dopo il controllo `Sd`/diametro nominale. I sette parametri fondamentali sono completi al **100.00%** dei record. I prezzi verificabili coprono il **81.75%**.

## Copertura parametri

| Parametro | Presenti | Mancanti | Copertura |
|---|---|---|---|
| Fs | 5.277 | 0 | 100.00% |
| Vas | 5.277 | 0 | 100.00% |
| Qts | 5.277 | 0 | 100.00% |
| Qms | 5.277 | 0 | 100.00% |
| Qes | 5.277 | 0 | 100.00% |
| Re | 5.277 | 0 | 100.00% |
| Sd | 5.277 | 0 | 100.00% |
| Mms | 5.273 | 4 | 99.92% |
| Cms | 5.207 | 70 | 98.67% |
| BL | 5.276 | 1 | 99.98% |
| Xmax | 4.977 | 300 | 94.31% |
| Potenza Pe | 4.943 | 334 | 93.67% |
| Le | 4.966 | 311 | 94.11% |
| Dimensione nominale | 5.268 | 9 | 99.83% |

## Prezzi

- Driver con prezzo: **4.314/5.277** (81.75%).
- Senza prezzo: **963**; marcati senza abbinamento commerciale affidabile: **921**.
- Prezzi con URL: **4.301**; con provenienza strutturata: **4.143**.
- Indice commerciale separato: **36.308** offerte; aggiornato `2026-08-04T21:10:30+00:00`.
- Valute: EUR 2.073, USD 1.884, GBP 283, BRL 28, SEK 18, JPY 7, THB 5, INR 5, ZAR 3, CZK 1, NZD 1, CHF 1, UAH 1, COP 1, VND 1, AUD 1, CAD 1.

I record senza corrispondenza sicura restano intenzionalmente senza prezzo: il report non considera stime o medie inventate.

## Qualità e provenienza

- Record con almeno un parametro fondamentale non valido: **0**.
- Conflitti fisici `Qms <= Qts`: **0**.
- Vecchi valori Pe invalidati perché privi di unità W/kW: **90**.
- Correzioni tracciate `Sd`: **26**; dimensione nominale: **847**.
- Record esclusi per conflitto irrisolto `Sd`/diametro nominale: **83**.
- Provenienza esplicita da refresh: Xmax **212**, Pe **1.033**, Le **281**.
- Campi derivati tracciati: Qes **4.831**, Cms **2.945**, size_in **2.917**, BL **838**, Mms **281**, Sd **89**, Re **13**, Qts **3**, Qms **3**, Vas **1**.

Le derivazioni vengono conteggiate solo quando memorizzate in `website_fields.derived_fields`; i valori pubblicati e quelli derivati restano distinguibili.

### Conflitti Sd/dimensione nominale esclusi

| Produttore | Modello | Nominale in | Sd cm² | Ø effettivo in |
|---|---|---|---|---|
| Dayton Audio | CE40-4 | 1 | 7.07 | 1.18 |
| Dayton Audio | CE48-4 | 2 | 9.1 | 1.34 |
| Dayton Audio | DML25-4 | 2 | 4.64 | 0.96 |
| Dayton Audio | RS100P-4 | 4 | 36.3 | 2.68 |
| Dayton Audio | RS100P-8 | 4 | 37.4 | 2.72 |
| Dayton Audio | CE38M-8 | 1.5 | 4.91 | 0.98 |
| GRS | NRT50-8 2" Extended Range Driver 8 Ohm | 2 | 8.9 | 1.33 |
| Tang Band | W1-1942S 1" Neodymium Full Range Driver | 1 | 9 | 1.33 |
| Tang Band | W6-2313 6-1/2" Coaxial Full-Range Woofer | 6.5 | 25.67 | 2.25 |
| Tang Band | W1-1815SA 1" Neodymium Full Range Driver | 1 | 75 | 3.85 |
| Morel | TM4055-8 2" Midrange and 1-1/8" Tweeter Speaker Plate | 2 | 28 | 2.35 |
| Wavecor | SW118WA01 4-1/2" Balanced Drive Paper Cone Subwoofer 4 Ohm | 4.5 | 49 | 3.11 |
| Wavecor | WF120BD05 4-3/4" Balanced Drive Paper/Glass Fiber Cone Mid-Woofer 4 Ohm | 4.75 | 54 | 3.26 |
| B&C Speakers | B&C 18RBX100 18" Professional Subwoofer 8 Ohm | 18 | 189.88 | 6.12 |
| Celestion | PowerProX18 18" Professional Subwoofer | 18 | 187.6 | 6.08 |
| Dayton Audio | CE30MB-16B 1-1/4" Mini Speaker Driver Black 16 Ohm | 1.25 | 3.1 | 0.78 |
| Dayton Audio | ND91-4 3-1/2" Aluminum Cone Full-Range Driver 4 | 3.5 | 30.4 | 2.45 |
| Dayton Audio | PS95-8 3-1/2" Point Source Full-Range Driver 8 | 3.5 | 28.3 | 2.36 |
| Dayton Audio | RS100-8 4" Reference Full-Range Driver | 4 | 35.3 | 2.64 |
| Dayton Audio | RS125-8 5" Reference Woofer | 5 | 52.8 | 3.23 |
| Dayton Audio | RS150-8 6" Reference Woofer | 6 | 85 | 4.10 |
| Dayton Audio | RS75-4 3" Reference Full-Range Driver 4 Ohm | 3 | 12 | 1.54 |
| B&C Speakers | B&C 18RBX100-4 18" Professional Subwoofer 4 Ohm | 18 | 189.88 | 6.12 |
| Dayton Audio | CE40-4 1" Full-Range Speaker Driver 10W 4 ohm | 1 | 7.07 | 1.18 |
| Dayton Audio | CE48-4 2" Full-Range Speaker Driver 5W 4 Ohm | 2 | 9.1 | 1.34 |
| Dayton Audio | ND91-8 3-1/2" Aluminum Cone Full-Range Driver 8 | 3.5 | 30.4 | 2.45 |
| Dayton Audio | RS100P-4 4" Reference Paper Midwoofer 4 Ohm | 4 | 36.3 | 2.68 |
| Dayton Audio | RS125P-4 5" Reference Paper Woofer 4 Ohm | 5 | 54.11 | 3.27 |
| Dayton Audio | RS150P-4A 6" Reference Paper Woofer 4 Ohm | 6 | 85 | 4.10 |
| Dayton Audio | RS75-8 3" Reference Full-Range Driver 8 Ohm | 3 | 15.8 | 1.77 |
| B&C Speakers | B&C 10MBX64 10" Professional Neodymium Woofer 8 Ohm | 10 | 53.63 | 3.25 |
| Celestion | FTX1225 12" Coaxial Full-Range Professional Driver | 12 | 169.1 | 5.78 |
| Dayton Audio | RS100P-8 4" Reference Paper Midwoofer 8 Ohm | 4 | 37.4 | 2.72 |
| Dayton Audio | RS125P-8 5" Reference Paper Woofer 8 Ohm | 5 | 52.8 | 3.23 |
| Dayton Audio | RS150P-8A 6" Reference Paper Woofer 8 Ohm | 6 | 85 | 4.10 |
| Dayton Audio | RS75T-8 3" Reference Full-Range Driver Truncate | 3 | 12 | 1.54 |
| Dayton Audio | CE53N-4 2" Dual Neo Full-Range Speaker Driver 10W 4 Ohm | 2 | 8.55 | 1.30 |
| Dayton Audio | RS100-4 4" Reference Full-Range Driver 4 Ohm | 4 | 35.3 | 2.64 |
| Dayton Audio | RS125-4 5" Reference Woofer 4 Ohm | 5 | 52.8 | 3.23 |
| Dayton Audio | RS150-4 6" Reference Woofer 4 Ohm | 6 | 85 | 4.10 |
| Coast Buyouts | EAS8P324A6 3-1/2" Square Frame Paper Cone Speaker 8 Ohm | 3.5 | 28.27 | 2.36 |
| PRV Audio | MT2.2TWB-4 Moto Series 2.25" Short Horn Black Tweeter 4 Ohm | 2.25 | 391 | 8.78 |
| PRV Audio | MT2.2TWC-4 Moto Series 2.25" Short Horn Chrome Tweeter 4 Ohm | 2.25 | 391 | 8.78 |
| FaitalPRO | 8HX210 8" Coaxial Speaker 8 Ohm | 8 | 1213 | 15.47 |
| PRV Audio | MT2.7TWB-4 Moto Series 2.75" Short Horn Chrome Tweeter 4 Ohm | 2.75 | 391 | 8.78 |
| Tectonic | TEBM36S05-4 1-1/2" Square BMR Full-Range Speaker 4 Ohm | 1.5 | 17.6 | 1.86 |
| Dayton Audio | ND91-8 | 3.5 | 30.4 | 2.45 |
| Dayton Audio | RS100-8 | 4 | 35.3 | 2.64 |
| Dayton Audio | RS125-4 | 5 | 52.8 | 3.23 |
| Dayton Audio | RS125-8 | 5 | 52.8 | 3.23 |
| Dayton Audio | RS125P-4 | 5 | 52.8 | 3.23 |
| Dayton Audio | RS125P-8 | 5 | 52.8 | 3.23 |
| Dayton Audio | RS150-4 | 6 | 85 | 4.10 |
| Dayton Audio | RS150-8 | 6 | 85 | 4.10 |
| Dayton Audio | RS150P-4A | 6 | 85 | 4.10 |
| Dayton Audio | RS150P-8A | 6 | 85 | 4.10 |
| Dayton Audio | RS150T-8 | 6 | 85 | 4.10 |
| Dayton Audio | RS75-4 | 3 | 12 | 1.54 |
| Dayton Audio | RS75-8 | 3 | 12 | 1.54 |
| Dayton Audio | RS75T-8 | 3 | 12 | 1.54 |
| Markaudio | Alpair-12P | 8 | 147.41 | 5.39 |
| Markaudio | CHBW-70 | 5 | 50.2 | 3.15 |
| Markaudio | CHN-110 | 6.75 | 109 | 4.64 |
| Markaudio | CHN-70 | 5 | 50.27 | 3.15 |
| Markaudio | PLUVIA-11 Gold | 7 | 109.359 | 4.65 |
| Markaudio | PLUVIA-11 Grey | 7 | 109.359 | 4.65 |
| Scan-Speak | 10F/4424G00 | 4 | 36 | 2.67 |
| Scan-Speak | 10F/8414G10 | 4 | 36.3 | 2.68 |
| SEAS | FU10RB | 4 | 38.5 | 2.76 |
| SEAS | L12RE/XFC | 5 | 47 | 3.05 |
| SEAS | MU10RB-SL | 4 | 38.5 | 2.76 |
| SEAS | W12CY003 | 4.5 | 50 | 3.14 |
| SEAS | W12CY006 | 4.5 | 50 | 3.14 |
| SEAS | W15CY001 | 5.5 | 75 | 3.85 |
| SEAS | W15LY001 | 5.5 | 75 | 3.85 |
| SEAS | W26FX001 | 10 | 50 | 3.14 |
| Tectonic | TEBM28C10-4/A | 1.125 | 8.55 | 1.30 |
| Wavecor | WF120BD11/12/13/14     4.75 inch die cast, Kevlar/Carbon fibre cone mid/woofers | 4.75 | 48 | 3.08 |
| Wavecor | WF152BD09/10/11/12     6 inch die cast, Kevlar/Carbon fibre cone mid/woofers | 6 | 85 | 4.10 |
| Wavecor | WF182BD13/14/15/16     7 inch die cast, Kevlar/Carbon fibre cone mid/woofers | 7 | 117 | 4.81 |
| MISCO | 100-MR08-01 | 4 | 18.5 | 1.91 |
| MISCO | JC5RTF-B | 5 | 58.1 | 3.39 |
| Eminence Speaker | Eminence Alpha-6CBMRA 6-1/2" Ferrite Sealed Back Midrange Sp | 6.5 | 8.13 | 1.27 |

## Deduplicazione

Dry-run corrente: **5.277 → 5.214**, duplicati conservativi rimovibili **63**.

L'ultimo report applicato ha ridotto il catalogo da 4.697 a 4.424 record (273 rimossi).

## Principali fonti

| Fonte | Driver | Quota |
|---|---|---|
| Parts Express API | 1.352 | 25.62% |
| SoundImports retailer | 913 | 17.30% |
| Manufacturer website | 449 | 8.51% |
| ToutLeHautParleur product page | 213 | 4.04% |
| SICA official | 146 | 2.77% |
| 18Sound | 141 | 2.67% |
| B&C Speakers Remix crawler | 140 | 2.65% |
| Ciare crawler | 117 | 2.22% |
| Bomber official | 108 | 2.05% |
| FaitalPRO Official Excel | 107 | 2.03% |
| Eminence crawler | 96 | 1.82% |
| Visaton crawler | 93 | 1.76% |
| PHL Audio official PDF | 93 | 1.76% |
| SB Acoustics crawler | 87 | 1.65% |
| Beyma Catalog | 86 | 1.63% |

## Lacune prioritarie per produttore

### Xmax

| Produttore | Record mancanti |
|---|---|
| DS18 | 49 |
| SICA | 42 |
| B&C Speakers | 33 |
| Rockville | 25 |
| Fostex | 19 |
| MISCO | 18 |
| Factory Buyouts | 16 |
| Visaton | 12 |
| DC Audio | 12 |
| Wavecor | 11 |
| Atohm | 7 |
| Supravox | 6 |
| Coast Buyouts | 6 |
| BMS | 5 |
| Pride | 4 |

### Potenza Pe

| Produttore | Record mancanti |
|---|---|
| Altec Lansing | 63 |
| Eminence | 62 |
| Wavecor | 43 |
| BMS | 34 |
| Fostex | 19 |
| Bomber | 16 |
| Rockville | 15 |
| Beyma | 11 |
| DC Audio | 10 |
| Supravox | 9 |
| Markaudio | 8 |
| Atohm | 7 |
| SICA | 7 |
| NVX | 7 |
| Visaton | 4 |

### Le

| Produttore | Record mancanti |
|---|---|
| Altec Lansing | 63 |
| Rockville | 36 |
| HiVi | 29 |
| Pride | 24 |
| BMS | 18 |
| Markaudio | 16 |
| Visaton | 14 |
| Ciare | 14 |
| Coast Buyouts | 12 |
| Bomber | 11 |
| Wavecor | 8 |
| Supravox | 7 |
| DC Audio | 7 |
| NVX | 7 |
| Factory Buyouts | 6 |

## Verifica software

Non eseguita durante questa rigenerazione. Usare `--run-tests` per inserire nel report l'esito fresco della suite completa.

## Rigenerazione

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py
```

Per aggiornare anche l'esito della suite completa:

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py --run-tests
```

Il comando è di sola lettura sui database e sovrascrive atomicamente soltanto questo report.
