# MODS — Roadmap migliorie Load Forge

Traccia operativa multi-sessione. Regole d'uso:

- `[ ]` da fare · `[~]` in corso · `[x]` fatto (aggiungere data e commit).
- Lavorare un punto alla volta, rispettando il contratto di CLAUDE.md:
  ogni modifica a `src/*.py` aggiorna `docs/<modulo>.md` + test nella stessa
  sessione; suite completa `.venv/bin/python tests/test_all.py` prima del commit.
- A fine sessione aggiornare questo file (stato + note) così la sessione
  successiva riparte da qui.

---

## 2. Backend

- [ ] **2.1 Split di `src/dccav.py` in moduli**
  Separare motore acustico / catalogo preset / pricing in
  `src/engine.py`, `src/presets.py`, `src/pricing.py` (o simili), mantenendo
  `dccav.py` come facciata compatibile. Aggiornare doc contract
  (`docs/<modulo>.md` per ogni nuovo modulo) e reload-rule Streamlit in
  `ui_app.py`.

- [ ] **2.2 Configurazioni multi-driver**
  N driver in parallelo/serie e isobarico (trasformazioni T/S: isobarico
  dimezza Vas, parallelo raddoppia Sd/Pe e dimezza Re, ecc.).
  Selettore configurazione in sidebar.
  File: `src/dccav.py`, `ui_app.py`, `docs/dccav.md`, `tests/test_all.py`.

- [ ] **2.3 Nuove topologie: bandpass 4°/6° ordine + radiatore passivo**
  Riusare il solver a 2 nodi vettorizzato del DCCAV: bandpass = camera sealed
  + camera ported; PR = ramo porto con massa+compliance+perdita propria.
  Estendere optimizer, Batch LF Finder, preset `.lfp`, metriche e warning.
  Lavoro grosso: spezzare in sotto-sessioni (4° ordine → PR → 6° ordine).

- [ ] **2.4 Batch LF Finder parallelo + cache**
  `ProcessPoolExecutor` per il ranking con optimizer, progress bar reale,
  `st.cache_data` sulle simulazioni ripetute (chiave = firma parametri).
  File: `ui_app.py` (+ eventuale helper in `src/`).

- [ ] **2.5 CI GitHub Actions**
  Workflow che replica il contratto: py_compile, `tests/test_all.py`,
  AppTest Streamlit, `ruff check`. Solo file workflow, nessun cambio runtime.

## 4. Funzioni innovative

- [ ] **4.1 Ottimizzatore price-aware — "miglior basso per euro"**
  Feature distintiva: ranking Batch per €/Hz di estensione, vincolo di budget
  nei goal dell'optimizer, score combinato F3×prezzo (valuta coerente,
  riusare la logica currency-aware esistente).
  File: `src/dccav.py`, `ui_app.py`, `docs/dccav.md`, `tests/test_all.py`.

- [ ] **4.2 Bande di tolleranza Monte Carlo**
  Perturbazione T/S ±10–20% (100–200 run vettorizzati), risposta come banda
  percentile 5–95 attorno alla curva nominale. Toggle in Plot Tools.
  File: `src/dccav.py`, `ui_app.py`, `docs/dccav.md`, `tests/test_all.py`.

- [ ] **4.3 Atlante del design space**
  Heatmap F3/ripple sul piano Vb–Fb (reflex/sealed) o Vtot–fl (DCCAV),
  cliccabile per applicare il punto scelto. Griglia calcolata col solver
  vettorizzato. File: `src/dccav.py`, `ui_app.py`, `docs/dccav.md`,
  `tests/test_all.py`.

- [ ] **4.4 Import impedenza misurata → estrazione T/S**
  Upload ZMA/CSV (REW/DATS), fit di Fs/Qms/Qes/Re; metodo massa aggiunta o
  volume noto per Vas. Confronto curva misurata vs simulata.
  File: nuovo `src/ts_extract.py` + doc + test, `ui_app.py`.

- [ ] **4.5 Export FRD/ZMA**
  Download risposta in `.frd` e impedenza in `.zma` (formati testuali
  standard per VituixCAD/XSim/REW), accanto al CSV esistente.
  File: `ui_app.py` (+ helper), `docs/dccav.md`, `tests/test_all.py`.

- [ ] **4.6 Cut list del mobile**
  Da volumi a dimensioni pannelli (proporzioni configurabili, spessore legno,
  volume occupato da driver/porto/rinforzi) con distinta di taglio
  esportabile. File: nuovo modulo `src/` + doc + test, `ui_app.py`.

---

## Fatto

- [x] **4.7 Classificazione sub puri vs woofer midbass (richiesta utente)** —
  2026-07-13, non ancora committato. Backend: `classify_driver_bandwidth()`
  in `src/dccav.py` → `DriverBandwidthClass` con classe
  (Subwoofer / Woofer / Midbass-capable), corner induttivo
  `f_Le = Re/(2πLe)`, densità di massa `Mms/Sd`, SPL 1W e motivazioni.
  Punteggio: f_Le <400 Hz sub / >800 Hz mid (peso 2); Fs ≤35 / ≥45; Mms/Sd
  ≥0.30 / ≤0.15 g/cm²; SPL1W ≤90 / ≥94 dB (peso 1); verdetto con margine ≥2,
  altrimenti "Woofer"; Le sconosciuta (0) salta l'indicatore. UI: filtro
  "Class" tra i filtri preset (con lru_cache per nome), metriche "VC corner"
  e "Class" nella riga di riferimento con caption delle motivazioni, colonna
  "Class" nel Batch (anche nel CSV). Doc: sezione API con pesi e caveat
  (breakup/direttività non modellati). Test: Dayton RSS315HO-4 → Subwoofer,
  Beyma 12CMV2 → Midbass-capable, f_Le esatto, Le=0 → None; filtro UI e
  AppTest su opzioni selectbox e metriche. Verifica: suite 55 pass / 0 fail.

- [x] **3.5 Batch: sparkline risposta + export CSV tabella** — 2026-07-13,
  non ancora committato. Ogni riga del Batch porta una colonna "Response"
  (`_batch_sparkline`: risposta totale ricampionata a 48 punti, normalizzata
  al picco e limitata a [-30, 0] dB) mostrata con `LineChartColumn` a scala
  fissa, così le sparkline sono confrontabili tra righe. Bottone "Download
  batch CSV" sotto la tabella (colonne visibili, sparkline esclusa). Le righe
  cache di sessioni precedenti senza "Response" degradano senza colonna.
  Attenzione trovata in corso: `_batch_rank_presets` è decorata
  `@st.cache_data` — l'inserimento è stato fatto sopra il decoratore. Test:
  asserzioni su lunghezza/range/roll-off della sparkline nel test batch
  esistente. Verifica: suite 53 pass / 0 fail. **Sezione 3 completa.**

- [x] **3.4 Condivisione design via URL** — 2026-07-13, non ancora
  committato. Bottone "Share via URL" accanto a Save/Load preset: serializza
  `_collect_params()` in JSON → zlib → base64url nel query param `d`; il link
  si copia dalla barra indirizzi ("Clear share link" lo rimuove). All'avvio
  il token viene decodificato una sola volta (guardia
  `_applied_share_token`), applicato e marcato con
  `_mark_auto_alignment_synced()` così l'auto-align non sovrascrive il box
  condiviso; token invalidi degradano con warning senza eccezioni.
  **Bug latente corretto**: `_collect_params`/`_apply_loaded_params`
  includevano le chiavi dei bottoni nudge (`*_minus_3`/`*_plus_3`, stesso
  prefisso box_/reflex_/sealed_), che al load facevano crashare Streamlit
  (`StreamlitValueAssignmentNotAllowedError`) — colpiva anche i preset .lfp
  salvati da app avviata; ora filtrate con `_is_param_key()`. Test AppTest:
  share → token in URL → decodifica coerente → sessione nuova con lo stesso
  URL ripristina load type/driver/box → token invalido = warning. Verifica:
  suite 53 pass / 0 fail.

- [x] **3.3 Riorganizzazione a tab + `st.fragment`** — 2026-07-13, non ancora
  committato. Sei tab: Response / Excursion / Impedance / Ports / Group Delay
  / Batch LF Finder (il Batch passa da expander a tab). Le checkbox
  mostra/nascondi per grafico (Exc./Z/Ports/GD) sono state rimosse: il tab
  stesso è il selettore; i pen delle tracce risposta + controlli cursore +
  pin/compare/MIL vivono nel tab Response, i pen dei porti + tabella Port
  Geometry nel tab Ports. Response e Ports sono `@st.fragment`: interagire
  con pen/cursori/pin/compare ri-esegue solo il fragment, non l'intera app
  (niente ri-simulazione, `_chart_signature` ricalcolata dentro il fragment).
  I warning e le righe metriche restano sopra i tab, sempre visibili.
  Chiavi rimosse: `plot_show_excursion/impedance/ports/gd`. Doc `dccav.md`
  aggiornata (GD tab). Test GD adattato al tab; tutti gli altri AppTest
  passano invariati (accesso flatten). Verifica: suite 52 pass / 0 fail.

- [x] **3.2 Confronto 4 topologie in un click** — 2026-07-13, non ancora
  committato. Toggle "Compare loads" accanto ai bottoni pin. Rivisto su
  feedback utente: le quattro curve totali (DCCAV/reflex/sealed/baffle a pari
  volume) vengono sovrapposte NEL grafico principale al posto delle tracce
  normali; in modalità confronto le checkbox Total/Cone/Lower port/MOL sono
  disabilitate (si vedono solo i totali). Cursori F3/F6/F10 e pin restano
  attivi sul carico corrente. Il carico attivo usa il box esatto corrente; gli altri usano
  gli starter standard vincolati allo stesso Vtot (`_batch_dccav_box` per il
  DCCAV, Vb=Vtot Fb=Fs per il reflex, Vb=Vtot per il sealed); con baffle
  infinito attivo il volume di confronto è Vas. Ogni topologia fallita viene
  saltata con log. Rispetta tensione e resistenza serie della simulazione.
  Solo `ui_app.py`. Test: helper puro (4 serie finite, volume esatto, carico
  attivo bit-identico alla simulazione diretta) + AppTest sul subheader.
  Verifica: suite 52 pass / 0 fail.

- [x] **3.1 Overlay A/B — "Pin curva corrente"** — 2026-07-13, non ancora
  committato. Bottoni "Pin response"/"Clear pin" sopra il grafico risposta:
  lo snapshot (label + frequenze + SPL totale) vive in
  `session_state["pinned_response"]` (solo sessione, non nei .lfp), la curva
  pinnata è tratteggiata grigia con tooltip dedicato e caption descrittiva
  (carico · preset · box). Sopravvive a cambi di driver/carico/allineamento;
  la chiave `pinned_` è entrata nella firma dei chart per il re-render. Solo
  `ui_app.py` (nessun cambio a src/, doc contract non toccato). Test AppTest:
  pin → snapshot presente e caption visibile, cambio carico → overlay
  sopravvive, clear → snapshot rimosso. Verifica: suite 51 pass / 0 fail.

- [x] **1.5 Igiene repo** — 2026-07-13, commit `3e3d424`. Rimosso il
  transcript spurio dalla root; tracciati `assets/load_forge_header.png` e
  `tools/run_price_enrichment_cycle.py` (entrambi referenziati dal README);
  `.gitignore` aggiornato con i lock/tmp del file prezzi. Il lavoro feature
  della sessione resta volutamente non committato.

- [x] **1.4 Resistenza serie (ampli + cavo + DCR crossover)** — 2026-07-13,
  non ancora committato. Backend: helper `_electrical_source()` condiviso;
  parametro `series_r_ohm=0.0` sui quattro simulatori (drive con Re+Rs,
  damping elettrico Bl²/(Re+Rs) → Qes/Qts effettivi più alti, impedenza vista
  dalla sorgente inclusa Rs); `_limit_curves` con partitore resistivo sul
  limite termico (potenza riportata = quota sul Re del driver). UI: input
  "Series R (ohm)" nella sezione Simulation (chiave `sim_series_r_ohm`,
  persistita in .lfp), con tooltip; optimizer e Batch restano a 0 Ω
  (documentato — possibile follow-up estenderli). Test: shift ~2 Ω del minimo
  di impedenza, riduzione drive, variazione di damping non piatta, cap
  termico lato driver, rifiuto valori negativi, percorso sealed/IB/DCCAV +
  AppTest sul metric Min impedance (0 → 4 Ω). Verifica: suite completa
  50 pass / 0 fail.

- [x] **1.3 Metriche derivate: sensibilità, η₀, EBP** — 2026-07-13, non
  ancora committato. Backend: `driver_reference_metrics()` →
  `DriverReferenceMetrics(eta0, spl_1w_db, spl_2v83_db, ebp_hz)` con formule
  classiche derivate dalle costanti del modulo. UI: seconda riga di metriche
  sotto quelle derivate (Eta0 ref, SPL 1W/1m, SPL 2.83V/1m, EBP) + caption con
  lettura topologica dell'EBP (<50 sealed, 50–100 entrambi, >100 ported).
  Test: formule vs `complete_driver` sul KEF dell'articolo + AppTest sulla
  riga di metriche. Verifica: suite completa 48 pass / 0 fail.

- [x] **1.2-bis Warning porto auto-esplicativo** — 2026-07-13 (feedback
  utente sullo screenshot: il messaggio "increase the port diameter" sembrava
  incoerente). Nuovi helper `port_max_tuning_hz()` (tetto di accordatura a
  lunghezza zero) e `port_min_diameter_cm()` (diametro minimo per il tuning
  richiesto), inversi esatti di `port_length_cm()` al bordo L=0. Il warning
  ora cita i numeri: "a 4.0 cm opening in 16.7 L tunes at most to ~81 Hz;
  reaching 127.6 Hz needs ≥ 9.8 cm". Test round-trip helper + AppTest sul
  messaggio. La fisica era corretta: accordature alte su volumi grandi
  richiedono porti larghi e corti.

- [x] **1.2 Velocità aria nel porto + warning chuffing** — 2026-07-13, non
  ancora committato. Backend: `port_air_velocity_ms()` (|U|/S in m/s, porta
  lower/upper), `port_length_cm()` (Helmholtz con correzioni di estremità:
  1.463·r default, 1.7·r per il porto superiore DCCAV, valore ≤0 = diametro
  troppo piccolo) e costante `PORT_VELOCITY_GUIDELINE_MS` (5% di c ≈ 17 m/s).
  UI: expander "Port geometry" (diametri vent/upper/lower, 0 = off, default
  5 cm, chiavi `reflex_port_d_cm`/`box_port_d_h_cm`/`box_port_d_l_cm`
  persistite in .lfp), tabella "Port Geometry" (diametro, lunghezza, picco
  m/s, frequenza del picco) e warning chuffing/lunghezza-non-positiva tra i
  model warnings. Doc: nuove sezioni API + elenco test. Test nuovi: round-trip
  Helmholtz + scaling area (backend) e warning small-vent (AppTest).
  Verifica: py_compile OK, test mirati 17 pass, AppTest OK, suite completa
  46 pass / 0 fail.

- [x] **1.1 Grafico Group Delay in UI** — 2026-07-13, non ancora committato.
  Backend: helper `group_delay_ms()` e colonna `group_delay_ms` nel CSV
  export. UI attuale: tab dedicato "Group Delay" nella vista a tab con
  grafico `_plot_group_delay()` e traccia colore dedicata; non usa più la
  vecchia checkbox `GD` dei Plot Tools. Doc aggiornata (`docs/dccav.md`,
  sezione `group_delay_ms` + elenco test). Test nuovi: "DCCAV group delay is
  finite and exported to CSV" e "UI group-delay tab renders the Group Delay
  chart". Verifica: py_compile OK, `-m dccav` 15 pass, AppTest OK, suite
  completa 44 pass / 0 fail.
