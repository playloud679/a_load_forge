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
| **Kartesian** | `https://www.kartesian-acoustic.com` | Subwoofer & Coassiali Studio/Hi-End francesi (Sub120, Sub150) | `tools/batch_harvest_global_manufacturers.py` |
| **Volt Loudspeakers** | `https://voltloudspeakers.co.uk` | Subwoofer da studio Radial Chassis UK (RV2501, RV3143, RV3863, RV4504) | `tools/batch_harvest_global_manufacturers.py` |
| **Stereo Integrity** | `https://stereointegrity.com` | Subwoofer SQ & Home Theater USA (SQL-12, SQL-15, HT-18 v3, BM-11) | `tools/batch_harvest_global_manufacturers.py` |
| **Eros Alto Falantes** | `https://www.eros.com.br` | Woofer/Sub Pancadão & High-SPL Brasile (Target Bass, SDS, Hammer) | `tools/batch_harvest_global_manufacturers.py` |
| **Triton Alto Falantes** | `https://www.tritonaltofalantes.com.br` | Trasduttori High-Efficiency Brasile (Shocker, TR 1550, Pro) | `tools/batch_harvest_global_manufacturers.py` |
| **7Driver** | `https://www.7driver.com.br` | Trasduttori Pro Audio/Pancadão Brasile (Thunder, Bass) | `tools/batch_harvest_global_manufacturers.py` |
| **GRS** | `https://www.parts-express.com` | Subwoofer e Woofer DIY Parts Express (SW-4, SW-4HE, FR-8) | `tools/batch_harvest_global_manufacturers.py` |
| **Great Plains Acoustics / TAD** | `https://archive.greatplainsacoustics.com` | Driver Altec Heritage & TAD Studio | `tools/import_heritage_drivers.py` |
| **Purifi Audio** | `https://purifi-audio.com` | Woofer & Subwoofer Ultra-Low Distortion Danesi (PTT4.0, PTT5.25, PTT6.5, PTT8.0, PTT10) | `tools/harvest_high_end_reference_drivers.py` |
| **Morel Loudspeakers** | `https://www.morelhifi.com` | Subwoofer Ultimate & Titanium (UW 958/1058/1258, TiCW series) | `tools/harvest_high_end_reference_drivers.py` |
| **CSS Audio** | `https://www.css-audio.com` | Subwoofer XBL2 brevettati USA (SDX12, SDX10, SDX7) | `tools/harvest_high_end_reference_drivers.py` |
| **Supravox** | `https://www.supravox.fr` | Woofer Alta Efficienza Heritage Francia (215 GMF, 285 GMF, 400 GMF) | `tools/harvest_high_end_reference_drivers.py` |
| **AudioTechnology / Skaaning** | `https://audiotechnology.dk` | Trasduttori Ultra High-End Danesi (Flexunits 6H52/8H52/10H77/12H77) | `tools/harvest_worldwide_production.py` |
| **Accuton (Thiel & Partner)** | `https://accuton.com` | Driver in Ceramica e Diamante Germania (C158, C220, C280) | `tools/harvest_worldwide_production.py` |
| **PHL Audio** | `https://phlaudio.com` | Trasduttori Studio & Pro Audio Francia (2440, 3020, 5010, 7010) | `tools/harvest_worldwide_production.py` |
| **Precision Devices** | `https://precision-devices.com` | Subwoofer Heavy-Duty Pro UK (PD.1850/3, PD.2150, PD.2450) | `tools/harvest_worldwide_production.py` |
| **BMS Speakers** | `https://bmsspeakers.com` | Subwoofer Pro Neodimio Germania (18N862, 15N850) | `tools/harvest_worldwide_production.py` |
| **Oberton** | `https://oberton.com` | Subwoofer e Driver Pro Audio Bulgaria (18XB1500, 15XB1200) | `tools/harvest_worldwide_production.py` |
| **Incriminator Audio** | `https://incriminatoraudio.com` | Subwoofer Extreme Heavy Excursion USA (Death Penalty 15/18) | `tools/harvest_worldwide_production.py` |
| **Fi Car Audio** | `https://ficaraudio.com` | Subwoofer High-BL Custom USA (Q v4 18, BTL v3 18) | `tools/harvest_worldwide_production.py` |
| **Snake Pro & Hard Power** | `https://snakepro.com.br` | Pancadão & Trio Elétrico Brasile (ESX 415, HP 1950) | `tools/harvest_worldwide_production.py` |
| **Lii Audio / Lii Song** | `https://lii-audio.com` | Dipolo Open Baffle & Full Range Alta Sensibilità (W-15, Fast-10) | `tools/harvest_worldwide_production.py` |
| **RCF** | `https://www.rcf.it` | Precision Transducers Pro Audio Italia (LF18X401, LF18N401, LF15X401, L18P300) | `tools/harvest_pro_audio_giants.py` |
| **Fane International** | `https://fane-international.com` | Subwoofer e Woofer Pro Audio UK (Colossus 18XB, 18-1000, 15XB) | `tools/harvest_pro_audio_giants.py` |
| **Radian Audio** | `https://radianaudio.com` | Driver Coassiali & Subwoofer USA (5215B, 2216) | `tools/harvest_pro_audio_giants.py` |
| **Eton** | `https://eton-gmbh.com` | Coni Hexacone Symphony II Germania (12-212, 11-581, 8-212, 7-212) | `tools/harvest_european_audiophile_giants.py` |
| **ATC Loudspeakers** | `https://atc.audio` | Trasduttori Super Linear Studio UK (SB75-375SC, SB75-314SC, SB75-234SC) | `tools/harvest_european_audiophile_giants.py` |
| **Davis Acoustics** | `https://davis-acoustics.com` | Coni Carbon-Kevlar & Full-Range Francia (20DE8, 25SCA10W) | `tools/harvest_european_audiophile_giants.py` |
| **Audax** | `https://audax.com` | Aerogel HD & Paper Pro Francia (HM210Z0, PR380M0) | `tools/harvest_european_audiophile_giants.py` |
| **SB Audience** | `https://sbaudience.com` | Linea Pro Audio SB Acoustics (Nero-21SW1100, Nero-18SW800, Bianco-18SW450) | `tools/harvest_european_audiophile_giants.py` |
| **Digital Designs (DD Audio)** | `https://ddaudio.com` | Subwoofer High-BL Car Audio USA (9918 ESP, 9515 ESP, 3512 ESP) | `tools/harvest_us_spl_giants.py` |
| **B2 Audio** | `https://b2audio.com` | Subwoofer Extreme SPL Danimarca/USA (Rage XL 15/18 v2) | `tools/harvest_us_spl_giants.py` |
| **Resilient Sounds** | `https://resilientsounds.com` | Subwoofer Heavy Bass USA (Platinum 18, Gold 15) | `tools/harvest_us_spl_giants.py` |
| **Sound Solutions Audio (SSA)** | `https://store.soundsolutionsaudio.com` | Subwoofer Handcrafted USA (Evil 18, ZCON 15) | `tools/harvest_us_spl_giants.py` |
| **Deaf Bonce (Alphard Audio)** | `https://alphardaudio.us` | Apocalypse, Machete, Hannibal, Black Hydra SPL/SQL | `tools/autonomous_crawler_daemon.py` |
| **Sundown Audio** | `https://sundownaudio.com` | Nightshade v6, X-Series v4, U-Series, SA-Series | `tools/autonomous_crawler_daemon.py` |
| **Gately Audio** | `https://gatelyaudio.com` | Subwoofer & Coassiali High Power USA | `tools/autonomous_crawler_daemon.py` |

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
