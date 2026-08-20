# MODS — Roadmap migliorie Load Forge

Traccia operativa multi-sessione. Regole d'uso:

- Ultimo aggiornamento: **2026-08-21**. Release corrente: **0.8.26**.
- `[ ]` da fare · `[~]` in corso · `[x]` fatto (aggiungere data e commit).
- Lavorare un punto alla volta, rispettando il contratto di `AGENTS.md`:
  ogni modifica a `src/*.py` aggiorna `docs/<modulo>.md` + test nella stessa
  sessione; suite completa `.venv/bin/python tests/test_all.py` prima del commit.
- A fine sessione aggiornare questo file (stato + note) così la sessione
  successiva riparte da qui.

---

## 1. Costruzione & CAD Fisico (Dimensionamento Mobile)

- [ ] **1.1 Cut list e dimensionamento 2D del mobile (Carpenteria)**
  Da volumi netti ($V_b, V_h, V_l$) a quote fisiche esterne/interne dei pannelli.
  Configurazione spessore legno (MDF/multistrato 15–30 mm), offset volume
  occupato dal cestello/magnete del driver, ingombro volumetrico dei condotti
  e rinforzi interni (*bracing*). Proporzioni consigliate anti-modi stazionari
  interni e distinta di taglio esportabile (PDF / SVG / CSV).
  File: nuovo modulo `src/cabinet.py` (o simile) + doc + test, `ui_app.py`.

- [ ] **1.2 Slot-port & Flared Ports Designer**
  Supporto specifico per condotti rettangolari laminari (*slot-port* a ridosso
  delle pareti con correzione di estremità dedicata $k \approx 2.22$) e condotti
  svasati (*aeroport*). Calcolo della resistenza acustica non-lineare e perdite
  di compressione ad alte velocità d'aria.

## 2. Fisica Elettroacustica & Large Signal

- [ ] **2.6 Simulatore filtri DSP & Crossover attivo**
  Integrazione nella catena di simulazione di:
  - Filtro passa-alto subsonico (HPF): Butterworth, Linkwitz-Riley, Bessel (12–48 dB/oct).
  - Filtro passa-basso di incrocio (LPF) con allineamento di fase al crossover.
  - PEQ (Equalizzatore parametrico): fino a 5 bande con guadagno, frequenza e Q.
  Aggiornamento real-time di curve SPL, escursione cono, MIL/MOL e fase, con
  export dei coefficienti biquad per miniDSP / CamillaDSP.

- [ ] **2.7 Fisica a grande segnale: Compressione termica $R_e(T)$ & non-linearità**
  Modello termico della bobina mobile: calcolo della sovratemperatura in funzione
  di $P_{\text{rms}}$ continua e costante di tempo termica, quantificazione del
  power compression loss in dB e shift dinamico del $Q_{es}(T)$. Stima preliminare
  non-linearità $Bl(x)$, $C_{ms}(x)$ e distorsione armonica (THD 2ª/3ª armonica).

## 3. Calcolo & Ottimizzazioni

- [ ] **3.6 Vettorizzazione & Accelerazione JIT per Bass Match**
  Ottimizzazione spinta dello sweep di calcolo su grandi librerie di driver
  (10.000+ unità) tramite NumPy vettorizzato e/o kernel Numba per rendere la
  scansione multidimensionale istantanea.

## 4. Architettura UI & Moduli

- [ ] **4.8 Refactor modulare di `ui_app.py`**
  Scomposizione del file monolitico (`ui_app.py` ~438 KB) in sottomoduli
  specializzati (`ui/workspace_design.py`, `ui/workspace_bass_match.py`,
  `ui/charts.py`, `ui/components/`) preservando il reload dinamico dei moduli
  `src/` e la stabilità dello stato dei widget Streamlit.

## 5. UX & Social Sharing

- [ ] **5.9 Generatore Social Card & Condivisione Facebook / Forum (Approccio Ibrido)**
  Generazione automatica di un'infografica ad alto contrasto (PNG 1200x630) per
  Facebook/forum con grafico SPL, metriche chiave ($V_b, F_b, F_3, X_{\max}$,
  condotto) e QR Code/link per riaprire il simulatore. Snippet testuale pronto per
  il copia-incolla con emoji, pulsante nativo "Condividi su Facebook" e download
  "Project Bundle" (.lfp + PNG + FRD/ZMA).
  Doc: `docs/social-api-hosting-strategy.md`.

## 6. SaaS, API & Hosting Low-Cost

- [~] **6.1 Open Beta autenticata + crawler agent separato** — working tree.
  Implementati: gate OIDC opt-in, account locali SQLite per dev, persistenza
  progetti Firestore/in-memory isolata per tenant, revisioni ottimistiche e
  Save/Load manuali. `LOAD_FORGE_OPEN_BETA_ENABLED` concede accesso Pro
  temporaneo. Crawler Cloud Run Job indipendente con robots-aware crawl.
  Documentazione: `docs/saas.md`, `docs/saas-strategy.md`,
  `docs/crawler-agent-service.md`, `docs/deploy-cloudrun.md`.
  **Prossimo gate:** collaudare OIDC e Firestore sul servizio Cloud Run reale,
  predisporre service account/bucket/manifest del crawler e telemetria minima
  conforme alla privacy.

- [ ] **6.2 Esposizione API REST Headless (FastAPI) per App Mobile Android / iOS**
  Microservizio FastAPI leggero (`api_app.py` o cartella `api/`) che importa
  direttamente `src/acoustics.py`, `src/engine.py`, `src/ranking.py`, `src/presets.py`.
  Endpoint REST stateless: `/api/v1/simulate`, `/api/v1/optimize`, `/api/v1/bass-match`,
  `/api/v1/drivers`. Predisposizione per client mobile multipiattaforma (Flutter /
  React Native) con grafici vettoriali touch a 120Hz.
  Doc: `docs/social-api-hosting-strategy.md`.

- [ ] **6.3 Hosting Low-Cost / Zero-Cost (Alternativa economica a Cloud Run)**
  Transizione da serverless con costi a consumo non controllati a hosting a costo
  fisso o gratuito: Hetzner Cloud VPS (~3.80 €/mese fisso, 2 vCPU, 4 GB RAM, 20 TB
  traffico) o Oracle Cloud Always Free (fino a 4 core ARM, 24 GB RAM, 100% gratis).
  Stack di produzione Docker Compose + Caddy con SSL automatico Let's Encrypt
  per far convivere Web App Streamlit, FastAPI e database su un singolo host.
  Doc: `docs/social-api-hosting-strategy.md`.

## Note e prototipi accantonati

- [-] **4.4 Acquisizione risposta/impedenza → estrazione T/S** — prototipo
  rimosso dal working tree il 2026-07-29: import e overlay FRD/ZMA più una
  stima T/S parziale non costituivano un flusso operativo utile per il
  dimensionamento. L'eventuale ripresa richiede calibrazione del modello,
  confronto misura/simulazione e ottimizzazione guidata; gli export FRD/ZMA
  simulati restano disponibili.

## 5. UX

- [x] **5.1 Refactor workflow Design / Find a driver** — 2026-07-13,
  commit `bf239e2` (release v0.3.0). Due workspace separano il design di un box dal
  ranking del catalogo. Il Finder possiede volume, tensione, goal e vincoli
  indipendenti, usa filtri stretti, mostra una preview e modifica il progetto
  solo con **Apply candidate to design**. Nel Design un solo selettore
  **Suggested / Optimized / Manual** sostituisce auto-align e modalità optimizer;
  preset T/S, sweep avanzato, cursori manuali e metriche secondarie sono
  progressivamente nascosti. Save/Load/Share sono nel popover **Project** e i
  grafici restano in cinque tab. Il Finder usa chiavi widget indipendenti dai
  vecchi `batch_*`, così il browser non ripropone minimi inutili; default:
  40 L, 2,83 V, Balanced, target F3 0 Hz (massima estensione), ripple 3 dB,
  1× Xmax, GD 30 ms,
  range 10–300 Hz, 500 preset / 20 risultati / 240 punti, optimizer inizialmente
  off per un primo scan rapido. I valori sono passati esplicitamente al primo
  rendering e le frequenze sono etichettate come range di valutazione.
  Compatibilità mantenuta
  per i vecchi `.lfp` e link condivisi. Test aggiunti per progressive disclosure
  e default Finder; verifica
  corrente: py_compile OK, DCCAV 19 pass, AppTest Design/Finder OK, suite
  completa 57 pass / 0 fail / 0 skip.

- [x] **5.2 Review UI/UX — fix mirati** — 2026-07-13, commit `bf239e2`
  (release v0.3.0).
  Fix applicati (`ui_app.py`, `.streamlit/config.toml`, `tests/test_all.py`):
  - **MOL fuori grafico (segnalazione utente)**: `_response_y_domain` ora
    estende il tetto della finestra Y a ogni traccia visualizzata (MOL,
    confronto carichi); il fondo resta ancorato alla Total a 10 Hz. Test
    dominio aggiornato + test dedicato MOL.
  - **Nudge ±3% oltre i bound**: `_nudge_state` clampa ai min/max del widget;
    prima, superare il max faceva resettare silenziosamente l'input al minimo
    (999 L → 0.05 L). Test AppTest sul clamp.
  - **Finder: vincoli morti senza optimizer**: target F3 / ripple / excursion
    / GD ora disabilitati quando "Optimize each candidate" è off, con caption
    esplicativa; il range di valutazione resta attivo. Test AppTest.
  - **Tema**: `[theme] base="dark"` in config.toml (palette grafici tarata su
    canvas scuro).
  - **Share via URL**: link completo mostrato in `st.code` (copy button)
    nel popover Project, via `st.context.url` con fallback relativo.
  - **Load type**: da radio orizzontale a selectbox con help (vale per Design
    e per il ranking del Finder).
  - **Microcopy**: help su MOL e "MIL chart"; caption click-marker
    (click/doppio click); caption linea Xmax nel tab Excursion; guideline GD
    dell'optimizer nel tab Group Delay; toast su "Apply candidate to design";
    errore sidebar parlante al posto di `str(exc)` grezzo.
  - **Rifiniture**: metrica "Box volume" nella riga principale (Vb o Vh+Vl);
    unità tipografiche Ω / cm² / T·m / m³/s in label, metriche e assi (le
    colonne Finder tipo "Min ohm" restano invariate per compatibilità cache).
  - **Ordinamento e default (richiesta utente)**: workspace "Find a driver" a
    sinistra e "Design a box" al centro (Project a destra); tendina Load type
    dall'alto Infinite baffle → Sealed → Bass reflex → DCCAV. Nuovi default:
    avvio nel workspace **Find a driver** con carico **Sealed**.
  - **Rename "Acoustic suspension" → "Sealed" (richiesta utente)**: nome
    canonico "Sealed" in UI, motore (`optimize_alignment` accetta i legacy
    "Acoustic suspension"/"Suspension pneumatic" e li canonicalizza) e test;
    migrazione automatica dei vecchi `.lfp`/link condivisi in
    `_apply_loaded_params`, allo startup e nei percorsi batch. Doc
    `docs/dccav.md` (valori `load_type` accettati) e `USER_GUIDE.md`
    aggiornate.
  - **Help "Box strategy"**: tooltip sul segmented control che spiega
    Suggested (starter empirico ri-applicato automaticamente al cambio di
    driver/carico) / Optimized (box dai goal dell'optimizer) / Manual (campi
    sbloccati) — nato da domanda utente "Suggested a cosa serve?".
  - **Robustezza bare-import**: `_finder_value()` con fallback sui default per
    il render del Finder fuori dal runtime Streamlit (il default workspace ora
    è il Finder e `import ui_app` nei test non popola lo stato dei widget).
  Verifica: py_compile OK, AppTest OK, suite completa 60 pass / 0 fail / 0 skip.
  Restano come idee aperte (non fatte): raggruppare pen/cursori del tab
  Response in popover per dare più spazio al grafico; cursore manuale
  singolo (M1 senza M2); palette theme-aware invece del tema forzato.

- [x] **1.9 Direttiva lunghezza assoluta porta vs dimensione cassa +
  optimizer multi-start (segnalazione utente: "porta 47cm per un 12"
  in 40L???")** — 2026-07-15. Il fix 1.8 chiudeva i casi in cui il condotto
  "mangiava" troppo volume della camera (>10%), ma un condotto sottile
  accordato molto basso può restare una frazione minuscola del volume (qui
  2,8%) pur essendo fisicamente più lungo della cassa stessa — 47,5 cm di
  condotto in un box da 40 L (lato stimato ~34 cm). Nuovo
  `port_max_straight_length_cm(volume_l)` (cassa approssimata a cubo,
  `side_cm = (volume_l·1000)^(1/3)`): direttiva indipendente dalla frazione
  di volume, entra come terzo tier di rejection in `_score_alignment`
  (`port_length_over_box_ratio`, calcolato sullo stesso `sized_port` di 1.8 —
  nessun nuovo doppione UI/optimizer) e come nuovo warning in Port Geometry
  ("needs an L-shaped/slot fold... a bigger box, or a higher tuning").
  **Bug trovato verificando il fix**: lo stesso isobarico PowerBass in reflex
  è tornato infattibile a quasi tutti i cap di volume — non un flat-score
  come in 1.8 (lo score era già continuo), ma lo stallo intrinseco della
  compass search: da un unico punto di partenza (Vas/Fs) può bloccarsi in un
  minimo locale infattibile anche con gradiente pulito, mentre una regione
  fattibile esiste altrove nei bound di ricerca (verificato con uno sweep
  esaustivo: score 1,06 raggiungibile a Vb≈40L/Fb≈20Hz, mai trovato dal
  singolo avvio). Fix: **restart deterministici** in `optimize_alignment` —
  se l'avvio primario resta nel tier infattibile, ritenta da punti fissi
  lungo la diagonale del box di ricerca (frazioni 0.75/0.25/0.5, niente
  casualità, budget `max_evaluations` condiviso), tiene il migliore. Verificato:
  tutti i 6 cap di volume ora risolvono per il driver problematico; il caso
  DCCAV originale (1.7/1.8) converge ancora bene (length_ratio 0,996, F3
  22,0 Hz). Doc engine.md/dccav.md. Test nuovi: direttiva lunghezza (ceiling
  esatto, caso reale sotto al 10% ma sopra la direttiva, rejection score,
  optimizer reale che la evita), AppTest sul warning che appare/scompare
  con l'accordatura, arricchito il test 1.8 sul multi-start con la seconda
  causa trovata. Verifica: py_compile OK, ruff OK, AppTest smoke OK, suite
  completa 90 pass / 0 fail / 0 skip.

- [x] **1.8 Fix: sizing porte ancora sbagliato dopo 1.7 (segnalazione
  utente: "trovo duct di 85cm")** — 2026-07-15. Il fix 1.7 aveva chiuso il
  caso singolo ma non il bug strutturale: `_optimizer_metrics` (engine, usato
  per la feasibility) e `_optimized_port_diameter_cm` (ui_app, usato per il
  diametro davvero applicato) erano **due implementazioni indipendenti** con
  tre disallineamenti — nessuna condivideva il margine di sicurezza 1,05× sulla
  velocità, nessuna delle due faceva rispettare il cap del 10% quando il
  target di lunghezza pratica (~5 cm) veniva raggiunto crescendo il diametro,
  e l'arrotondamento a 0,5 cm (risoluzione widget) avveniva SEMPRE per
  eccesso, il che da solo bastava a far superare di nuovo il 10% su un
  ottimo teorico esattamente al limite. Sweep di verifica: 27 combinazioni
  Vb/Fb "approvate" dall'optimizer producevano comunque un condotto reale
  oltre il 10% una volta applicato. Fix: un solo sizer condiviso in engine,
  `port_diameter_for_load(volume_l, fb_hz, end_correction, floor_cm,
  max_diameter_cm, target_length_cm=5.0, grid_cm=0.5)`, usato identico da
  entrambe le parti — cresce verso il target di lunghezza ma non oltre il
  cap del 10% (bisezione sulla frazione, monotona per costruzione), arrotonda
  alla griglia **per difetto** quando resta sopra il floor obbligatorio (mai
  per eccesso, che riaprirebbe il cap), `None` quando il floor stesso (dopo
  arrotondamento a griglia) è già oltre il 10% — nessun diametro soddisfa
  tutte le direttive, va cambiato il box non la porta. Nuovo
  `port_velocity_diameter_cm(peak_volume_velocity, margin=1.05)` condiviso
  per il floor di velocità (prima il margine 1,05× era solo lato UI).
  **Secondo bug trovato durante la verifica**: il primo tentativo di
  `sized_port` (helper interno a `_optimizer_metrics`) codificava il caso
  "nessun diametro va bene" come `required_port_diameter_cm = inf`, il che
  appiattiva lo score del pattern search optimizer a un valore costante su
  tutta la regione infattibile, togliendo il gradiente e facendo fallire
  `optimize_alignment` con "no buildable box" anche quando esisteva un box
  valido appena fuori dal vicinato di partenza (riprodotto: lo stesso
  isobarico PowerBass in reflex, infattibile a QUALSIASI cap di volume incluso
  nessun cap, quando prima funzionava). Corretto riportando la frazione
  (continua) calcolata al floor arrotondato a griglia, non `inf` — ripristina
  il gradiente, lo score resta comunque nel tier infattibile (≥1e5) tramite
  il check esistente sulla frazione. Verificato: il box esatto segnalato
  dall'utente (Vh 5,43/Vl 4,57 @ 34,47 Hz) resta respinto (score infattibile,
  29% del volume), l'optimizer converge su un'alternativa conforme (lower
  port 9,6%); sweep di 1480 combinazioni Vb/Fb → 0 discrepanze
  optimizer↔UI; optimizer reflex trovato feasible su 6 cap di volume diversi
  (prima: 6/6 falliva). Test nuovi: sizer condiviso sui tre rami (target di
  lunghezza, floor-già-infattibile pre/post arrotondamento, arrotondamento
  per difetto), coerenza optimizer↔UI su sweep, non-stallo della ricerca su
  vicinato di partenza infattibile. Adattato un assert obsoleto (porta
  sempre ≥5 cm) che non teneva conto del nuovo compromesso corretto
  (lunghezza più corta quando il cap del 10% vince). Verifica: py_compile
  OK, ruff OK, suite completa 88 pass / 0 fail / 0 skip.

- [x] **1.7 Porte reflex: direttiva volume condotto + risonanza di canna
  (segnalazione utente: porta 4,5 × 84,6 cm)** — 2026-07-15. Il sizing
  poteva richiedere condotti lunghissimi in camere piccole accordate basse
  (caso reale: isobarico 12" in Vl 4,57 L @ 34,5 Hz → 4,5 × 84,6 cm = 29%
  della camera). Nuovi in engine: `port_volume_fraction()` (volume del
  cilindro Helmholtz / camera) con `PORT_MAX_VOLUME_FRACTION = 0.10` e
  `port_pipe_resonance_hz()` (`c/2L`) con `PORT_PIPE_RESONANCE_GUARD = 4`.
  L'optimizer valuta la frazione per-porta al diametro minimo richiesto di
  quella porta (feasibility tier 1e5, come il tetto dei 60 cm): il box
  incriminato ora è scartato e l'optimizer ripiega su Vl 12,9 L @ 25,5 Hz
  (condotto 8%, canna a 300 Hz). UI: due nuovi warning in Port Geometry
  (condotto > 10% della camera; prima risonanza di canna sotto 4× accordo).
  Doc engine/dccav/USER_GUIDE. Test: frazione esatta del cilindro, caso
  utente respinto + box alternativo conforme, helper canna, AppTest sui due
  warning; adattato il test del cap 1 L (ora correttamente infeasible con
  ValueError, cap fattibile 5 L verificato). Verifica: py_compile OK, ruff
  OK, suite completa 85 pass / 0 fail / 0 skip.

- [x] **1.6 Porte reflex: golden rule dell'area minima (richiesta utente)** —
  2026-07-15. Nuovo `port_displacement_min_diameter_cm(ts, fb_hz)` in engine
  (+ costante `PORT_DISPLACEMENT_COEFFICIENT_CM = 20.3`): regola classica
  Small/Dickason `Dmin = 20.3·(Vd²/Fb)^0.25` cm con `Vd = Sd·Xmax` in litri;
  0.0 se Xmax non pubblicato. A differenza del criterio 5%-di-c è
  indipendente dal drive: prima, a tensioni basse (es. il caso 0,01 V del
  5.5) il sizing automatico poteva produrre vent minuscoli. Applicata in tre
  punti: floor nel sizing UI `_optimized_port_diameter_cm` (reflex, bandpass,
  entrambi i porti DCCAV, driver composito incluso), nel
  `required_port_diameter_cm` di `_optimizer_metrics` (feasibility optimizer)
  e nuovo warning Port Geometry quando un porto attivo è sotto la regola.
  Doc engine.md/dccav.md + USER_GUIDE. Test: valore esatto a mano (5,648 cm
  per Sd 530/Xmax 8 a 30 Hz), monotonia col tuning, Xmax mancante → 0,
  fb non positivo → ValueError, floor su sizing e metrica a 0,01 V, AppTest
  warning sotto/sopra la soglia. Verifica: py_compile OK, ruff OK, suite
  completa 83 pass / 0 fail / 0 skip.

- [x] **5.5 Fix: i valori del Design sopravvivono al Finder (segnalazione
  utente)** — 2026-07-15. Nel browser reale Streamlit cancella lo stato dei
  widget keyed non renderizzati in un rerun: un giro nel workspace Finder
  resettava in silenzio tensione (2,83 → default, o 0,01 V dal minimo del
  widget), box Manual, T/S editati e perdite. Il sintomo segnalato
  ("2× parallel dimezza l'ampiezza") era tensione a 0,01 V + i legittimi
  ±6 dB del cablaggio parallelo a pari tensione. Nuovo
  `_preserve_design_state()`: self-assignment di tutte le chiavi
  `_is_param_key()` (prefissi driver_/box_/reflex_/bandpass4_/sealed_/
  loss_/sim_/opt_/load_type, nudge esclusi) accanto ai keep-alive già
  esistenti di plot/Finder/filtri. Riproduzione via AppTest con widget-bound
  `set_value` (le assegnazioni programmatiche non subiscono il cleanup) e
  test di regressione sul round-trip Design→Finder→Design (tensione, Vb
  Manual, strategia). Verifica: suite completa 81 pass / 0 fail / 0 skip.

- [x] **5.4 Un solo algoritmo di box: optimizer con 3 obiettivi (richiesta
  utente)** — 2026-07-15. Eliminata la doppia natura starter/optimizer
  percepita come "5 modalità di calcolo". Il selettore **Box strategy** ora è
  `Max extension / Balanced / Flattest / Manual`: i tre obiettivi sono lo
  stesso `optimize_alignment` (objective extension/balanced/flat) e il box si
  ri-applica da solo a ogni cambio di driver/carico/vincolo (l'auto-align
  legge `box_strategy`, non più `sim_auto_align`; il bottone "Run optimizer
  and apply" e i bottoni/caption "Reset to suggested/starter" sono rimossi;
  optimizer infeasible → fallback allo starter con warning `_auto_box_error`).
  Lo starter empirico resta solo come seed interno (optimizer, Atlas, compare
  loads, seeds widget). Finder: rimosso il toggle "Optimize enclosure per
  candidate" — il ranking passa SEMPRE dall'optimizer (goal + vincoli sempre
  visibili, IB escluso con caption); benchmark: scan intera libreria (6219)
  ~3–25 s via pool parallelo con progress bar. Migrazione: `.lfp`/share/live
  session con "Suggested"→"Balanced", "Optimized"→label di `opt_objective`
  (`_normalize_box_strategy`/`_set_box_strategy_state`, legacy keys
  `sim_auto_align`/`opt_align_mode`/`opt_objective` tenute in sync per il
  round-trip); load con strategia auto forza il re-derive via
  `_optimizer_engine_revision=0`. `_FINDER_DEFAULTS_VERSION`=4 ora popa anche
  `finder_use_optimizer`. Solo `ui_app.py` + test + USER_GUIDE/README
  (niente src/). Test riscritti: auto-strategy applica box goal-driven senza
  bottone, GRS max-extension senza warning, vincoli Finder sempre attivi +
  nascosti su IB, normalizzazione legacy, share pin via Manual. Verifica:
  py_compile OK, ruff OK, suite completa 80 pass / 0 fail / 0 skip.

- [x] **5.3 Finder: scan sempre su tutta la libreria filtrata (richiesta
  utente)** — 2026-07-15. Rimosso l'input manuale "Drivers to evaluate"
  (`finder_candidate_limit`): `_run_find_driver_search` ora usa
  `len(filtered_preset_names)`, quindi lo scan copre sempre l'intera libreria
  dopo i filtri e il conteggio si auto-aggiorna a ogni modifica (caption
  "Scans all N matching presets"). `_FINDER_DEFAULTS_VERSION` → 4 con pop
  esplicito della chiave legacy nella migrazione (vecchi .lfp/share con la
  chiave degradano senza effetto). Le funzioni cached `_batch_rank_presets*`
  mantengono il parametro `candidate_limit` (usato dai test); la UI passa la
  dimensione piena. Solo `ui_app.py` + test + USER_GUIDE (niente src/).
  Test: widget assente nei default e nella mappa sidebar, scan count ==
  libreria filtrata dopo "Find drivers". Verifica: py_compile OK, ruff OK,
  suite completa 80 pass / 0 fail / 0 skip.

---

## Fatto

- [x] **5.6 Upload preset consumato una sola volta** — 2026-07-29, commit
  `c87147b`. I file `.lfp`, JSON e CRW vengono applicati una volta e
  l'uploader Project viene resettato prima del rerun, eliminando il ciclo
  infinito con overlay di caricamento bloccato. Regressione AppTest sul doppio
  upload inclusa.

- [x] **5.7 Audit UI/UX e correzione del flusso principale** — working tree,
  2026-07-29, non ancora committato. Corretto il bug Streamlit che nel
  round-trip Box Design → Bass Match cancellava le checkbox condizionali e
  trasformava i filtri aggregati `All` in `__none__`, svuotando la libreria.
  L'empty state offre ora `Reset candidate filters`; Bass Match è stato
  promosso a flusso hero con brief acustico live, CTA unica `Run Bass Match`,
  risultati driver/load/box e libreria grezza raccolta nel pool candidati
  secondario. Il pre-filtro per carico elimina prima del solver i candidati
  incompatibili per sensibilità di riferimento alla tensione scelta, T/S,
  configurazione o Xmax, mostrando conteggi ammessi/scartati; F3, MOL, ripple,
  escursione e ritardo restano verifiche post-simulazione. I duplicati fisici
  tra cataloghi vengono eliminati prima del solver privilegiando il database
  Load Forge e poi il prezzo; più carichi validi dello stesso driver producono
  una sola riga, quella del progetto meglio classificato. Filtri Mms/Le, range
  e risoluzione sono raccolti in sezioni avanzate, come Mms/Cms/Bl/Le10k nel
  Design. Il Bass Brief espone ora in una griglia densa tutti i constraint di
  carico, prestazione, driver, libreria e valutazione, mostrando anche gli stati
  Off/Any/N/A; metriche e CTA occupano una sola fascia. Il run espone una
  progress bar spessa a tutta larghezza, il completamento è un toast non
  persistente e la classifica ha altezza fissa con scroll interno, così lo stato
  normale non allunga la pagina. Etichette e valori del brief sono stati
  ingranditi; `Desired F3` è stato eliminato dal Finder perché agiva solo come
  preferenza morbida dell'optimizer e non come constraint affidabile. Etichette
  automatiche F3/F6/F10 compatte, export raccolti sotto
  `Export design`, tooltip per Forge Score e badge riscritti come verifiche
  tecniche. Regressioni AppTest dedicate al flusso hero, al pre-filtro, alla
  deduplica, al round-trip e al reset incluse.

- [x] **2.4 Find a driver parallelo + cache** — 2026-07-14. Nuovo modulo
  `src/ranking.py` (esposto dalla facciata, doc `docs/ranking.md`):
  `rank_preset_row()` (una riga di ranking per preset, worker-safe: niente
  Streamlit/stato, box DCCAV via `design_space_box`, preset inutilizzabili →
  `None`), `sort_ranked_rows()`, `rank_sort_value()` e `response_sparkline()`
  con le costanti `SPARKLINE_*` (spostati da ui_app; `_batch_dccav_box` e
  `_rank_value` restano come deleghe sottili per i test). In `ui_app`:
  `_batch_rank_presets` (cachato) ora è il percorso seriale; nuovo
  `_batch_rank_presets_parallel` con `ProcessPoolExecutor` e **progress bar
  reale** (N/total via `as_completed`), usato dal bottone Rank quando
  l'optimizer è attivo su >8 candidati; risultati identici al seriale
  (optimizer deterministico, verificato nel test). Contesto multiprocessing
  **forkserver** (fallback spawn): niente re-import del `__main__` chiamante
  né fork di un processo Streamlit pieno di thread. Trappola trovata:
  spawn/forkserver re-importano il `__main__` del padre come `__mp_main__` —
  il runner dei test eseguiva l'intera suite dentro i worker; ora
  `tests/test_all.py` ha la guardia `_IS_MP_CHILD` (registrazione test,
  argparse e summary/exit saltati nei figli). Flakiness da carico sistemata
  alzando a 60 s il timeout dell'AppTest optimizer. Reload-rule e tabella
  moduli aggiornate (CLAUDE.md), doc API + elenco test in `docs/dccav.md`.
  Test nuovi: worker su nome inesistente → None, parallelo ≡ seriale
  (driver/F3/Vb/sparkline). Verifica: py_compile OK, ruff OK, suite completa
  71 pass / 0 fail / 0 skip. **Sezione 2 completa.**

- [x] **2.1 Split di `src/dccav.py` in moduli** — 2026-07-14. Il file
  (2377 righe) è stato tagliato per slicing meccanico in:
  `src/engine.py` (~1580 righe: costanti fisiche, dataclass tranne
  `DriverPresetInfo`, derivazione/allineamenti, 4 simulatori, optimizer,
  porte, export FRD/ZMA, Monte Carlo, atlante, classificazione,
  configurazioni multi-driver, diagnostica), `src/presets.py` (~700:
  `DRIVER_PRESETS`, loader LSDB cachato, `driver_preset_names/info/get`,
  `DriverPresetInfo`) e `src/pricing.py` (~140: loader prezzi cachato,
  matching sicuro, `_preset_price`, `price_extension_score`).
  `src/dccav.py` è ora una facciata di 25 righe con doppio contesto di
  import (try relativo / except top-level, perché ui_app importa `dccav`
  con `src/` su sys.path mentre i test usano `from src import dccav`);
  ri-esporta anche i due loader privati cachati usati dai test price.
  Dipendenze pulite: engine non importa nulla del catalogo/prezzi
  (verificato via AST nel test di facciata), presets dipende da
  engine+pricing, pricing è foglia. Reload-rule Streamlit aggiornata in
  `ui_app.py` (deps prima, facciata ultima) e in CLAUDE.md (anche tabella
  moduli, architettura e comando py_compile con `src/*.py`); CI aggiornata.
  Doc nuove: `docs/engine.md`, `docs/presets.md`, `docs/pricing.md`
  (contratti per modulo); `docs/dccav.md` resta il riferimento API completo
  con intro da facciata. Test nuovo: identità facciata↔moduli + purezza
  import dell'engine. Nessun cambio di comportamento: suite completa
  70 pass / 0 fail / 0 skip, ruff pulito, entrambi i contesti di import
  verificati end-to-end. **Sblocca il 2.4** (worker paralleli importabili).

- [x] **4.3 Atlante del design space** — 2026-07-14. Backend:
  `design_space_box()` (costruzione del box per un punto del piano — assi:
  reflex Vb/Fb, sealed Vb 1-D, DCCAV Vtot/fl con split Vh/Vl e rapporto
  fh/fl dallo starter empirico; perdite dal template) e `design_space_map()`
  → `DesignSpaceMap` con griglie F3/ripple via `_optimizer_metrics`
  (assi log 0.3–3× starter, 0.55–1.6× tuning; sealed 0.2–4× Vas; celle
  invalide NaN; IB e resolution<3 rifiutati; valutazione a `voltage_v`,
  0 Ω serie come optimizer). UI: nuovo tab **Atlas** nel Design; la
  computazione (~225 sim) è gated dal toggle "Compute atlas" così i rerun
  normali non la pagano, cache per driver+perdite+tensione; heatmap
  `mark_rect` (viridis inverso, "Color by" F3/Ripple) o linea F3–Vb per il
  sealed; click sul punto → riepilogo + "Apply selected box" via pending
  point pre-widget (`_apply_pending_atlas_point`, strategia Manual,
  stesso `design_space_box` della griglia quindi cella riprodotta esatta).
  Doc: sezioni API + elenco test. Test: shape/finitezza griglie, round-trip
  cella↔box, minimo F3 ≤ starter, sweep sealed monotono, rifiuti IB/res,
  AppTest su tab gated + radio + apply pendente (Vb/Fb applicati, Manual).
  Aggiornata l'asserzione dei tab nel test di progressive disclosure.
  Verifica: py_compile OK, ruff OK, suite completa 69 pass / 0 fail / 0 skip.

- [x] **2.2 Configurazioni multi-driver** — 2026-07-14. Backend:
  `DRIVER_CONFIGURATIONS` + `apply_driver_configuration()` (Single /
  2× parallelo / 2× serie / coppia isobarica parallelo-serie): Fs/Qts/Qms
  invarianti; 2× raddoppia Sd/Vas/Pe con Re/Le dimezzati (parallelo) o
  raddoppiati (serie); isobarico dimezza Vas a Sd invariato con Pe×2;
  override Mms/Cms/Bl scartati per ri-derivazione auto-consistente.
  Verificati gli shift classici: coppia parallela +3 dB η₀ esatto,
  isobarico −3 dB per mezza cassa. UI: selettore "Driver configuration" in
  sidebar (chiave `driver_config`, persistita in .lfp/share con il prefisso
  driver_), composito applicato dentro `_driver_from_state()` così
  allineamenti/optimizer/metriche/grafici lo vedono ovunque; caption con
  Sd/Vas/Re/Pe compositi; on_change ri-allinea il box suggerito; il callback
  del preset usa il composito (non il singolo); pin e caption di design
  riportano la configurazione. Finder invariato (ranking su driver singoli,
  documentato nell'help) e "Apply candidate" resetta a Single driver per
  coerenza col box applicato. Doc: sezione API + elenco test. Test:
  scaling esatti, invarianti, override scartati, η₀ ±3 dB, config ignota
  rifiutata; AppTest: 2× parallelo → Min impedance dimezzata, Box volume
  raddoppiato, caption composita. Verifica: py_compile OK, ruff OK, suite
  completa 67 pass / 0 fail / 0 skip.

- [x] **4.2 Bande di tolleranza Monte Carlo** — 2026-07-14, nel working tree.
  Backend: `monte_carlo_response_band()` → `ToleranceBand(frequency_hz,
  lower_db, upper_db, runs)`: perturbazione uniforme ±tolleranza su
  Fs/Vas/Qts/Qms (override Mms/Cms/Bl scartati per auto-consistenza, Qts
  cappato sotto il Qms perturbato), box fissa ("stessa cassa, spread dei
  driver"), 120 run default, percentili 5–95, seed fisso riproducibile,
  run invalidi saltati (<runs/4 validi → ValueError), tolerance=0 collassa
  sulla nominale (verificato esatto). UI: toggle "Tolerance band" nel tab
  Response (disabilitato in Compare loads), input "T/S tolerance (%)"
  5–30%, banda come `mark_area` sotto le tracce con tooltip P5/P95,
  dominio Y esteso al bordo superiore della banda, calcolo con
  `@st.cache_data` (niente ricalcolo per interazioni del fragment).
  Doc: sezione API + elenco test. Test: banda contiene la nominale,
  determinismo del seed, collasso a tolleranza zero, larghezza crescente
  con la tolleranza, smoke sealed/IB, rifiuto tolerance≥1, AppTest su
  toggle + caption. Verifica: py_compile OK, ruff OK, suite completa
  65 pass / 0 fail / 0 skip.

- [x] **4.1 Ottimizzatore price-aware — "miglior basso per euro"** —
  2026-07-14, nel working tree. Backend: `price_extension_score(f3, price)`
  = `F3 × prezzo` (più basso = meglio; input mancanti/non positivi → `inf`).
  UI Finder: radio "Rank by" (`Deepest bass (F3)` / `Best value (F3 × price)`)
  visibile quando i risultati hanno prezzi; il value-sort ri-ordina lo scan già
  simulato senza rilanciarlo (`_value_sorted_frame`, ordinamento stabile con
  fallback F3 per i senza-prezzo in coda), valuta coerente
  (`_finder_price_currency`: valuta sidebar se presente tra i risultati,
  altrimenti la moda), colonna "Value (F3 × price)" e caption esplicativa.
  Vincolo di budget = filtro prezzo currency-aware già in sidebar (richiamato
  nell'help, nessuno stato duplicato). Chiave tabella distinta per modalità
  così la selezione non punta alla riga sbagliata dopo il ri-ordino. Doc:
  sezione API + elenco test. Test: score puro, ri-ordino sintetico multi-valuta
  (unpriced/valuta-diversa in coda, Value NaN), fallback valuta, AppTest con
  risultati seminati (radio + caption; fix: allineare
  `_finder_defaults_version` per non far cancellare i seed dalla migrazione).
  Rifinitura collaterale: variabili design inizializzate a monte della sidebar
  (niente NameError loggato nel bare import col default Finder).
  Verifica: py_compile OK, ruff OK, suite completa 63 pass / 0 fail / 0 skip.

- [x] **2.5 CI GitHub Actions** — 2026-07-14, commit `bf239e2`
  (release v0.3.0). `.github/workflows/ci.yml` su push
  (master/experimental) e PR, Python 3.14 (come il venv locale), pip cache:
  py_compile → `ruff check src tests ui_app.py` → suite completa → AppTest
  smoke (comando folded verificato con `compile()`). Per rendere il lint
  bloccante il repo è stato portato a **ruff clean**: 12 autofix (I001 import
  sort, UP033 `@cache`, UP037) + manuali `zip(..., strict=True)` ×3 (le
  colonne/array hanno sempre pari lunghezza), `_DEFAULT_GOALS` singleton per
  B008 su `optimize_alignment` (firma semanticamente identica) e
  per-file-ignores E402 in `pyproject.toml` per i due file che estendono
  `sys.path` prima degli import. Nessun cambio di comportamento: suite
  completa 61 pass / 0 fail dopo il cleanup.

- [x] **4.5 Export FRD/ZMA** — 2026-07-14, commit `bf239e2`
  (release v0.3.0). Backend (`src/dccav.py`): nuovo campo
  `SimulationResult.impedance_phase_deg` (default `None` per compatibilità con
  risultati costruiti a mano; popolato nei tre costruttori: DCCAV, reflex,
  `_unported_result` per sealed/IB), helper `response_phase_deg()` (fase
  acustica totale ±180°, include il termine di radiazione +90° da `jw·(Ud+Up)`)
  e exporter `export_frd_text()` / `export_zma_text()` (2 righe di commento
  `*`, righe dati tab-separated `%.4f`, righe non finite saltate; ZMA con fase
  zero su risultati legacy senza il campo). UI: bottoni "Download FRD
  (response)" e "Download ZMA (impedance)" accanto al CSV, riga a 3 colonne.
  Doc: sezioni API + campo nel `SimulationResult` + voce nell'elenco test.
  Test: round-trip colonne vs array simulati, fase FRD wrapped e non piatta,
  fase impedenza entro ±90° e variabile, fase presente sui 4 carichi, fallback
  legacy a fase zero, bottoni presenti in AppTest (`at.get("download_button")`).
  Verifica: py_compile OK, `-m dccav` 20 pass, suite completa
  61 pass / 0 fail / 0 skip.

- [x] **4.7 Classificazione sub puri vs woofer midbass (richiesta utente)** —
  2026-07-13, commit `57c25e1`. Backend: `classify_driver_bandwidth()`
  in `src/dccav.py` → `DriverBandwidthClass` con classe
  (Subwoofer / Woofer / Midbass-capable), corner induttivo
  `f_Le = Re/(2πLe)`, densità di massa `Mms/Sd`, SPL 1W e motivazioni.
  Punteggio: f_Le <400 Hz sub / >800 Hz mid (peso 2); Fs ≤35 / ≥45; Mms/Sd
  ≥0.30 / ≤0.15 g/cm²; SPL1W ≤90 / ≥94 dB (peso 1); verdetto con margine ≥2,
  altrimenti "Woofer"; Le sconosciuta (0) salta l'indicatore. UI: filtro
  "Class" tra i filtri preset (con lru_cache per nome), metriche "VC corner"
  e "Class" nella riga di riferimento con caption delle motivazioni, colonna
  "Class" nel Finder (anche nel CSV). Doc: sezione API con pesi e caveat
  (breakup/direttività non modellati). Test: Dayton RSS315HO-4 → Subwoofer,
  Beyma 12CMV2 → Midbass-capable, f_Le esatto, Le=0 → None; filtro UI e
  AppTest su opzioni selectbox e metriche. Verifica: suite 55 pass / 0 fail.

- [x] **3.5 Batch: sparkline risposta + export CSV tabella** — 2026-07-13,
  commit `57c25e1`. Ogni riga del ranking porta una colonna "Response"
  (`_batch_sparkline`: risposta totale ricampionata a 48 punti, normalizzata
  al picco e limitata a [-30, 0] dB) mostrata con `LineChartColumn` a scala
  fissa, così le sparkline sono confrontabili tra righe. Bottone "Download
  candidate CSV" sotto la tabella (colonne visibili, sparkline esclusa). Le righe
  cache di sessioni precedenti senza "Response" degradano senza colonna.
  Attenzione trovata in corso: `_batch_rank_presets` è decorata
  `@st.cache_data` — l'inserimento è stato fatto sopra il decoratore. Test:
  asserzioni su lunghezza/range/roll-off della sparkline nel test batch
  esistente. Verifica: suite 53 pass / 0 fail. **Sezione 3 completa.**

- [x] **3.4 Condivisione design via URL** — 2026-07-13, commit `57c25e1`.
  Bottone "Share via URL", ora nel popover Project con Save/Load: serializza
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

- [x] **3.3 Riorganizzazione a tab + `st.fragment`** — 2026-07-13, commit
  `57c25e1`. Lo snapshot introduceva sei tab; il refactor 5.1 mantiene
  Response / Excursion / Impedance / Ports / Group Delay nel Design e sposta
  il Finder in un workspace autonomo. Le checkbox
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

- [x] **3.2 Confronto 4 topologie in un click** — 2026-07-13, commit
  `57c25e1`. Toggle "Compare loads" accanto ai bottoni pin. Rivisto su
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

- [x] **3.1 Overlay A/B — "Pin curva corrente"** — 2026-07-13, commit
  `57c25e1`. Bottoni "Pin response"/"Clear pin" sopra il grafico risposta:
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
  `.gitignore` aggiornato con i lock/tmp del file prezzi. Il successivo
  snapshot del lavoro feature è il commit `57c25e1`.

- [x] **1.4 Resistenza serie (ampli + cavo + DCR crossover)** — 2026-07-13,
  commit `57c25e1`. Backend: helper `_electrical_source()` condiviso;
  parametro `series_r_ohm=0.0` sui quattro simulatori (drive con Re+Rs,
  damping elettrico Bl²/(Re+Rs) → Qes/Qts effettivi più alti, impedenza vista
  dalla sorgente inclusa Rs); `_limit_curves` con partitore resistivo sul
  limite termico (potenza riportata = quota sul Re del driver). UI: input
  "Series R (ohm)" nei controlli Drive avanzati (chiave `sim_series_r_ohm`,
  persistita in .lfp), con tooltip; optimizer e Finder restano a 0 Ω
  (documentato — possibile follow-up estenderli). Test: shift ~2 Ω del minimo
  di impedenza, riduzione drive, variazione di damping non piatta, cap
  termico lato driver, rifiuto valori negativi, percorso sealed/IB/DCCAV +
  AppTest sul metric Min impedance (0 → 4 Ω). Verifica: suite completa
  50 pass / 0 fail.

- [x] **1.3 Metriche derivate: sensibilità, η₀, EBP** — 2026-07-13, commit
  `57c25e1`. Backend: `driver_reference_metrics()` →
  `DriverReferenceMetrics(eta0, spl_1w_db, spl_2v83_db, ebp_hz)` con formule
  classiche derivate dalle costanti del modulo. UI: metriche nel pannello
  Driver details (Eta0 ref, SPL 1W/1m, SPL 2.83V/1m, EBP) + caption con
  lettura topologica dell'EBP (<50 sealed, 50–100 entrambi, >100 ported).
  Test: formule vs `complete_driver` sul KEF dell'articolo + AppTest sulla
  riga di metriche. Verifica: suite completa 48 pass / 0 fail.

- [x] **1.2-bis Warning porto auto-esplicativo** — 2026-07-13, commit
  `57c25e1` (feedback
  utente sullo screenshot: il messaggio "increase the port diameter" sembrava
  incoerente). Nuovi helper `port_max_tuning_hz()` (tetto di accordatura a
  lunghezza zero) e `port_min_diameter_cm()` (diametro minimo per il tuning
  richiesto), inversi esatti di `port_length_cm()` al bordo L=0. Il warning
  ora cita i numeri: "a 4.0 cm opening in 16.7 L tunes at most to ~81 Hz;
  reaching 127.6 Hz needs ≥ 9.8 cm". Test round-trip helper + AppTest sul
  messaggio. La fisica era corretta: accordature alte su volumi grandi
  richiedono porti larghi e corti.

- [x] **1.2 Velocità aria nel porto + warning chuffing** — 2026-07-13, commit
  `57c25e1`. Backend: `port_air_velocity_ms()` (|U|/S in m/s, porta
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

- [x] **1.1 Grafico Group Delay in UI** — 2026-07-13, commit `57c25e1`.
  Backend: helper `group_delay_ms()` e colonna `group_delay_ms` nel CSV
  export. UI attuale: tab dedicato "Group Delay" nella vista a tab con
  grafico `_plot_group_delay()` e traccia colore dedicata; non usa più la
  vecchia checkbox `GD` dei Plot Tools. Doc aggiornata (`docs/dccav.md`,
  sezione `group_delay_ms` + elenco test). Test nuovi: "DCCAV group delay is
  finite and exported to CSV" e "UI group-delay tab renders the Group Delay
  chart". Verifica: py_compile OK, `-m dccav` 15 pass, AppTest OK, suite
  completa 44 pass / 0 fail.
