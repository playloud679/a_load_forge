# Changelog

## 2.13.0 (2026-06-09)

- **Flange di montaggio per il waveguide OS-SE (ATH)** (`ui_app.py`, `src/flange_generator.py`): l'OS-SE ora supporta tutte e tre le flange (gola/bocca/intermedia), prima disabilitate. La **gola è rotonda** → flangia circolare piatta saldata alla parete esterna (`generate_flange`), esattamente come i profili assialsimmetrici. **Bocca e mid sono superellittiche** → nuova `generate_contour_flange()` che costruisce la flangia attorno al **contorno reale** della sezione (ridge diagonali inclusi) via offset Shapely, invece di un'ellisse inscritta. L'ellisse inscritta sarebbe **~30 mm corta all'angolo diagonale** (177.7 vs 147.4 mm su un OS-SE 90°×60°) e taglierebbe l'airway negli angoli; il contorno reale segue la superellisse: foro = contorno morso di `bite` verso l'interno (la parete a spessore costante spunta e si fonde), anello = contorno + parete + `ring`, fori distribuiti **per lunghezza d'arco** lungo il contorno così da seguirne la forma. Le tre flange saldano con l'horn in **un corpo unico watertight**.
- **Sezione OS-SE campionata dal campo `r(z,φ)`** (`ui_app.py`): nuovi helper `_osse_contour_xy(z)` (contorno x,y reale) e `_osse_airway_wh_at_z(z)` (W×H airway) ricavano la geometria di bocca/mid direttamente dal campo morphato del waveguide; la gola usa il riferimento rotondo `throat_R + thickness`.
- **Test** (`tests/test_all.py`): +`OS-SE throat/mouth/mid flanges weld to horn` (le tre flange watertight, union in corpo unico, e verifica che la flangia bocca **raggiunga l'angolo diagonale reale** e non un'ellisse ~30 mm più stretta) → **197 funzionali** + 33 geometria, tutti verdi.
- **Docs**: `docs/osse_horn.md` (sezione "UI mounting flanges"), `docs/flange_generator.md` (`generate_contour_flange`), README e `USER_GUIDE.md` con il profilo **OS-SE (ATH)** e le sue flange; `VERSION` e `pyproject.toml` aggiornati a `2.13.0`.

## 2.12.2 (2026-06-08)

- **Spigoli vivi su adapter rettangolari non quadrati** (`src/throat_adapter.py`): `_rect_points()` ora **ancora i 4 angoli come vertici esatti** invece di campionare il perimetro in modo uniforme. Il morph cerchio→rettangolo mantiene gli spigoli vivi solo se un vertice cade *esattamente* sull'angolo: con il campionamento uniforme questo capitava **solo per un quadrato** (frazioni d'angolo `1/8, 3/8, 5/8, 7/8` → indici interi 8/24/40/56), mentre per un rettangolo non quadrato gli angoli cadevano *tra* due campioni e l'edge di collegamento li tagliava, producendo un **chamfer** visibile su pareti interne **ed** esterne. Ora il perimetro è diviso in 5 archi (start mid-right + 4 angoli) e i punti sono distribuiti proporzionalmente alla lunghezza dei lati (≥1 intervallo per arco). L'output del quadrato è invariato (archi `1:2:2:2:1` → `8,16,16,16,8`); risolve sia gli spigoli interni che esterni perché la parete esterna è offset/morph di quella interna ora viva.
- **Parete adapter a spessore costante — niente pieno tra flangia/collare e flare** (`src/throat_adapter.py`): la parete della transizione (sia filettata che flangiata) ora è **sempre un offset parallelo (miter) dell'inner morphato** (`_offset_polygon_outward(inner, wall_thickness)`), quindi resta esattamente `wall_thickness` su ogni asse con l'airway dietro vuoto. Prima l'outer veniva morphato **indipendentemente** verso l'area-equivalente esterna dell'horn: per un target rettangolare allungato l'intermedio area-preserving è più tondo della forma finale, così **l'asse stretto dell'outer faceva overshoot più dell'inner** e impacchettava di materiale lo spazio tra collare/flangia e flare ("lo spazio tra flangia e flare non deve essere pieno"). L'offset parallelo è anche intrinsecamente flush con l'horn (la parete dell'horn è lo stesso offset costante dello stesso inner). Misurato: parete sull'asse stretto **~10 mm → 4.00 mm** costante. I parametri `outer_target_*`/`outer_rect_*` restano accettati per compatibilità ma non guidano più la parete (rimossi i locali morti `_outer_target_fn`/`_outer_target_R`).
- **Test aderenza profili alle curve matematiche** (`tests/test_all.py`): nuova sezione che verifica, via `r_eq = √(area_airway/π)` (metrica unica per cerchio/rettangolo/N-gono), che la parete generata segua la matematica a più stazioni z. **Senza morph**: assisimmetrici (Tractrix, Salmon, Exponential, Oblate, Conical, R-OSSE, Le Cléac'h) entro 0.4 mm (scarto reale ~0.01 mm); rettangolare (w/h e r_eq) entro 0.6 mm; poligonali 4/6/8-gon (area-matched) entro 0.4 mm — con gestione corretta dei profili roll-back (campionamento sotto il labbro). **Con morph**: l'adapter embedded preserva il flare sopra il giunto, mantiene l'airway continuo al giunto (nessuno step), onora il bore lato driver (~25 mm) e cresce monotòno fino alla bocca.
- **Regressioni** (`tests/test_all.py`): +`rect points corners anchored` (vertice esatto su ogni angolo per 50×50, 185×80, 370×30, 10×400) e +`adapter transition wall constant thickness` (parete sull'asse stretto < 1.4× spessore su un rettangolo molto allungato, niente pieno) → **191 funzionali** + 33 geometria, tutti verdi.
- **Docs/versioning**: `docs/throat_adapter.md` (descrizioni `_rect_points`, modalità transizione threaded/flanged e regola parete a spessore costante), `VERSION` e `pyproject.toml` aggiornati a `2.12.2`.

## 2.12.1 (2026-06-08)

- **Forma e dimensionamento Mouth/Mid** (`src/flange_generator.py`, `ui_app.py`): `Offset from flare` mostra solo l'offset e segue automaticamente la sezione del flare, con fori centrati nel materiale. `Custom dimensions` espone Circular/Polygonal/Rectangular su ogni sezione e consente fori auto-centrati oppure su distanza fissa dal centro (PCD). La mouth inward resta vincolata al bordo strutturale; la throat flange mantiene controlli e comportamento precedenti.
- **Mouth inward su tutti i roll-back** (`ui_app.py`): la modalità inward non è più limitata a Rectangular/Elliptical. Il bordo di ritorno viene rilevato dalla geometria esterna reale e la piastra interna, i fori, i pilastri e le sedi testa seguono anche sezioni Circular e Polygonal. L'opzione compare solo quando la cavità ha profondità sufficiente per offset e diametro fori correnti.
- **DXF ellittico custom** (`src/dxf_export.py`): `elliptical_flange_dxf()` accetta anche `outer_w`/`outer_h`, così flange ellittiche con dimensioni esterne arbitrarie mantengono outline e pattern fori esatti.
- **DXF flange più affidabili** (`src/dxf_export.py`, `ui_app.py`): il rilevamento automatico prova anche i piani mediani tra facce orizzontali, quindi trova piatti sottili sopra adapter lunghi; la flangia bocca inward esporta anche i fori passanti ricavati dai tagli applicati all'assieme.
- **Shape adapter senza aumento profondità** (`ui_app.py`): confermato il morph embedded che sostituisce il primo tratto del flare e mantiene invariata la posizione della bocca.
- **Test/docs** (`tests/test_all.py`): aggiunte regressioni per adapter lunghi, DXF ellittico analitico, generatore Mouth/Mid comune e piastre inward circolari/poligonali. Totale: **175 funzionali** + 33 geometria.
- **Versioning**: `VERSION` e `pyproject.toml` aggiornati a `2.12.1`.

## 2.12.0 (2026-06-08)

- **Export DXF dima fori flange** (`src/dxf_export.py` nuovo, `ui_app.py`): ogni flangia (gola/bocca/intermedia) ora si scarica come **DXF 2D** — fori-bullone, foro centrale e contorno su layer separati (`HOLES`/`BORE`/`OUTLINE`/`CENTERS`), pronto come dima di foratura o taglio laser/CNC di una piastra. Nessuna dipendenza nuova: scritto a mano come AutoCAD **R12 (AC1009)** ASCII in millimetri (come `_step_export.py` per lo STEP). Il template è **derivato dalla mesh** della flangia (sezione planare del piatto), quindi funziona per ogni tipo (circolare/poligonale/rettangolare/ellittica, custom o bolt-on, incluso il piatto dell'adapter bolt-on) senza riderivare parametri. I fori-bullone escono come **cerchi al diametro nominale esatto** sul cerchio bulloni reale (raggio recuperato come raggio circoscritto dei vertici, anche se il foro mesh è un cilindro a 12 facce); un foro centrale esagonale o rettangolare mantiene la forma vera come polilinea. Bottoni di download per-flangia sotto STL/STEP nei risultati; mostrati solo per flange con fori reali.
- **Test** (`tests/test_all.py`): +4 controlli DXF (recupero esatto fori circolari, bore poligonale come polilinea, flangia rettangolare, nessun template senza fori) → **169 funzionali** + 33 geometria, tutti verdi.
- **Docs/versioning**: nuovo `docs/dxf_export.md`, tabella moduli in `CLAUDE.md`, `docs/INDEX.md`, README, guida utente e versione aggiornati a `2.12.0`.

## 2.11.1 (2026-06-08)

- **Raccordo C2 adapter→flare** (`src/throat_adapter.py`, `ui_app.py`): il raggio equivalente dell'adapter ora può usare Hermite **quintico** che combacia anche la **curvatura** (`d²r/dz²`) del flare al handoff, non solo valore e slope. Il raccordo cubico precedente, partendo piatto dal driver, faceva overshoot dello slope e ripiegava: vicino al giunto la curvatura cambiava segno rispetto al flare e lasciava una **linea d'inflessione** visibile nel slicer. Nuovi parametri `target_curv`/`outer_target_curv` su `make_adapter()` e `make_adapter_assembly()`; la UI calcola la curvatura interna ed esterna al punto di raccordo (`_profile_curv`) e la passa. Misurato: salto di slope al giunto **0.0034 → 0.0007** (≈5×), pezzo watertight invariato.
- **Test** (`tests/test_all.py`): +2 controlli (verifica analitica valore/slope/curvatura del quintico + confronto C2 vs C1 più liscio) → **165 funzionali** + 33 geometria, tutti verdi.
- **Docs/versioning**: `docs/throat_adapter.md`, README e versione aggiornati a `2.11.1`.

## 2.11.0 (2026-06-08)

- **Preset bolt-on driver standard** (`src/flange_generator.py`): nuovo `DriverFlangeSpec` + tabella `DRIVER_FLANGE_SPECS` con i pattern industriali di montaggio (`bolt_on_1in_2` 1" 2-fori, `bolt_on_1in_3` 1" 3-fori, `bolt_on_1_4in_4` 1.4" 4-fori a croce, `bolt_on_2in_4` 2" 4-fori a croce). Helper `driver_mounting_hole_centers()` e `generate_driver_mounting_flange()` fissano diametro esterno, fori M6, PCD, numero e fase del pattern; il foro centrale è `gola nominale + throat_clearance` (default 0.3 mm).
- **Adapter di gola con bolt-on** (`src/throat_adapter.py`): `make_adapter_assembly()` accetta una chiave bolt-on come `driver_type` e nuovo parametro `driver_clearance` (0.3 mm). Per i preset carica il pattern fisso da `DRIVER_FLANGE_SPECS` e lo unisce alla transizione con il motore manifold; la flangia custom resta disponibile via `flange_R`.
- **UI** (`ui_app.py`): selettore driver esteso con flangia custom + bolt-on standard 1"/1.4"/2"; clearance di gola configurabile. I preset bloccano Ø esterno, fori, PCD e layout angolare così che non possano divergere.
- **Single source of truth**: throat nominale, Ø esterno, fori M6, PCD e fase vivono solo in `DRIVER_FLANGE_SPECS`; UI e adapter consumano quelle chiavi (vedi `docs/INDEX.md`).
- **Test** (`tests/test_all.py`): +7 controlli sui preset bolt-on (centri fori, clearance, union watertight con l'adapter) → **163 funzionali** + 33 geometria, tutti verdi.
- **Docs/versioning**: `VERSION`, `pyproject.toml`, README, guida utente e documentazione di modulo (`docs/flange_generator.md`, `docs/throat_adapter.md`, `docs/INDEX.md`) aggiornati a `2.11.0`.

## 2.10.1 (2026-06-08)

- **Flangia bocca inward strutturale** (`ui_app.py`): la roll-back mouth flange ora crea piloni pieni tra flare e flangia interna, poi li rifila con una booleana sulla superficie reale del flare. Il supporto resta continuo fino alla battuta delle viti senza sporgere dalla parete esterna.
- **Fori e sedi testa corretti** (`ui_app.py`): i fori visibili sul flare sono tagli circolari del solo diametro vite; le sedi testa sono assiali e concentriche ai fori verticali, con fondo comune complanare controllato da `Head depth`. La sottrazione finale avviene dopo l'unione dei piloni, evitando riempimenti o aperture deformate.
- **Posizionamento rettangolare** (`ui_app.py`): i piloni e i bulloni delle flange inward rettangolari seguono il bordo rettangolare reale invece di una circonferenza equivalente.
- **Regressioni** (`tests/test_all.py`): aggiunti controlli sulla creazione, rifilatura e unione dei piloni, sul foro esterno tondo e sulle sedi testa assiali/complanari.
- **Docs/versioning**: `VERSION`, `pyproject.toml`, README, guida utente, manuale e documentazione tecnica aggiornati a `2.10.1`.
- **Test**: 156 funzionali + 33 geometria (189 totali), tutti verdi.

## 2.10.0 (2026-06-06)

- **Flange + adapter Elliptical** (`rectangular_flange.py`, `throat_adapter.py`, `ui_app.py`): aggiunto foro interno ellittico, abilitate flange di gola/bocca/intermedia e shape adapter con target ellittico reale. Il morph usa il raggio equivalente `sqrt(W·H)/2` e sostituisce l'inizio del flare senza allungare la tromba.
- **Threaded corretto** (`throat_adapter.py`, `ui_app.py`): rimossa la selezione 1"/1¼"/2". Rimane il solo standard driver **1⅜"-18**, distinguendo il diametro del filetto (`34,925 mm`) dal foro acustico reale da **25,0 mm**, da cui ora parte il morph.
- **Adapter integrato nella lunghezza della tromba** (`ui_app.py`): il morph round→shape non viene più aggiunto prima della gola. Ora sostituisce i primi millimetri del flare, che viene tagliato alla quota di raccordo; forma interna/esterna e pendenze sono interpolate sul profilo reale. La posizione della bocca e la profondità acustica restano invariate. Solo flangia o socket filettato possono sporgere dietro il piano gola.
- **Nuovo profilo R-OSSE** (`profile_generator.get_rosse`, CLI `--profile rosse`, `ui_app.py`): implementazione delle equazioni parametriche pubblicate in “R-OSSE Acoustic Waveguide rev.7” di Marcel Batík, con roll-back completo verso lo spazio libero. La UI espone diametro esterno, copertura totale, angolo gola e fattori `k/r/m/b/q`; supporta sezioni Circular/Polygonal e conversione area-preservante Rectangular/Elliptical. Test di regressione sul campione ST260 del documento (Ø260 mm, profondità 77,70 mm) e mesh watertight.
- **Nuovo profilo Conical** (`src/profile_generator.py` `get_conical`, `src/rectangular_horn.py` `get_rectangular_conical`, CLI `--profile conical`, `ui_app.py`): cono dritto CD `r(x)=r0+x·tan(theta)`, baseline a direttività costante. Stessa interfaccia throat+coverage+length dell'oblate; la UI le dispaccia entrambe via un singolo handle `is_cd` invece di duplicare 17 branch. Sezioni Circular/Polygonal/Rectangular (Radial non supportato, come Le Cléac'h). Docs di modulo + 9 nuovi test (math/legge/mesh circolare/rettangolare).
- **Sezione Elliptical** (`ui_app.py`, motore `profile_generator.generate_elliptical_3d_mesh_from_profiles` già esistente): nuova Section che riusa l'intera matematica rettangolare (eredita tutti i profili + input W/H e copertura H/V dei CD) ma lofta ogni slice come **ellisse vera** (semiassi w/2, h/2). È la sezione "giusta" per i waveguide asimmetrici. In questa v1 flange/adapter sono **disabilitati** per l'ellittica (una flangia rett./circolare non si salda watertight attorno a un'ellisse — servirà una flangia a foro ellittico). Nuovo test end-to-end watertight (rect-math Salmon → ellisse).
- **Ergonomia UI** (`ui_app.py`): le tre flange (Throat/Mouth/Mid) mostrano in primo piano solo i campi che contano (Thickness, Bolt count/Ø, Ring width); Z offset, Bolt position e Outer shape/sides spostati in un expander "Advanced". I parametri secondari dei giunti radiali e box (clearance, outer skin, margin) spostati in expander "Advanced … joint" lasciando in vista solo la depth. Rimossi tre `number_input` disabilitati di sola anteprima nella sezione Slice e import morti (`io, zipfile`, `_utils` ri-importato in locale 5×, ora a livello modulo).
- **Badge versione in UI** (`ui_app.py`): la versione (letta da `VERSION` a runtime) è mostrata in piccolo sotto il titolo e nel titolo della tab del browser.
- **Guida utente** (`USER_GUIDE.md`): nuovo manuale bilingue IT/EN orientato all'utente dell'app (distinto dal tecnico `MANUAL.md`).
- **Test**: 136 funzionali + 33 geometria (169 totali), tutti verdi. Verificato con `streamlit.testing.AppTest` su tutti i profili × sezioni + percorso generate→slice→giunti (0 eccezioni).

## 2.9.0 (2026-06-05)

- **Profilo oblate spheroidal CD** (`src/profile_generator.py`, `src/rectangular_horn.py`, `src/radial_horn.py`, `ui_app.py`): nuovo profilo constant-directivity con legge `r(x)=sqrt(r0^2 + (x*tan(theta))^2)`, throat a pendenza zero e asintoto conico. Supporto asimmetrico rettangolare/ellittico con coperture orizzontale e verticale indipendenti.
- **Slicing print-volume** (`src/_slicer.py`, `ui_app.py`): nuova modalita `Print volume boxes` con volume massimo X/Y/Z, packing `Center-up core first`, `Adaptive largest pieces` o `Regular grid`. Il default parte dal core centrale basso, sale in Z e poi genera ali laterali grandi invece di listelli da griglia globale.
- **Throat adapter/flange monolitici nei box**: il blocco throat-side protetto resta integrato nel primo core chunk invece di diventare un pezzo separato. Il primo chunk puo superare il volume di stampa se necessario per mantenere adapter/flange monolitici.
- **Box tongue & groove** (`src/_slicer.py`, `ui_app.py`): giunti maschio/femmina opzionali sulle facce condivise dei chunk print-volume, con depth, clearance e margin regolabili.
- **CLI sync** (`src/main.py`): `python -m src.main` e lo script console `horn` delegano alla CLI aggiornata di `profile_generator.py`, evitando una seconda lista profili obsoleta.
- **Docs/versioning**: README, docs modulo, `VERSION` e `pyproject.toml` aggiornati a 2.9.0.
- **Packaging fix** (`pyproject.toml`): aggiunta `shapely>=2.0.0` mancante dalle `dependencies` (era solo in `requirements.txt`, ma `_slicer.py` la richiede) — un install via `pip install .` ora porta tutte le dipendenze runtime.
- **Tooling** (`pyproject.toml`, `Makefile`): config `ruff` minima (`E,F,I,UP,B`, line-length 100) + extra `[dev]`; nuovi target `make test`, `make lint`, `make format`, `make dev`.
- **Type aliases** (`src/_utils.py`): `CircularProfile` `(z, r)` e `RectProfile` `(z, w, h)` per annotare il math-layer; nuovo `docs/_utils.md`.
- **Hardening sorgenti UI** (`ui_app.py`, `.streamlit/config.toml`): i traceback non finiscono più nel browser (esponevano frammenti di sorgente). `st.code(traceback.format_exc())` sostituito da messaggio generico + `logger.exception` lato server; nuova config con `client.showErrorDetails = "none"` e `server.enableStaticServing = false`.
- **Test**: 126 funzionali + 33 geometria (159 totali), tutti verdi. Nuovi: `pyproject.toml covers all requirements.txt deps` (blinda l'omissione `shapely`) e `_utils exposes CircularProfile/RectProfile aliases`.

## 2.8.2 (2026-06-04)

- **Slicer UI cache reset** (`ui_app.py`): aggiunto pulsante `Reset slicer cache` e invalidazione automatica di `_ax_segs` / `_pieces` quando cambiano mesh, axial cut, adapter segment, petal count, radial joint depth, clearance o `Outer skin keep`. I download STL non restano più fermi su pezzi generati con parametri vecchi.
- **Test**: 79 funzionali + 33 geometria (112 totali), tutti verdi.

## 2.8.1 (2026-06-04)

- **Slicer radial T&G — pelle esterna consistente** (`src/_slicer.py`, `ui_app.py`): lingua e cava non vengono più centrate su tutta la parete del seam. Il profilo del giunto può proteggere una fascia esterna (`Outer skin keep`, default 1.5 mm) e spostare tongue/groove verso l'interno, evitando bordini esterni troppo sottili.
- **Test**: 79 funzionali + 33 geometria (112 totali), tutti verdi. Nuovo test `joint profile preserves outer skin`.
- **Docs**: `docs/_slicer.md` aggiornato per `outer_margin` e `_joint_profile`.

## 2.8.0 (2026-06-04)

- **Slicer — adapter come segmento assiale** (`src/_slicer.py`, `ui_app.py`): quando l'assembly generato contiene un throat adapter, lo slicer può creare un taglio dedicato alla quota adapter→flare. L'adapter diventa il segmento assiale inferiore e il flare viene segmentato solo sopra quel punto, con lo stesso axial joint lip se abilitato.
- **Test**: 78 funzionali + 33 geometria (111 totali), tutti verdi. Nuovo test `adapter segment axial cut`.
- **Docs**: README e `docs/_slicer.md` aggiornati per il nuovo taglio adapter.

## 2.7.1 (2026-06-04)

- **Version sync**: `VERSION` e `pyproject.toml` allineati a `2.7.1`.
- **Docs sync**: README e indice docs aggiornati per chiarire la regola della mouth flange: foro sulla parete esterna reale del flare con bite da 0.5 mm, coerente tra UI, ring width, bolt circle e mesh generata.

## 2.7.0 (2026-06-04)

- **Adapter filettato anche su flare circolari** (`src/throat_adapter.py`, `ui_app.py`): la sezione Throat Flange / Adapter espone l'interfaccia threaded anche quando la sezione del corno è **Circular**. Il backend accetta `horn_shape="circular"` oltre a rectangular/polygonal. Le vecchie taglie multiple sono state sostituite in 2.10.0 dal solo attacco 1⅜"-18 con foro da 1".
- **Raccordo C1 adapter↔flare per tutti i tipi**: l'adapter non termina più con una semplice corrispondenza di diametro. La morph shape usa smoothstep quintico, mentre il raggio equivalente usa Hermite con `target_slope` e `outer_target_slope` calcolati dalla derivata reale del flare. Risultato: niente spigolo al giunto e continuità di espansione interna/esterna per circular, rectangular e polygonal, sia flanged sia threaded.
- **Fix fase adapter poligonale**: il target N-gon dell'adapter usa la stessa rotazione `+π/2` del motore `polygonal_horn`, quindi adapter e flare poligonale non risultano più sfasati dopo generazione o split.
- **Fix non-manifold adapter↔flare**: l'adapter viene inserito nel flare con 0.5 mm di overlap volumetrico invece di appoggiarsi con facce coplanari al throat. La union manifold non lascia più edge con più di due facce nel caso polygonal + threaded adapter.
- **Fix mouth flange consistente** (`ui_app.py`): circular, polygonal e rectangular ora usano la stessa regola per il foro alla bocca: parete esterna reale del flare meno `_FLANGE_WALL_BITE` (0.5 mm). La misura mostrata in UI, il ring width, il bolt circle e la mesh generata non divergono più.
- **Outer target coerente col mesh engine** (`ui_app.py`): la UI passa all'adapter le dimensioni esterne e la pendenza esterna calcolate con lo stesso parallel-offset usato dai motori 3D, evitando scalini fuori dalla gola.
- **Split defaults** (`ui_app.py`): il taglio assiale ora parte da **1 segmento** e i petali per segmento partono da **2 petali**.
- **Test**: 77 funzionali + 33 geometria (110 totali), tutti verdi. Nuovi test per adapter circular, threaded circular, pendenza C1 del raccordo, fase poligonale, fase sorgente del morph e union polygonal adapter↔flare.
- **Docs**: README, `docs/INDEX.md` e `docs/throat_adapter.md` aggiornati.

## 2.6.1 (2026-06-04)

- **Fix gradino esterno al raccordo throat adapter↔corno** (`src/throat_adapter.py`): in modalità flangiata l'adattatore calcolava la parete esterna con un offset **radiale dall'origine** (`outer = inner·(1+wt/r)`), che combacia col centro dei lati ma **rientra agli angoli**, mentre i corni offsettano la parete in **normale/per-faccia** (`R_o = R_i + thickness/cos(π/n)`). Risultato: il bore era continuo ma la parete esterna saltava di ~2 mm alla giunzione (*"dentro ok, fuori il gradino"*). Ora l'outer usa un vero **offset normale (miter)** (`_offset_polygon_outward`) → spessore parete costante, identico a quello del corno → parete esterna **a filo**. Nuovi helper `_offset_polygon_outward` + `_signed_area` (winding-aware, miter clampato a `cos_half ≥ 0.2` sugli angoli vivi).
- **Fix non-manifold + ledge alla flangia rettangolare di bocca** (`ui_app.py`): i fori delle flange rettangolari (gola/bocca/mid) erano dimensionati **esattamente** sulla parete esterna del corno. Foro == parete esterna → facce coincidenti/coplanari → l'unione manifold è degenere e lascia **1 non-manifold edge** + un ledge visibile sul foro. Le flange ora **mordono** la parete di `_FLANGE_WALL_BITE` = 0.5 mm/lato → saldatura volumetrica pulita (stesso principio dei giunti dei petali). *Nota:* compromesso strutturale — una flangia piatta non può essere a filo su entrambi i lati di una parete che svasa; resta un micro-gradino esterno di 0.5 mm sulla flangia.
- **Test**: 71 funzionali + 33 geometria (104 totali), tutti verdi. 2 nuovi: `adapter outer wall flush with horn (no step)`, `rect mouth flange wall-bite (no non-manifold edge)`.
- **Docs**: `docs/throat_adapter.md` aggiornato (helper di offset + modalità flangiata) per la regola docs-in-sync.

## 2.6.0 (2026-06-04)

- **Throat adapter / attacco filettato (`src/throat_adapter.py`)**: nuovo modulo per la flangia di gola che supporta un **adattatore tondo→rettangolare/poligonale** con interfaccia filettata. L'adattatore crea una transizione fluida (morphing) dall'uscita tonda del driver alla gola rettangolare/poligonale del corno, mantenendo la legge d'area del profilo di espansione. Il **filetto è modellato con profilo UNF 60°** tramite rivoluzione sinusoidale del profilo (r, z) — nessuna operazione booleana. Le taglie threaded originarie sono state sostituite in 2.10.0 dal solo attacco 1⅜"-18 con foro acustico da 25 mm.
- **ThreadSpec**: dataclass con specifiche geometriche dei filetti (major_diam, pitch, tpi).
- **UI — Throat Adapter**: nuova sezione nella flangia di gola per sezioni Rettangolare/Poligonale: checkbox "Include shape adapter", scelta Flanged/Threaded, lunghezza adattatore e profondità socket filettato. La flangia lato driver (se flangiata) è circolare e si aggancia all'uscita del driver; l'adattatore morphing collega il driver alla gola del corno.
- **Fix profilo spiralato**: allineamento vertici cerchio↔bersaglio a θ=0 in `_rect_points` e `_poly_points` — il loft non ha più torsione elicoidale.
- **Fix outer target**: l'adattatore filettato passa le dimensioni esterne del corno (`_rect_w_o_0` / `_rect_h_o_0`) come outer target, così l'outer wall dell'adattatore si aggancia all'ESTERNO della gola e l'inner wall all'INTERNO — parete continua senza scalini.
- **Test**: 69 test funzionali + 33 geometria (102 totali), tutti verdi. 11 nuovi test per `throat_adapter`.

## 2.5.0 (2026-06-03)

- **Iwata fedele (pavillon l'Audiophile, JBL 2440/375)**: il profilo "Iwata" non è più un clone assialsimmetrico di Salmon T=0.707, ma la geometria reale ricostruita dal piano originale — un corno **rettangolare a doppio flare** (larghezza e altezza con tassi diversi: gola 50×50 → bocca 740×320, aspect 1:1 → 2.3:1). Nuova `rectangular_horn.get_iwata_horn(throat, length)`. La sezione Iwata è auto-rettangolare e ignora il selettore Section (come il radiale); input ridotti a gola Ø + lunghezza (mouth, aspect e Fc sono intrinseci e derivati).
- **Bocca ad arco (vista in pianta)**: la bocca nel piano orizzontale è un arco circolare (r=692 mm nativo attorno all'apice "point R", ~120 mm dietro la gola), piatta in elevazione — come da disegno. Realizzata per **intersezione booleana** del loft con un cilindro lungo l'altezza (`iwata_arc_mouth()`), 256 facce per un arco liscio. Flangia di bocca disabilitata per l'Iwata (bocca curva). Conferma da Petoin (petoindominique.fr): l'Iwata è di fatto un Le Cléac'h, legge d'area hypex F≈207 Hz, T≈0.5.
- **Profilo liscio**: `_iwata_smooth` rimpiazza l'interpolazione PCHIP punto-per-punto con un fit monòtono liscio (cubica in log-space, estremi ancorati) — toglie il rumore di digitalizzazione che appariva come ondulazioni sulla parete (curviness 0.005 vs 0.026), gola/bocca esatte.
- **Velocità del suono regolabile**: nuovo campo "Speed of sound (m/s)" (Advanced settings, default 344 = Hornresp), propagato a tutta la matematica dei flare tramite override dei global di modulo. Rimossi i `343_000` hardcoded nei readout Fc tractrix.
- **Warning adeguatezza bocca**: il pannello Computed avvisa quando il Ø-equivalente della bocca è sotto `c/(π·fc)` (circonferenza bocca < lunghezza d'onda al taglio) → il cutoff reale sarà più alto di quello impostato.
- **UI prima sezione ridisegnata**: blocchi separati Shape (Profile + Section) / "You set" (solo input attivi) / "Computed" (`st.metric`, niente più campi grigi disabilitati). Spessore parete, punti profilo e velocità del suono spostati nell'expander "Advanced settings".
- **Flange**: parametro `bolt_phase` in `generate_flange`, `generate_polygonal_flange`, `generate_rectangular_flange` per allineare i bulloni a vertici o mezzerie.
- **Pulizia**: rimossi i rami `get_iwata` assialsimmetrici ormai irraggiungibili nella UI (l'Iwata assiale resta solo per la CLI).
- **Test**: 58 test, tutti verdi (3 nuovi per l'Iwata: riproduzione piano, scala, bocca ad arco watertight).

## 2.4.6 (2026-06-02)

- **Sezione Rectangular reinserita nella UI**: quarta opzione in `section_type` radio (dopo Polygonal). Dimensioni W×H invece di Ø, aspect ratio slider, hint dedicato.
- **Profili rettangolari**: chiama `get_rectangular_tractrix()`, `get_rectangular_exponential()`, `get_rectangular_salmon()`, oppure `_area_to_rect()` per Iwata/Le Cléac'h.
- **Preview 2D rettangolare**: mostra W(z) e H(z) affiancati.
- **Flange rettangolari** (gola/bocca/mid): generate con `generate_rectangular_flange()`, outer shape "Circular" o "Rectangular". Foro allineato alle dimensioni esterne reali del corno (conto tenuto del clip `z_o` dell'engine).
- **Fix offset flangia rettangolare**: `generate_rectangular_flange` interpreta `offset` come fondo (non top come `generate_flange`). Passati offset corretti: gola `z_min + ft_off`, bocca `z_mouth + fm_off - fm_sp`, mid `z_mid - mid_sp`.
- **Fix outer_diam mancante**: quando outer è "Circular" passato `outer_diam=X` invece del default 70mm che causava auto-espansione a `sqrt(w²+h²)+24`.
- **Fix mesh non‑manifold**: `horn.fix_normals()` dopo `generate_rectangular_3d_mesh()` — il winding inconsistente impediva a manifold3d di processare il mesh.
- **Test**: 54 test, tutti verdi.

## 2.4.3 (2026-06-02)

- **Clearance regolabile giunto petali**: nuovo parametro `clearance` in `slice_into_petals()` (default 0.1 mm). La lingua viene rimpicciolita di `clearance/2`, la cava viene allargata di `clearance/2` → gioco totale `clearance` mm (0.05 mm per parte al default). Controllo UI "Clearance (mm)" in Tab Slice STL sotto il checkbox del giunto radiale.
- **Tolleranza 0.05 mm per parte**: `add_radial_tongue` buffer `-(margin + clearance/2)`, `add_radial_groove` buffer `-(margin - clearance/2)`. Con margin=0.5 e clearance=0.1 il gioco risultante è 0.1 mm totale.
- **Test**: 54 test, tutti verdi.

## 2.4.2 (2026-06-02)

- **Fix giunto radiale a 2 petali**: prima il caso `n=2` faceva il joint su una sola faccia (lo step a tutta faccia cancellava il materiale della lingua, che falliva silenziosamente). Causa: con 2 petali i due piani di taglio sono complanari (`normal0 == normal1`) — un unico piano diametrale che attraversa l'asse e taglia la parete in **due strisce**, mentre `_seam_face_polygon` ne teneva solo la più grande.
- **Petali ermafroditi (maschio + femmina su ogni pezzo)**: nel caso `n=2` ogni metà riceve ora una **lingua su una striscia e una scanalatura sull'altra**; l'assegnazione si inverte fra le due metà (`side`/`axis` rispetto a un asse globale fisso) così che maschio e femmina si fronteggino sempre. Le due metà risultano **pezzi identici** (uno è l'altro ruotato di 180° attorno a Z). Per `n>=3` il comportamento (scanalatura a sinistra + lingua a destra) è invariato.
- **`_seam_face_polygon` → `_seam_face_polygons`**: ritorna tutte le strisce significative della sezione del seam (sliver sotto il 5% dell'area massima scartati); `add_radial_tongue`/`add_radial_groove` iterano su tutte le strisce e accettano un selettore `side`/`axis` (via `_filter_polys_by_side`) per limitare il giunto a una striscia.
- **Lingua con overlap nel corpo**: la lingua parte ora da `z=-overlap` così da compenetrare il petalo — un contatto puramente complanare non si saldava in modo affidabile nella union (causava `body_count == 2`). Rimossa la funzione `_apply_step_joint` non più usata.
- **Test**: check `n=2` rinforzato — verifica che ogni petalo abbia una lingua che sporge oltre il seam su una striscia e che le due metà siano pezzi identici (54 test, tutti verdi).

## 2.4.1 (2026-06-02)

- **Radial joint (tongue & groove)**: nuovo interlock per petali radiali. Ogni petalo riceve una lingua maschio su un seam e una scanalatura femmina sull'altro. Supportato per 2+ petali:
  - 2 petali: step joint (intera faccia arretrata 2mm) + lingua sporgente
  - 3+ petali: scanalatura centrale 2mm + lingua sporgente 2mm
  - `slice_into_petals()` ora accetta parametri `joint_depth` e `joint_margin`
- **Fix robustezza booleane**: overlap di 1mm nelle estrusioni per evitare facce coincidenti con manifold3d; re-merge dei corpi a volume negativo dopo union
- **Fix `_seam_face_polygon`**: `to_2D(normal=normal)` esplicito per allineamento corretto del sistema di riferimento; filtro `None` in `polygons_closed` che causava crash con 3 petali
- **UI — Controllo "Radial joint (tongue & groove)"**: checkbox + joint depth in Tab 3 (Slice STL), disabilitato di default

## 2.4.0 (2026-06-02)

- **Spessore parete costante (vero offset 3D)**: l'engine assisimmetrico (`profile_generator.py`) ora usa un offset parallelo puro lungo la normale del meridiano — per un solido di rivoluzione coincide con un offset 3D, quindi lo spessore perpendicolare è **costante ovunque** (verificato min=max=thickness). Rimosso lo shift assiale `z_o -= z_o[0]` che assottigliava progressivamente la parete verso la bocca (fino a ~0.8 mm su 4).
- **Base gola tagliata piatta**: poiché l'offset parallelo lascerebbe il bordo di gola inclinato, la base viene sezionata con un piano e richiusa via trimesh → faccia di gola perfettamente planare, mantenendo lo spessore uniforme sulle pareti.
- **Mouth flange a filo**: lo spessore di default della mouth flange ora è l'**estensione assiale** della parete alla bocca (`thickness·|n_z|`), non lo spessore lungo la normale. La flangia termina a filo con il flare, senza bordino sporgente. Si riallinea automaticamente al cambio di wall thickness.
- **Petali senza tasselli**: rimosso l'interlock a tassello (tab/slot alternati) dai seam radiali; `slice_into_petals()` taglia con seam piatti puliti. Rimosse le funzioni helper non più usate.
- **2D Preview parallelo**: la linea "+ wall" del preview ora disegna l'offset parallelo lungo la normale (sia circolare che poligonale), coerente con la geometria stampata, invece di un offset radiale a Z costante.
- **`make run` / `run.sh`**: avvia l'app e la apre in Safari (Streamlit headless + `open -a Safari`).
- **`requirements.txt` / `pyproject.toml`**: `trimesh[easy]` per includere le dipendenze opzionali (networkx, rtree, …) necessarie allo slicing dei petali.

## 2.3.0 (2026-06-01)

- **`get_iwata()`** renamed to **`get_salmon(T)`** — la formula è Salmon hyperbolic-exponential, non Iwata. Parametro `T` variabile (0=catenoidale, 0.707=Hypex, 1=exponenziale).
- **Nuovo preset `get_iwata()`** — wrapper per `get_salmon(T=0.707)`, per chi cerca il nome classico Iwata.
- **Nuovo `get_lecleach()`** — ODE isofase con legge d'area Salmon + parametro `max_angle` (roll-back 90-180°). Corrisponde al flare type "Le Cléac'h" di Hornresp.
- **Rimosso `get_rectangular_iwata()`** → rinominato `get_rectangular_salmon()`.
- **`src/_slicer.py`** — nuovo modulo per sezionare mesh STL in segmenti assiali e petali radiali.
- **UI — Sezione "Slice STL"**: taglio assiale (per conteggio o altezza) + petali radiali con conteggio variabile per segmento. Download singolo o ZIP.
- **UI — Flange**: Mouth flange disabilitata su Le Cléac'h (roll-back incompatibile). Mid-flange attivo di default su Le Cléac'h.
- **UI — Helper cm²**: sotto Throat/Mouth Ø mostra area equivalente in cm² (formato Hornresp).
- **Documentazione**: AGENTS.md, CLAUDE.md, README.md allineati ai nuovi nomi.

## 2.2.10 (2026-06-01)

- **Removed `get_lecleach()`**: profilo ODE isofase rimosso. Non corrispondeva al "Le Cléac'h horn" della comunità audio (che è `get_iwata(T=0.707)`). Rimossi tutti i riferimenti da UI, CLI, test, radial/rectangular horn e docs.

## 2.2.9 (2026-06-01)

- **Buy Me a Coffee button**: a "☕ Buy me a coffee" link button in the header. Set `BMC_USERNAME` at the top of `ui_app.py`; until it's filled in, the button hides and shows a reminder instead of a broken link.

## 2.2.8 (2026-06-01)

UI clarity pass on the dimensions inputs, plus three flange-parameter bugs found
by actually measuring the generated solid instead of trusting that the value reached
it. All in `ui_app.py`.

### Dimensions inputs

- Each profile is driven by a different set of inputs (Tractrix: throat+mouth; Le Cléac'h: throat+Fc; Iwata: throat+Fc+length; Exponential: throat+mouth+Fc). A one-line hint now states which you set and which follow.
- The fields you don't set are no longer blank or a cryptic "—". They show the **computed value live, greyed out** — Le Cléac'h shows the resulting mouth Ø, Tractrix shows the derived Fc and length, etc. Implemented by reading the editable inputs first, solving the profile once, then filling the read-only fields.
- Per-profile help on Fc (flare rate for Exponential vs cutoff for Le Cléac'h/Iwata); units unified (polygonal mouth shown as a diameter across corners).

### Flange bolt circle — three bugs

- **Polygonal outer was ignored on circular-hole flanges**: `generate_flange` rendered a circle no matter the selection. (Fixed in the engine in 2.2.7; the UI now passes `outer_n_sides` through for throat/mouth/mid.)
- **Editing the bolt circle did nothing**: the widgets used the `st.number_input(value=…, key=…)` anti-pattern, so the recomputed default fought the user's value on every rerun. Switched to the canonical pattern — seed `session_state` once if absent, then create the widget with `key` and no `value`. The radial throat bolt circle also shared key `ft_bc` with the non-radial one (a latent crash when switching sections); it now has its own key.
- **Moving bolts outward made them vanish, or (after a first fix) wrongly grew the flange**: the bolt circle is now clamped to a valid band inside the ring — from just outside the hole to just inside the outer edge (the inradius, on polygons). The flange size is set solely by the ring width; the bolts slide within it and can't be pushed off the edge. To seat bolts further out you widen the ring. Verified by measuring bolt-hole radii in the generated mesh across the range.

### Robustness

- `_clamp_state` keeps a persisted widget value within its current min/max before the widget is created, so changing the horn (which changes the flange bounds) can't raise `StreamlitValueAboveMaxError` mid-run.

## 2.2.7 (2026-05-31)

Cross-section overhaul plus a round of flange-correctness fixes. Most of these were
bugs that produced a plausible-looking but wrong solid — the kind you only catch when
you load the STL in a slicer, which is exactly why this release also rewrites the tests.

### Cross-section is now its own axis

- **Polygonal section** replaces Rectangular: regular N-gon (3–12 sides) at every Z slice, area-matched to the equivalent circle. The old rectangular lofting engine is gone.
- **Radial 360°** is no longer a separate "profile" — it's a section type, so it now composes with all four expansion curves (Tractrix, Le Cléac'h, Iwata, Exponential), not just exponential.
- The model is now cleanly **4 expansion profiles × 3 sections** (Circular, Polygonal, Radial), instead of profiles and sections being tangled together.

### Exponential + Circular was silently broken

`get_exponential` only existed inline in the UI, and only on the Polygonal path. With a
Circular section the code fell through to `get_iwata` in **five** places — mouth input,
derived metrics, 2D preview, flange sizing, and final generation — so you'd ask for an
exponential horn and quietly get an Iwata. Extracted `get_exponential` to
`profile_generator.py` as a first-class profile and wired all five paths to it.

### Polygonal flange outer shape

- `generate_flange` ignored `outer_n_sides`, so selecting a "Polygonal" outer on a circular-hole flange always rendered a **circle**. Added the parameter; the outer body can now be an N-gon prism.
- **Ring width on polygonal outers now means wall thickness at the flat faces** (the minimum wall), with circumradius `= (inner_R + ring) / cos(π/N)`. Before, ring width was the corner extension, so for a large hole the flat-face wall went negative and the round hole punched through the polygon edges — leaving four detached corner triangles. With the new definition the default 15 mm is valid for any side count and the wall is uniform where it's thinnest.
- **Auto-expand guard**: if the inner hole would still exceed the polygon inradius, `flange_R` grows to fit instead of producing a broken solid.
- Reordered the flange input blocks (outer-shape selector before ring width), which also removes a latent `NameError` that would fire the moment you picked Polygonal.

### Other fixes

- **Mid flange** distance is clamped to the horn length, and the midpoint percentage is clamped to 100 — it was indexing past the end of the profile array.
- **Le Cléac'h mouth flange** hole is now sized `inner_R + thickness` like every other circular profile; it was missing the wall offset, so the hole sat on the inner wall instead of the outer.
- `generate_flange` defaults `output_path=None` — it no longer writes `io/flange.stl` as a side effect on every UI generation.

### Tests

- `tests/test_all.py` rewritten: **18 → 54**. Real geometric assertions (watertight, single body, positive volume, correct mouth radius) across the full profile × section matrix, instead of "didn't throw".
- New `tests/test_geometry.py` (**36 tests**): checks output *shape* the way you would in a slicer — sections the mesh, isolates the outer contour, and measures `max_r / min_r` (1.0 = circle, `1/cos(π/N)` = N-gon). This is the test that catches "polygonal flange came out round" and "ring width isn't a uniform 15 mm wall".

### Dependencies

- `shapely>=2.0.0` (polygon extrusion for N-gon flange bodies)

## 2.2.6 (2026-05-31)

- **Renamed to flare_forge**: new brand name throughout — UI title, page tab, STEP export header, package name, download filenames
- **Full English translation**: all UI labels, captions, subheaders, button text, metrics, variable names (`espansione` → `profile_type`, `spessore` → `thickness`, `gola_out` → `throat_outer`, etc.), session state keys
- **STEP export rewritten**: correct AP203 schema — `FACETED_BREP` + `FACE_OUTER_BOUND` + `POLY_LOOP` (previously `MANIFOLD_SOLID_BREP` + `POLY_LOOP` was invalid and rejected by FreeCAD / Fusion 360 / SolidWorks); correct `PRODUCT_DEFINITION` chain; file 5× smaller (no per-triangle `DIRECTION`/`PLANE` entities)
- **Bug fix**: `_get_rect_profile` was defined after its first call — rectangular exponential metrics were silently never shown
- **Dead code removed**: unreachable second `elif is_rect` block in 2D preview; duplicate `get_rectangular_lecleach` / `get_rectangular_iwata` definitions with unreachable code in `rectangular_horn.py`; unused `_PROFILES` dict in `profile_generator.py`; unreachable `args.profile == "iwata"` condition in `resolve_profile`
- **Anti-pattern fix**: `'_var' not in dir()` checks replaced with explicit default initialization for all flange dimension variables

## 2.2.5 (2026-05-30)

- **Z-offset flat bottom fix**: Clipped `z_o` coordinates to the original `[z[0], z[-1]]` range in `rectangular_horn.py` to completely eliminate negative Z protrusions ("bordino") under the throat flange, ensuring a perfectly flat base.
- **Streamlit hot reload**: Added explicit `importlib.reload()` for all core generator modules at the top of `ui_app.py` to bypass Streamlit's module caching, ensuring that all subsequent code modifications immediately take effect in the active dashboard.
- **Agent instructions**: Updated `AGENTS.md` with guidelines on Streamlit module caching and hot reloading to prevent future caching issues.

## 2.2.4 (2026-05-29)

- **Architecture**: removed all `importlib.machinery.SourceFileLoader` — standard Python imports throughout
- **File rename**: `0*_*.py` → descriptive names (`profile_generator.py`, `flange_generator.py`, etc.)
- **ODE solver**: `get_lecleach` refactored to `scipy.integrate.solve_ivp` with RK45 + termination event
- **No vertex inference**: flange hole dimensions from analytical profile values, not 3D mesh sampling
- **STEP export**: download button alongside STL, uses `_step_export.py` for AP242 conversion
- **State management**: `on_change` callbacks on horn widgets, targeted `pop()` instead of destructive `del`
- **Rectangular flange patch**: `offset` parameter, `bolt_inset`, safety clamps, `thickness*3` boolean cylinders
- **LeCléac'h mouth fix**: hole sized from roll-back endpoint with 30mm shrink + 5mm minimum wall
- **Radial assembly**: both bottom + top in one STL, properly spaced by acoustic gap, top reflector rebuilt solid
- **Expansion × Section**: all 4 expansion types (Tractrix, LeCléac'h, Iwata, Exponential) × 2 sections (Circular, Rectangular)
- **Import/export**: standard `from src import profile_generator`, all tests pass from project root

## 2.2.3 (2026-05-29)

- **Refactored UI**: single-view monotab dashboard — Horn Profile + 2D Preview | Flanges | Assembly
- **Per-flange outer shape selector**: Circular (disc) or Rectangular (plate) — independently for throat, mouth, mid
- **Inner hole always matches horn profile**: circular for axisymmetric, rectangular for rectangular horns
- **Live 2D preview**: reactive Matplotlib plot, no "Show Preview" button
- **Smart rectangular defaults**: outer OD = corner diagonal + wall + 15mm, bolt circle = midpoint
- **Mid flange**: Z-offset from throat input, dimensions auto-intercepted from horn profile at that position
- **Rectangular flange outer W×H**: adjustable independent dimensions when Rectangular outer selected
- **`generate_rectangular_flange`**: accepts optional `outer_w`/`outer_h` for custom rectangular plate dimensions

## 2.2.2 (2026-05-28)

- **Three-column wide layout**: Horn Profile (left) | Flanges (center) | Assembly + Download (right) — no scrolling needed
- **Compact flange inputs**: Throat / Mouth / Mid in 3 side-by-side columns with collapsed labels
- **Compact metrics**: replaced `st.metric` with markdown for smaller result display
- Mid flange always visible (removed expander)

## 2.2.1 (2026-05-28)

- **English UI**: complete rewrite with proper acoustic terminology (throat, mouth, bolt circle, PCD)
- **Auto-recalculate on profile change**: flange defaults update automatically when switching profiles
- **LeCleach safety clamp**: flange OD capped at mouth diameter, hole auto-adjusted to fit
- **Duplicate element ID fix**: unique keys for all repeated labels (thickness, bolt count, etc.)
- **Integration test**: 5-profile full assembly test (`tests/test_integration.py`) — tractrix, lecleach, iwata, rectangular, radial — all watertight
- Fixed LeCleach inward flange logic in integration test

## 2.2.0 (2026-05-28)

- **Mid flange**: third adjustable flange at any position (5-95% of horn length), auto-calculated hole & bolt circle
- **Selective generation**: checkboxes to toggle horn, throat flange, mid flange, mouth flange independently before assembly
- Fixed stray `NameError` on mid flange variable for radial profiles
- Fixed `_tris`/`_vol` variable ordering in metrics display

## 2.1.0 (2026-05-28)

- **Flange calculator**: "Calcola flange" button auto-computes all diameters (outer, bolt circle) from horn geometry with real 2D profile generation for Le Cleac'h / Iwata
- **Le Cleac'h mouth flange**: positioned at roll-back (max radius), extruded backward, 10mm flange ring goes *inward* (verso il centro) instead of outward — outer edge flush with mouth, hole 20mm smaller
- **Derived metrics**: automatic display of Fc (tractrix), length, and mouth diameter on every parameter change
- Mouth flange hole sizing now profile-aware: local radius for standard profiles, max radius for Le Cleac'h roll-back
- Simplified flange parameter UI: session-state driven inputs, removed scattered inline computations

## 2.0.0 (2026-05-28)

- Circular flange rewritten with CSG boolean operations (trimesh + manifold3d): bolt holes are now genuine cutouts, no more overlapping geometry artifacts
- Fixed throat Z-alignment: outer and inner profiles now share the same Z origin, ensuring a flat bottom annulus for perfect flange mating
- Fixed mouth flange positioning: uses max Z instead of max-radius vertex, eliminating gap (was 3mm on tractrix, 84mm on Le Cleac'h)
- Throat flange now grows upward (into horn body) instead of downward, ensuring proper boolean union merge
- Shared constants module (`src/_constants.py`): single source for SOUND_SPEED
- Shared utilities module (`src/_utils.py`): compute_profile_normals, ensure_positive_volume, align_z_to_zero
- CLI orchestrator rewritten: direct function calls via importlib instead of subprocess
- Web UI: unified lazy-import helper, radial horn uses temp files, circular flange returns trimesh directly
- Cleaned up dead code: removed unused `_bc()` function from radial horn, simplified redundant expression
- Added `pyproject.toml`, `manifold3d` and `streamlit` to dependencies
- README: corrected test count (16 → 18), updated project structure

## 1.4.0 (2026-05-26)

- Rectangular flange: circular outer shape, rectangular inner hole, N bolts on adjustable circle
- Web UI: flange type selector with circular/rectangular options
- Merge Tab: concatenation for rectangular horn+flange (no boolean)

## 1.3.0 (2026-05-26)

- Fixed radial horn: `_revolve_polygon` replaces `_revolve_profile` (no center caps, closed 4-loop)
- Fixed UI: guard `if profile not in ("rectangular", "radial")` prevents `z=None` error
- Added comprehensive test suite (`tests/test_all.py`): 16 tests, all profiles
- Added radial horn to Web UI (dual-piece download)
- Rectangular horn engine + Web UI integration

## 1.0.0 (2026-05-26)

- Initial release
- Three acoustic profiles: Tractrix, Le Cléac'h (Euler integration with 160° roll-back), Iwata (Salmon T=0.707)
- Shared 3D mesh engine: normal-vector offset, revolution, watertight STL
- Parametric circular flange generator (outer/inner diameter, bolt holes)
- Web UI (Streamlit) with horn, flange, and merge tabs
- CLI orchestrator (`python -m src.main`)
- Cutoff frequency (Fc) calculation and display for all profiles
- Boundary protection for degenerate profiles
- Automatic normal flip on negative volume
- Multi-section horn splitting for 250mm³ printers
- Merge flange + horn into single watertight STL
- **Spessore Elliptical nei roll-back** (`profile_generator.py`, `ui_app.py`): sostituito l'offset radiale `rx+t`, `ry+t` con un vero offset lungo la normale 3D della superficie. R-OSSE e altri profili che tornano indietro mantengono ora lo spessore perpendicolare impostato; anche i calcoli esterni della UI usano la stessa superficie.
- **Fix artefatto petali sui roll-back** (`_slicer.py`): con 2 petali i due limiti coincidono sullo stesso piano diametrale; ora viene applicato un solo taglio/cap invece di richiudere due volte facce coplanari, eliminando la riga di z-fighting visibile in Bambu Studio.
