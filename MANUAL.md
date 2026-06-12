# flare_forge — Manuale / Manual

> Scritto nello stile di "antirez". Non sono parole sue reali: è un'imitazione
> voluta dall'autore del progetto. Prendetela per quello che è — consigli diretti
> e codice che gira.
>
> Written in the style of "antirez". These are **not** his real words: it's a
> deliberate impersonation requested by the project author. Take it for what it
> is — blunt advice and code that runs.

---

## 0. Prima di tutto / First of all

**IT** — Questo non è un framework. È un attrezzo che fa una cosa: prende dei
numeri (gola, bocca, frequenza di taglio) e ti sputa fuori un STL di una tromba
acustica pronto da stampare. Tutto il resto del manuale serve solo a spiegarti
come girare quei numeri. Se ti perdi, torna a questa frase.

**EN** — This is not a framework. It's a tool that does one thing: you give it
numbers (throat, mouth, cutoff frequency) and it spits out a printable STL of an
acoustic horn. Everything else in this manual just explains how to turn those
numbers. If you get lost, come back to this sentence.

La regola d'oro del progetto, quella che devi tenere in testa sempre / The one
rule to keep in your head:

> **Due strati. / Two layers.**
> Lo strato **matematico** ritorna solo `(z, r)` — la curva, nient'altro.
> Lo strato **mesh** prende un qualsiasi `(z, r)` valido e lo trasforma in solido.
> The **math** layer returns only `(z, r)` — the curve, nothing else.
> The **mesh** layer takes any valid `(z, r)` and turns it into a solid.

Se capisci questo, capisci il 90% del codice. Il restante 10% sono i casi
speciali (Iwata, radiale) che hanno il loro motore perché la realtà è disordinata.

---

## 1. Installazione / Installation

```bash
make install          # crea .venv e installa le dipendenze / create .venv + deps
make dev              # come sopra + ruff (lint/format)       / same + ruff

# verifica che tutto giri / check everything runs
make test
```

**IT** — Se `make test` non finisce in verde, **fermati lì**. Non costruire niente
sopra una base che non passa i test. È la cosa più importante che ti dico in tutto
il manuale.

**EN** — If `make test` doesn't end green, **stop right there**. Don't build
anything on top of a base that fails its tests. It's the most important thing I'll
tell you in this whole manual.

Tutti i file generati finiscono in `io/`. / All generated files land in `io/`.

---

## 2. Quickstart — la CLI / The CLI

**IT** — Il modo più veloce per avere un STL in mano. Un comando, un file.

**EN** — The fastest way to hold an STL. One command, one file.

```bash
# Tractrix: dai gola e bocca / give throat and mouth
python -m src.main --throat 20 --mouth 100 --output io/horn.stl

# Esponenziale/Salmon: dai gola e frequenza di taglio / throat + cutoff freq
python -m src.main --throat 20 --fc 800 --output io/horn.stl

# Salmon con lunghezza e profilo esplicito / explicit length + profile
python -m src.main --profile salmon --throat 20 --fc 600 --length 80 \
    --output io/horn.stl
```

Argomenti che contano / arguments that matter:

| Flag | IT | EN |
|---|---|---|
| `--throat` | diametro gola (mm), **obbligatorio** | throat diameter (mm), **required** |
| `--mouth` | diametro bocca (tractrix) | mouth diameter (tractrix) |
| `--fc` | frequenza di taglio Hz (exp/salmon) | cutoff frequency Hz (exp/salmon) |
| `--length` | lunghezza assiale (salmon/oblate) | axial length (salmon/oblate) |
| `--profile` | `auto`/`tractrix`/`salmon`/`iwata`/`lecleach`/`oblate` | same |
| `--thickness` | spessore parete, default 4 mm | wall thickness, default 4 mm |
| `--output` | path del file, **obbligatorio** | file path, **required** |

**Nota da amico / friendly note:** `--profile auto` indovina il profilo dai
parametri che gli passi. Va benissimo per provare. Quando fai sul serio, scrivi
il profilo esplicito — il "magico" un giorno indovina diverso da quello che
volevi.

---

## 3. Tutorial — lo strato matematico / The math layer

**IT** — Queste funzioni vivono in `src/profile_generator.py` (assialsimmetriche)
e `src/rectangular_horn.py` (rettangolari). Ritornano **solo array**. Nessun file,
nessun effetto collaterale. Le puoi chiamare, stampare, plottare, senza generare
niente. È il bello dello strato: è puro.

**EN** — These live in `src/profile_generator.py` (axisymmetric) and
`src/rectangular_horn.py` (rectangular). They return **only arrays**. No files,
no side effects. You can call them, print them, plot them, without generating
anything. That's the beauty of the layer: it's pure.

```python
import numpy as np
from src import profile_generator as pg

N = 300   # numero di punti del profilo / number of profile samples

# --- Tractrix: gola → bocca ----------------------------------------------
z, r = pg.get_tractrix(throat=20.0, mouth=100.0, n=N)
print(z[0], r[0]*2)     # z parte da 0, diametro alla gola = throat
print(z[-1], r[-1]*2)   # alla bocca: diametro ≈ mouth

# --- Esponenziale: m = 4π·fc/c -------------------------------------------
z, r = pg.get_exponential(throat=20.0, mouth=100.0, fc=800.0, n=N)

# --- Salmon (ipex, T=0.707 di default) -----------------------------------
z, r = pg.get_salmon(throat=20.0, fc=600.0, length=80.0, n=N, T=0.707)
#   T=0   → catenoidale / catenoidal
#   T<1   → cosh-dominato / cosh-dominated  (0.707 = Hypex classico)
#   T=1   → esponenziale puro / pure exponential
#   T>1   → sinh-dominato / sinh-dominated

# --- Le Cléac'h (fronte d'onda isofase) ----------------------------------
z, r = pg.get_lecleach(throat=20.0, fc=600.0, n=N,
                       T=0.707, max_angle=160.0)

# --- Oblate spheroidal CD (constant directivity) -------------------------
z, r = pg.get_oblate_spheroidal(throat=25.4, coverage_angle=90.0,
                                length=70.0, n=N)
#   coverage_angle = angolo di copertura TOTALE / TOTAL coverage angle
#   (theta del cono asintotico = coverage/2)
```

**Tutte queste funzioni rispettano lo stesso contratto / they all honor the same
contract:**

```python
assert z[0] == 0.0          # la gola è all'origine / throat at origin
assert r[0] == throat / 2   # raggio iniziale = mezza gola
assert np.all(np.diff(r) >= 0)  # il raggio non torna mai indietro / monotone
```

**IT** — Se scrivi un tuo profilo nuovo, deve rispettare questo contratto e basta.
Niente di più. Il motore mesh non sa e non vuole sapere *quale* curva gli stai
dando. Gli dai `(z, r)` validi, lui ti fa il solido. Questa è la cosa giusta.

**EN** — If you write a new profile, it just has to honor this contract. Nothing
more. The mesh engine neither knows nor wants to know *which* curve you're handing
it. Give it valid `(z, r)`, it gives you the solid. That's the right thing.

### Profili rettangolari / Rectangular profiles

Stesso spirito, ma ritornano **tre** array `(z, w, h)` — larghezza e altezza.
Same spirit, but they return **three** arrays `(z, w, h)` — width and height.

```python
from src import rectangular_horn as rh

z, w, h = rh.get_rectangular_salmon(...)        # vedi firma nel sorgente
z, w, h = rh.get_rectangular_oblate_spheroidal(...)

# L'Iwata vero (l'Audiophile), il caso speciale / the real Iwata, the special case
z, w, h = rh.get_iwata_horn(throat=50.0, length=572.0, n=300)
#   Con i default riproduce il disegno originale: bocca ≈ 740×320, gola ≈ 50×50.
#   With defaults it reproduces the original drawing.
```

---

## 4. Tutorial — lo strato mesh / The mesh layer

**IT** — Qui i numeri diventano triangoli. La funzione chiave è una sola e mangia
qualsiasi `(z, r)`:

**EN** — Here numbers become triangles. There's one key function and it eats any
`(z, r)`:

```python
from src import profile_generator as pg

z, r = pg.get_salmon(20.0, 600.0, 80.0, 300)

m = pg.generate_3d_mesh_from_profile(
    z, r,
    thickness=4.0,        # spessore parete, costante e perpendicolare / wall thickness
    rings=64,             # segmenti attorno all'asse / segments around the axis
    output_path="io/horn.stl",
)
# m è un numpy-stl mesh.Mesh; il file è già salvato. / file is already saved.
```

**Cosa fa dentro, in 5 passi / what it does inside, in 5 steps:**

1. Calcola le normali del profilo (gradiente alle differenze finite).
2. Sposta il profilo interno di `thickness` **lungo la normale** → profilo esterno.
   Questo dà uno spessore *perpendicolare costante* (offset parallelo vero), non
   uno spessore assiale.
3. Rivoluziona entrambi i profili attorno a Z; tappa cima e fondo.
4. Taglia la base della gola con un piano (lo spessore costante lascia un bordo
   inclinato) e ri-tappa.
5. Salva e ritorna.

**IT — la trappola da conoscere:** poiché lo spessore è perpendicolare, la parete
alla bocca **non** ha estensione assiale pari a `thickness`. Se ti serve l'estensione
assiale (per esempio per una flangia a filo bocca) devi rifare lo stesso conto:
`z_o = z_i + n_z · thickness`. Questo è scritto in `CLAUDE.md` e va tenuto in sync.
Non indovinare, ricalcola.

**EN — the trap to know:** because thickness is perpendicular, the wall at the
mouth does **not** have axial extent equal to `thickness`. If you need the axial
extent (e.g. a mouth-flush flange) you must redo the same math:
`z_o = z_i + n_z · thickness`. This is documented in `CLAUDE.md` and must stay in
sync. Don't guess, recompute.

### Gli altri motori / The other engines

| Funzione / Function | Modulo | Ingresso / Input |
|---|---|---|
| `generate_3d_mesh_from_profile(z, r, ...)` | `profile_generator.py` | assialsimmetrico / axisymmetric |
| `generate_rectangular_3d_mesh(z, w, h, ...)` | `rectangular_horn.py` | rettangolare / rectangular |
| `generate_polygonal_3d_mesh(z, r_eq, n_sides, ...)` | `polygonal_horn.py` | N-gono / N-gon (3–12 lati) |
| `generate_radial_horn(throat, mouth, fc, ...)` | `radial_horn.py` | API sperimentale non esposta nella UI / experimental API not exposed in UI |

```python
from src import polygonal_horn as ph
from src import rectangular_horn as rh
from src import radial_horn as rd

# Sezione poligonale: r_eq è il raggio equivalente in area / area-equivalent radius
ph.generate_polygonal_3d_mesh(z, r, n_sides=8, thickness=4.0,
                              output_path="io/octo.stl")

# Sezione rettangolare
rh.generate_rectangular_3d_mesh(z, w, h, thickness=4.0,
                                output_path="io/rect.stl")

# Radiale: NON ritorna un pezzo solo — scrive bottom + top / writes TWO files
rd.generate_radial_horn(throat_diam=25.0, mouth_diam=200.0, fc=500.0,
                        output_dir="io", profile="Exponential")
#   → io/radial_bottom.stl  +  io/radial_top.stl
```

**Da ricordare / remember:** il radiale è speciale, esce in **due pezzi** (piatto
inferiore + riflettore superiore) e **non si può fondere** con flange/adapter come
gli altri. Non combatterlo, è fatto così di proposito.

---

## 5. Tutorial — flange / Flanges

**IT** — La flangia è l'anello con i fori per bullone che attacca la tromba al
driver o al baffle. Tre generatori, scegli secondo la forma del foro/corpo:

**EN** — The flange is the bolt-hole ring that mounts the horn to the driver or
baffle. Three generators, pick by hole/body shape:

```python
from src import flange_generator as fg
from src import rectangular_flange as rf

# Flangia circolare (corpo circolare o N-gono) / circular (round or N-gon body)
fg.generate_flange(
    throat_R=12.0,        # raggio foro interno = raggio gola / inner hole radius
    flange_R=30.0,        # raggio esterno / outer radius
    thickness=6.0,
    bolt_R=22.0,          # raggio cerchio bulloni / bolt-circle radius
    bolt_n=4, bolt_d=3.5, # numero e diametro fori / count + diameter
    outer_n_sides=0,      # 0 = circolare; ≥3 = prisma N-gono / N-gon prism
    output_path="io/flange.stl",
)

# Flangia poligonale / polygonal flange
fg.generate_polygonal_flange(...)

# Foro interno rettangolare / rectangular inner hole
rf.generate_rectangular_flange(...)
```

I fori dei bulloni sono **vere sottrazioni booleane** (trimesh), non finta
geometria. The bolt holes are **real boolean cutouts**, not fake geometry.

Per una mouth flange inward sotto un roll-back, la UI costruisce prima piloni
pieni portanti, li interseca con il volume interno alla superficie reale del
flare e infine unisce il risultato. Solo dopo l'unione sottrae i fori vite e le
eventuali sedi testa. I fori esterni restano tondi al diametro del gambo; le
sedi testa sono assiali, concentriche e hanno un unico fondo complanare definito
da `Head depth`.

For an inward mouth flange below a roll-back, the UI first creates full
load-bearing pillars, clips them to the real flare surface, and unions the
result. Screw holes and optional head seats are subtracted only after that
union. External openings remain round at shaft diameter; head seats are axial,
concentric, and terminate on one coplanar floor set by `Head depth`.

---

## 6. Tutorial — throat adapter / L'adattatore di gola

**IT** — L'adapter raccorda il driver rotondo alla gola della tromba (che può
essere tonda, rettangolare o poligonale) con interfaccia **flangiata** o
**filettata** (1" / 1¼" / 2" UNF). È il pezzo geometricamente più complesso del
progetto, quindi qui non ti do tutta la firma a memoria — la trovi in
`docs/throat_adapter.md`, che è la fonte di verità (leggi quello, non il sorgente:
ti risparmia token e tempo).

**EN** — The adapter bridges the round driver to the horn throat (round, rect or
polygonal) with a **flanged** or **threaded 1⅜"-18** interface and a separate
25 mm acoustic bore. It's
the geometrically hairiest part of the project, so I won't recite the full
signature here — it lives in `docs/throat_adapter.md`, the source of truth (read
that, not the source: saves you tokens and time).

```python
from src import throat_adapter as ta

adapter = ta.make_adapter_assembly(
    driver_type="1in", thread_key="1in",
    horn_shape="circular",        # "circular" / "rectangular" / "polygonal"
    adapter_length=30.0,
    wall_thickness=4.0,
    # ... parametri di raccordo C1 e allineamento: vedi docs/throat_adapter.md
    output_path="io/adapter.stl",
)
```

**Consiglio operativo / operational tip:** l'adapter embedded si sovrappone al
flare fino a **6 mm** (`embedded_morph_span()` accorcia prima il trim e poi
l'overlap sui flare corti), seguendo esattamente il contorno reale del flare
nel tratto di overlap. Un contatto solo complanare **non** salda in modo
affidabile in una unione booleana. Se ti escono buchi all'incollatura, la
sovrapposizione è il primo posto dove guardare.

---

## 7. Tutorial — slicing per la stampa / Slicing for printing

**IT** — Una tromba grande non ci sta nel piatto della stampante. Lo slicer la
taglia in pezzi richiudibili. Vive in `src/_slicer.py` e lavora su `trimesh.Trimesh`.

**EN** — A big horn doesn't fit on the print bed. The slicer cuts it into
re-joinable pieces. It lives in `src/_slicer.py` and works on `trimesh.Trimesh`.

```python
import trimesh
from src import _slicer as slc

horn = trimesh.load("io/horn.stl")

# (a) Taglio assiale in N segmenti uguali / axial cut into N equal segments
segments = slc.slice_into_segments(horn, n=3)

# (b) Taglio a quote precise / cut at specific heights
segments = slc.slice_at_heights(horn, heights=[40.0, 90.0])

# (c) Petali radiali con giunto a maschio/femmina / radial petals with T&G joint
petals = slc.slice_into_petals(horn, n=4, joint_depth=2.0, joint_margin=1.0)

# (d) Box per volume di stampa / print-volume boxes
chunks = slc.slice_to_print_volume(horn, max_x=200, max_y=200, max_z=200)
```

**Il caso a 2 petali, da capire / the 2-petal case, worth understanding:** con
`n=2` il giunto è **ermafrodita** — ogni metà ha un maschio su un lato e una
femmina sull'altro, così un dente trova sempre una cava. Le due metà escono
**identiche** (una è l'altra ruotata di 180° attorno a Z). È un bel trucco:
stampi due volte lo stesso pezzo. Per `n≥3` invece: cava centrata sul seam
sinistro, dente centrato sul destro.

**EN — the 2-petal case:** with `n=2` the joint is **hermaphroditic** — each half
has a male tongue on one side and a female groove on the other, so a tongue always
meets a groove. The two halves come out **identical** (one is the other rotated
180° about Z). Nice trick: print the same part twice. For `n≥3`: centered groove
on the left seam, centered tongue on the right.

> **IT** — Lo slicer è l'unico posto dove ci sono `except` che ingoiano i fallimenti
> dei boolean. Se un pezzo esce strano, è il primo sospettato. Non fidarti del
> silenzio.
> **EN** — The slicer is the one place with `except` blocks that swallow boolean
> failures. If a piece comes out wrong, it's the prime suspect. Don't trust the
> silence.

---

## 8. Export STEP / STEP export

```python
from src._step_export import export_step
export_step("io/horn.stl", "io/horn.step")   # AP203
```

Triangoli dentro un guscio STEP. Per CAD/CAM, non per stampa. / Triangles inside a
STEP shell. For CAD/CAM, not for printing.

---

## 9. La UI / The UI

```bash
make run                       # headless + apre Safari / opens Safari
streamlit run ui_app.py        # browser di default / default browser
```

**IT** — La UI (`ui_app.py`) è una dashboard Streamlit a pagina singola con quattro
sezioni in ordine di flusso: **Acoustic Profile → Mounting Flanges → Generate
Assembly → Slice STL**. È un orchestratore: chiama gli stessi moduli `src/` che hai
visto qui sopra. Non c'è magia in più, solo bottoni davanti alle stesse funzioni.

**EN** — The UI (`ui_app.py`) is a single-page Streamlit dashboard with four
sections in flow order: **Acoustic Profile → Mounting Flanges → Generate Assembly
→ Slice STL**. It's an orchestrator: it calls the same `src/` modules you saw
above. No extra magic, just buttons in front of the same functions.

**Una cosa onesta che ti devo dire / one honest thing:** dentro la UI la velocità
del suono `c` viene impostata mutando una variabile globale dei moduli dopo un
`importlib.reload`. Funziona, ma è la parte più fragile del progetto. Se un giorno
un valore di `c` "si attacca" tra una generazione e l'altra, hai trovato il bug —
e nel `TODO.md` c'è già scritto di sistemarlo passando `c` come parametro. Fallo
quando ti dà fastidio per davvero, non prima.

---

## 10. Ricetta completa / End-to-end recipe

**IT** — Dalla curva al pezzo stampabile, tutto in Python, senza UI.
**EN** — From curve to printable piece, all in Python, no UI.

```python
import trimesh
from src import profile_generator as pg
from src import _slicer as slc

# 1. matematica: scegli la curva / math: pick the curve
z, r = pg.get_lecleach(throat=25.4, fc=500.0, n=300, max_angle=160.0)

# 2. mesh: trasformala in solido watertight / turn it into a watertight solid
pg.generate_3d_mesh_from_profile(z, r, thickness=5.0, output_path="io/horn.stl")

# 3. slicing: tagliala per la tua stampante / slice it for your printer
horn = trimesh.load("io/horn.stl")
petals = slc.slice_into_petals(horn, n=4, joint_depth=2.0, joint_margin=1.0)
for i, p in enumerate(petals):
    p.export(f"io/petal_{i}.stl")

# 4. controlla SEMPRE che sia chiuso / ALWAYS check it's closed
print("watertight:", horn.is_watertight, "volume:", horn.volume)
```

---

## 11. Quando qualcosa va storto / When something breaks

| Sintomo / Symptom | IT | EN |
|---|---|---|
| "Your mesh is not closed" | Il pezzo non è watertight: spesso un boolean fallito silenziosamente. Controlla lo slicer/adapter. | Piece isn't watertight: often a silently-failed boolean. Check the slicer/adapter. |
| Buco all'incollatura adapter↔gola | Manca la sovrapposizione (fino a 6 mm via `embedded_morph_span`); un contatto solo complanare non salda. | Missing the weld overlap (up to 6 mm via `embedded_morph_span`); coplanar-only contact does not weld. |
| Flangia non a filo bocca | Hai usato `thickness` come estensione assiale. Ricalcola `z_o = z_i + n_z·thickness`. | You used `thickness` as axial extent. Recompute `z_o = z_i + n_z·thickness`. |
| `pip install .` senza una libreria | Dipendenza solo in `requirements.txt` e non in `pyproject.toml`. C'è un test che lo blinda: fallo girare. | Dep only in `requirements.txt`, not `pyproject.toml`. There's a test guarding this: run it. |
| Profilo "strano" alla gola | `z[0]` deve essere 0 e `r[0]` deve essere `throat/2`. Verifica il contratto. | `z[0]` must be 0, `r[0]` must be `throat/2`. Check the contract. |

---

## 12. Se vuoi estendere / If you want to extend

**IT** — Vuoi aggiungere un profilo tuo? Il percorso è corto e disciplinato:

1. Scrivi `get_miacurva(throat, ...) -> (z, r)` in `profile_generator.py`. Rispetta
   il contratto (`z[0]=0`, `r[0]=throat/2`, monotono). **Nessun side effect.**
2. Aggiungilo alla UI (`ui_app.py`): selectbox, input, ramo di generazione.
3. Aggiorna `docs/profile_generator.md` **nello stesso commit**. Doc disallineato =
   build rotta.
4. Aggiungi un test in `tests/test_all.py`.

**EN** — Want to add your own profile? The path is short and disciplined:

1. Write `get_mycurve(throat, ...) -> (z, r)` in `profile_generator.py`. Honor the
   contract (`z[0]=0`, `r[0]=throat/2`, monotone). **No side effects.**
2. Add it to the UI (`ui_app.py`): selectbox, inputs, generation branch.
3. Update `docs/profile_generator.md` **in the same commit**. Stale doc = broken
   build.
4. Add a test in `tests/test_all.py`.

**L'ultima parola / the last word:**

> Non aggiungere un'astrazione finché non hai **tre** casi che la chiedono. Non
> aggiungere un livello di indirezione per far sembrare il codice "serio". Una
> tromba non ha bisogno di un `BuildResult`. Ha bisogno di uscire watertight.
>
> Don't add an abstraction until **three** cases demand it. Don't add a layer of
> indirection to make the code look "serious". A horn doesn't need a `BuildResult`.
> It needs to come out watertight.

Buon divertimento. / Have fun.

— "antirez"
