# Load Forge — Registro Fonti Dati & Cataloghi

Questo documento traccia in modo completo e strutturato **tutte le fonti dati, i distributori, i costruttori e i crawler** utilizzati in Load Forge (attuali e storici).

---

## 1. Livello Primario: Database Proprietario Load Forge (`data/catalog_proprietario.json`)
*Questo è l'**unico archivio sicuro, indipendente e autorizzato per la distribuzione pubblica** del software. Contiene parametri T/S di laboratorio verificati e prezzi diretti.*

### 1.1 Costruttori Diretti & Store Ufficiali (T/S + Prezzi)
| Brand / Fonte | URL / Endpoint | Tipologia Componenti | Tool di Acquisizione |
|---|---|---|---|
| **SB Acoustics & Satori** | `https://sbacoustics.com` | Woofer, Midwoofer, Subwoofer Hi-Fi | `tools/enrich_manufacturer_metadata.py` |
| **Dayton Audio** | `https://www.daytonaudio.com` | Subwoofer, Woofer, PMT, Epique | `tools/enrich_manufacturer_metadata.py` |
| **B&C Speakers** | `https://www.bcspeakers.com` | Driver Pro Audio, Subwoofer Neodimio/Ferrite | `tools/enrich_manufacturer_metadata.py` |
| **FaitalPRO** | `https://faitalpro.com` | Driver Pro Audio, Subwoofer High-SPL | `tools/enrich_manufacturer_metadata.py` |
| **Acustica Beyma** | `https://www.beyma.com` | Driver Pro Audio, Studio & Subwoofer | `tools/enrich_manufacturer_metadata.py` |
| **LaVoce Italiana** | `https://www.lavocespeakers.com` | Trasduttori Pro Audio & Bass | `tools/enrich_manufacturer_metadata.py` |
| **SICA Loudspeakers** | `https://www.sica.it` | Woofer e Coassiali Pro/Studio | `tools/enrich_manufacturer_metadata.py` |
| **Visaton** | `https://www.visaton.de` | Componenti Hi-Fi, Car & Industrial | `tools/enrich_manufacturer_metadata.py` |
| **Eminence** | `https://eminence.com` | Pro Audio, Bass Guitar, Home Theater | `tools/enrich_manufacturer_metadata.py` |
| **Celestion** | `https://celestion.com` | Pro Audio, Chitarra/Basso, Subwoofer | `tools/enrich_manufacturer_metadata.py` |
| **Ciare** | `https://www.ciare.com` | Hi-Fi, Car Audio, Pro Audio | `tools/enrich_manufacturer_metadata.py` |
| **PRV Audio** | `https://prvaudio.com` | Pro Audio & Car Audio SPL | `tools/enrich_manufacturer_metadata.py` |
| **Eighteen Sound (18 Sound)** | `https://www.eighteensound.it` | Subwoofer Pro & High-End Touring | `tools/enrich_manufacturer_metadata.py` |
| **Markaudio** | `https://www.markaudio.com` | Alpair, Pluvia (Full-Range & Woofer) | `tools/enrich_manufacturer_metadata.py` |
| **Tang Band (TB Speaker)** | `https://tb-speaker.com` | Subwoofer Micro & Full-Range | `tools/enrich_manufacturer_metadata.py` |
| **CT Sounds** | `https://www.ctsounds.com` | Subwoofer Car Audio (EXO, Thermo, Meso, Strato, Bio) | `tools/harvest_ctsounds.py` |
| **Rockville Audio** | `https://www.rockvilleaudio.com` | Subwoofer & Driver (Punisher, Destroyer, K9, K6) | `tools/harvest_rockville.py` |
| **Skar Audio** | `https://www.skaraudio.com` | Subwoofer Car Audio (EVL, SDR, SVR, VXF, ZVX, TXL, VD) | `tools/harvest_extra_retailers.py` |
| **Kicker** | `https://www.kicker.com` | Solo-Baric L7S/L7R/L7T, CompQ, CompVX, CompR, CompVR | `tools/enrich_driver_prices.py` |
| **DS18** | `https://www.ds18.com` | Subwoofer & Midrange Car Audio | `tools/harvest_extra_retailers.py` |
| **NVX** | `https://nvx.com` | Subwoofer Car Audio Serie VC / VSW | `tools/harvest_nvx.py` |
| **Bomber Speakers** | `https://www.bomber.com.br` | Subwoofer e Woofer regionali America Latina | `tools/harvest_bomber_regional.py` |
| **REDCATT** | `https://redcatt.com` | Driver e Coassiali OEM / Pro Audio | `tools/harvest_extra_retailers.py` |
| **ZTZ Audio** | `https://www.ztzaudio.com` | Driver LF Ferrite Pro Audio | `tools/crawl_ztzaudio_lf.py` |
| **Great Plains Acoustics / TAD** | `https://archive.greatplainsacoustics.com` | Driver Altec Heritage & TAD Studio | `tools/import_heritage_drivers.py` |

---

## 2. Distributori Ufficiali & Retailer Specializzati (Listini & Disponibilità)

### 2.1 Retailer Ufficiali Europa (EUR € / GBP £)
* **SoundImports.eu** (`https://www.soundimports.eu`): Distributore ufficiale per Dayton Audio, SB Acoustics, Scan-Speak, SEAS, Peerless, Morel, Purifi, Tang Band. (*Crawler: `tools/enrich_driver_prices.py` via schema.org JSON-LD*).
* **ToutLeHautParleur (TLHP)** (`https://en.toutlehautparleur.com`): Principale distributore europeo per B&C, FaitalPRO, Beyma, Eighteen Sound, Ciare, Celestion, RCF, SICA, Oberton, BMS, PHL Audio. (*Crawler: `tools/harvest_toutlehautparleur.py`*).
* **Sound Auto Concept** (`https://soundautoconcept.com`): Distributore Car Audio europeo per Ground Zero, Gladen, Hertz, Audison, Focal, DD Audio, Deaf Bonce, HiFonics. (*Crawler: `tools/harvest_soundautoconcept.py`*).
* **Audiophonics.fr** (`https://www.audiophonics.fr`): Componenti Hi-Fi DIY, Purifi, Accuton, Dayton Audio.
* **Lautsprechershop.de (Strassacker)** (`https://www.lautsprechershop.de`): Visaton, Audax, Seas, Scan-Speak, Monacor.
* **Blue Aran UK** (`https://www.bluearan.co.uk`): Precision Devices, Celestion, Fane, Beyma, Eminence (*Sitemap JSON-LD crawler*).
* **Retailer Nazionali Specializzati**:
  * *Topservicepro.it* & *StrumentiMusicali.net* (Italia - Ricambi Pro Audio / RCF / FBT)
  * *LeanAudio.co.uk*, *KJF Audio*, *Willys-HiFi.com* (Regno Unito)
  * *DIYspeakers.eu* & *Audio-Hi.Fi* (Europa dell'Est / Nordics)
  * *Hogtalarshoppen.se* (Svezia)
  * *Analoghifi.no* (Norvegia)

### 2.2 Retailer Ufficiali Nord America & Globale (USD $)
* **Parts Express** (`https://www.parts-express.com`): Dayton Audio, GRS, Eminence, Peerless (*SuiteCommerce API crawler: `tools/harvest_partsexpress.py`*).
* **Madisound Speaker Store** (`https://www.madisoundspeakerstore.com`): Scan-Speak, SEAS, SB Acoustics, Morel, Fostex, Accuton (*CollectionPage JSON-LD crawler*).
* **AudioVideoParts** (`https://www.audiovideoparts.com`): Prezzi e componenti DIY.

---

## 3. Dataset Storici / Aggregatori Terzi (Tier Esterni Opzionali)
*Questi dataset risiedono in file separati e **non vengono inclusi nella build pubblica autonoma** di Load Forge.*

1. **Loudspeaker Database Import** (`data/catalog_lsdb.json`):
   * *Origine*: `loudspeakerdatabase.com`
   * *Tool*: `tools/import_loudspeaker_database.py`
   * *Uso*: Archivio di consultazione estesa per sviluppo locale.
2. **VituixCAD Online Database** (`data/catalog_vituixcad.json`):
   * *Origine*: `kimmosaunisto.net/Software/VituixCAD`
   * *Tool*: `tools/import_vituixcad_database.py`
   * *Uso*: Dataset aggregato pubblico per simulazioni cross-software.
3. **Speaker Box Lite Public Database** (`data/catalog_speakerboxlite.json`):
   * *Origine*: `speakerboxlite.com`
   * *Tool*: `tools/import_speakerboxlite_database.py`
   * *Uso*: Archivio comunitario sottoposto a validazione fisica automatica di $S_d, V_{as}, Q_{ts}$.

---

## 4. Riepilogo Pipeline di Validazione & Aggiornamento Dati
* **Validatore di Coerenza Dati (< 0.1s)**:
  ```bash
  .venv/bin/python -c "import sys; sys.path.insert(0, 'src'); import presets; presets._load_manufacturer_presets.cache_clear(); p, _ = presets._load_manufacturer_presets(); print(f'✓ {len(p)} preset verificati.')"
  ```
* **Cache Binaria Atomica**: Ogni catalogo JSON produce una copia `.cache.pickle` validata tramite `mtime` per un boot istantaneo (0.07s).
