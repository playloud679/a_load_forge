# Stato database manufacturer driver

> File generato automaticamente: non modificare a mano i numeri.  
> Rigenerazione: `.venv/bin/python tools/generate_manufacturer_database_report.py`

Generato: **2026-07-28T01:09:24+02:00**
Database letto: `data/manufacturer_drivers.json` (modificato 2026-07-28T01:09:07+02:00)

## Sintesi

Il catalogo contiene **4.807 driver** di **68 produttori**. L'app ne espone **4.796** dopo il controllo `Sd`/diametro nominale. I sette parametri fondamentali sono completi al **100.00%** dei record. I prezzi verificabili coprono il **67.15%**.

## Copertura parametri

| Parametro | Presenti | Mancanti | Copertura |
|---|---|---|---|
| Fs | 4.807 | 0 | 100.00% |
| Vas | 4.807 | 0 | 100.00% |
| Qts | 4.807 | 0 | 100.00% |
| Qms | 4.807 | 0 | 100.00% |
| Qes | 4.807 | 0 | 100.00% |
| Re | 4.807 | 0 | 100.00% |
| Sd | 4.807 | 0 | 100.00% |
| Mms | 4.804 | 3 | 99.94% |
| Cms | 4.806 | 1 | 99.98% |
| BL | 4.807 | 0 | 100.00% |
| Xmax | 4.484 | 323 | 93.28% |
| Potenza Pe | 4.386 | 421 | 91.24% |
| Le | 4.544 | 263 | 94.53% |
| Dimensione nominale | 4.807 | 0 | 100.00% |

## Prezzi

- Driver con prezzo: **3.228/4.807** (67.15%).
- Senza prezzo: **1.579**; marcati senza abbinamento commerciale affidabile: **1.641**.
- Prezzi con URL: **3.228**; con provenienza strutturata: **3.228**.
- Indice commerciale separato: **8.605** offerte; aggiornato `2026-07-27T18:35:04+00:00`.
- Valute: USD 1.536, EUR 1.360, GBP 317, SEK 15.

I record senza corrispondenza sicura restano intenzionalmente senza prezzo: il report non considera stime o medie inventate.

## Qualità e provenienza

- Record con almeno un parametro fondamentale non valido: **0**.
- Conflitti fisici `Qms <= Qts`: **0**.
- Vecchi valori Pe invalidati perché privi di unità W/kW: **87**.
- Correzioni tracciate `Sd`: **26**; dimensione nominale: **591**.
- Record esclusi per conflitto irrisolto `Sd`/diametro nominale: **11**.
- Provenienza esplicita da refresh: Xmax **188**, Pe **879**, Le **264**.
- Campi derivati tracciati: Qes **4.647**, Cms **2.872**, size_in **2.662**, BL **775**, Mms **197**, Sd **25**, Re **11**, Qms **3**, Qts **2**, Vas **1**.

Le derivazioni vengono conteggiate solo quando memorizzate in `website_fields.derived_fields`; i valori pubblicati e quelli derivati restano distinguibili.

### Conflitti Sd/dimensione nominale esclusi

| Produttore | Modello | Nominale in | Sd cm² | Ø effettivo in |
|---|---|---|---|---|
| Tang Band | W6-2313 6-1/2" Coaxial Full-Range Woofer | 6.5 | 25.67 | 2.25 |
| Tang Band | W1-1815SA 1" Neodymium Full Range Driver | 1 | 75 | 3.85 |
| B&C Speakers | B&C 18RBX100 18" Professional Subwoofer 8 Ohm | 18 | 189.88 | 6.12 |
| Celestion | PowerProX18 18" Professional Subwoofer | 18 | 187.6 | 6.08 |
| B&C Speakers | B&C 18RBX100-4 18" Professional Subwoofer 4 Ohm | 18 | 189.88 | 6.12 |
| B&C Speakers | B&C 10MBX64 10" Professional Neodymium Woofer 8 Ohm | 10 | 53.63 | 3.25 |
| PRV Audio | MT2.2TWB-4 Moto Series 2.25" Short Horn Black Tweeter 4 Ohm | 2.25 | 391 | 8.78 |
| PRV Audio | MT2.2TWC-4 Moto Series 2.25" Short Horn Chrome Tweeter 4 Ohm | 2.25 | 391 | 8.78 |
| FaitalPRO | 8HX210 8" Coaxial Speaker 8 Ohm | 8 | 1213 | 15.47 |
| PRV Audio | MT2.7TWB-4 Moto Series 2.75" Short Horn Chrome Tweeter 4 Ohm | 2.75 | 391 | 8.78 |
| SEAS | W26FX001 | 10 | 50 | 3.14 |

## Deduplicazione

Dry-run corrente: **4.807 → 4.793**, duplicati conservativi rimovibili **14**.

L'ultimo report applicato ha ridotto il catalogo da 4.697 a 4.424 record (273 rimossi).

## Principali fonti

| Fonte | Driver | Quota |
|---|---|---|
| Parts Express API | 1.168 | 24.30% |
| SoundImports retailer | 913 | 18.99% |
| Manufacturer website | 449 | 9.34% |
| SICA official | 146 | 3.04% |
| 18Sound | 141 | 2.93% |
| B&C Speakers Remix crawler | 140 | 2.91% |
| Ciare crawler | 117 | 2.43% |
| Bomber official | 108 | 2.25% |
| FaitalPRO Official Excel | 107 | 2.23% |
| Eminence crawler | 96 | 2.00% |
| Visaton crawler | 93 | 1.93% |
| PHL Audio official PDF | 93 | 1.93% |
| SB Acoustics crawler | 87 | 1.81% |
| Beyma Catalog | 86 | 1.79% |
| P.Audio official | 86 | 1.79% |

## Lacune prioritarie per produttore

### Xmax

| Produttore | Record mancanti |
|---|---|
| DS18 | 49 |
| SICA | 42 |
| B&C Speakers | 33 |
| BMS | 28 |
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
| Pride | 4 |

### Potenza Pe

| Produttore | Record mancanti |
|---|---|
| 18Sound | 148 |
| Eminence | 69 |
| Wavecor | 43 |
| BMS | 33 |
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
| Rockville | 36 |
| BMS | 35 |
| HiVi | 29 |
| Pride | 24 |
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
| Celestion | 5 |

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
