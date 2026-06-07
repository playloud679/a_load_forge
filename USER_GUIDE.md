# flare_forge — Guida Utente / User Guide

> Per chi **usa l'app**, non per chi la programma. Niente codice: solo come
> ottenere una tromba acustica stampabile dai controlli dello schermo.
> (Il manuale tecnico per sviluppatori è `MANUAL.md`.)
>
> For people who **use the app**, not who code it. No code: just how to get a
> printable acoustic horn from the on-screen controls.
> (The developer manual is `MANUAL.md`.)

---

## In due righe / In two lines

**IT** — Imposti tre o quattro numeri (gola, bocca o frequenza di taglio,
lunghezza), scegli la forma, premi un bottone e scarichi un file `.stl` pronto
per la stampante 3D. L'app pensa lei a fare le pareti chiuse e i fori dei bulloni.

**EN** — You set three or four numbers (throat, mouth or cutoff frequency,
length), pick a shape, press a button and download a printable `.stl`. The app
handles the watertight walls and the bolt holes for you.

La pagina è un'unica schermata, dall'alto in basso, nell'ordine in cui lavori:

```
1. Acoustic Profile   →   2. Mounting Flanges   →   3. Generate Assembly   →   4. Slice STL
   (che tromba)            (come si attacca)         (crea il file)            (taglia per la stampa)
```

Segui le sezioni in quest'ordine e non puoi sbagliare.

---

## 1. Acoustic Profile — che tromba vuoi / which horn

### Profile (il profilo acustico / the acoustic curve)

| Profilo | IT — quando sceglierlo | EN — when to pick it |
|---|---|---|
| **Tractrix** | Classico, carico dolce. Imposti gola + bocca. | Classic, gentle loading. Set throat + mouth. |
| **Salmon** | Ipex (T=0.707), molto usato. Imposti gola + Fc + lunghezza. | Hypex, very common. Throat + Fc + length. |
| **Le Cléac'h** | Fronte d'onda isofase, "roll-back" alla bocca. Hi-fi. | Isophase wavefront, mouth roll-back. Hi-fi. |
| **Oblate spheroidal** | Direttività costante (CD): scegli l'angolo di copertura. | Constant directivity: you pick the coverage angle. |
| **Conical** | Il CD più semplice: cono dritto, direttività data solo dall'angolo. Throat + coverage + length. | Simplest CD: straight cone, directivity set by the angle alone. Throat + coverage + length. |
| **R-OSSE** | Waveguide CD parametrico con bordo che torna indietro dolcemente nello spazio libero. Imposta gola, diametro esterno e copertura; i fattori avanzati regolano la forma. | Parametric CD waveguide with a smooth free-space roll-back. Set throat, outer diameter and coverage; advanced factors tune the shape. |
| **Exponential** | Il più semplice: gola + bocca + Fc (tasso di flare). | Simplest: throat + mouth + Fc (flare rate). |
| **Iwata** | La tromba vera del piano l'Audiophile. Solo gola + lunghezza. | The real l'Audiophile horn. Throat + length only. |

> **Iwata è speciale.** È una forma fissa rettangolare: quando la scegli, il
> selettore **Section** viene ignorato e ti restano solo gola + lunghezza. Tutto
> il resto (bocca, Fc) te lo calcola lei.
> **Iwata is special:** a fixed rectangular shape; the Section selector is
> ignored and you only set throat + length.

### Section (la forma della bocca / the mouth shape)

- **Circular** — tonda. La più semplice. / round, the simplest.
- **Polygonal** — a N lati (3–12). Scegli quanti lati. / N-gon, you pick the side count.
- **Rectangular** — rettangolare. Imposti larghezza/altezza (aspect ratio). / set width/height.
- **Elliptical** — sezione a **ellisse vera** (stessi input del rettangolare:
  W/H o copertura H/V per i profili CD). È la forma giusta per i waveguide
  asimmetrici. Le flange usano un foro ellittico dedicato e lo shape adapter
  raccorda il driver all'ellisse senza allungare la tromba. / true ellipse
  cross-section, with elliptical-hole flanges and an embedded shape adapter.
- **Radial 360°** — omnidirezionale, esce in **due pezzi** (piatto + riflettore).
  / omnidirectional, comes out as **two pieces**.

### I numeri / the numbers — "You set" vs "Computed"

**IT** — A sinistra (**You set**) metti i pochi numeri che guidano la tromba che
hai scelto. A destra (**Computed**) l'app ti **mostra** quello che ne deriva
(lunghezza, Fc, area di gola/bocca) — quelli non si toccano, sono risultati. La
frasetta sotto "Dimensions" ti dice ogni volta *quali* campi servono.

**EN** — On the left (**You set**) you enter the few numbers that drive your
chosen horn. On the right (**Computed**) the app **shows** what follows (length,
Fc, throat/mouth area) — those aren't editable, they're results. The hint under
"Dimensions" tells you each time *which* fields are needed.

> ⚠️ **Avviso bocca piccola / small-mouth warning.** Se compare un avviso giallo,
> la bocca è troppo piccola per "caricare" fino alla Fc dichiarata: la frequenza
> di taglio reale sarà più alta. Allarga la bocca o alza la Fc.
> If a yellow warning appears, the mouth is too small to load down to the stated
> Fc — the real cutoff will be higher. Enlarge the mouth or raise Fc.

### ⚙️ Advanced settings (di solito lasciali stare / usually leave them)

- **Wall thickness** — spessore parete (default 4 mm). / wall thickness.
- **Profile points** — risoluzione/qualità della mesh (più alto = più liscio e
  pesante). / mesh resolution (higher = smoother and heavier).
- **Speed of sound** — velocità del suono (344 m/s a ~20 °C; alzala col caldo).
  Cambia i calcoli di Fc/bocca. / speed of sound; affects Fc/mouth math.

### 2D Preview

A destra vedi la **sezione** della tromba in tempo reale: linea interna + parete.
È solo un'anteprima, non un file. Serve a capire se la forma è quella che volevi
prima di generare. / Live cross-section preview; not a file, just a sanity check.

---

## 2. Mounting Flanges — come si attacca / how it mounts

**IT** — Le flange sono gli anelli con i fori per i bulloni. Tre possibili:
- **Throat / Adapter** — lato driver (l'altoparlante).
- **Mouth** — lato bocca (il baffle / pannello).
- **Mid** — una flangia intermedia, utile per trombe lunghe da stampare a pezzi.

Ogni flangia ha una casella **Include**: spegnila se non la vuoi.

**EN** — Flanges are the bolt-hole rings. Three of them: **Throat/Adapter**
(driver side), **Mouth** (baffle side), **Mid** (an intermediate ring, handy for
long horns printed in parts). Each has an **Include** checkbox.

### I campi che contano / the fields that matter

In prima fila trovi solo l'essenziale:

| Campo | IT | EN |
|---|---|---|
| **Bolt count** | quanti bulloni | number of bolts |
| **Bolt hole Ø** | diametro del foro bullone | bolt hole diameter |
| **Ring width** | larghezza dell'anello attorno al foro: **è questo che decide la dimensione della flangia**. Allargalo per far stare i bulloni più in fuori. | width of the ring around the hole — **this sets the flange size**. Widen it to push bolts further out. |
| **Bolt circle Ø** | su che cerchio stanno i bulloni | the circle the bolts sit on |

Sotto **Advanced** (apri solo se serve): `Z offset`, posizione bulloni
(spigoli/facce), forma esterna (tonda/poligonale) e numero lati esterni.

> **Mouth flange inward.** Quando la flangia di bocca rientra sotto il
> roll-back, l'app costruisce piloni pieni fino alla battuta delle viti e li
> rifila sulla superficie curva reale: dal flare non sporge nulla. Il foro
> visibile resta tondo e largo quanto il gambo vite. Abilitando
> **Screw-head seat**, `Head Ø` imposta il diametro della testa e `Head depth`
> la quota del fondo; tutte le sedi sono assiali ai fori e terminano sullo
> stesso piano. / For an inward mouth flange, full pillars reach the screw
> bearing face and are clipped to the real flare surface, with nothing
> protruding outside. The visible opening stays round at shaft diameter.
> Optional screw-head seats are axial, concentric, and share one flat floor.

> **Throat — adattatore driver.** Se spunti **Include shape adapter** puoi
> collegare un driver **a vite 1⅜"-18 con foro acustico da 25 mm** oppure
> **flangiato custom** o bolt-on standard **1" 2-fori**, **1" 3-fori**,
> **1.4" 4-fori** e **2" 4-fori**, e
> l'app costruisce la transizione dalla gola tonda alla forma della tromba.
> **Morph length inside horn** sostituisce i primi millimetri del flare: non
> allunga la tromba. Solo flangia o socket possono sporgere dietro la gola.
> **Throat — driver adapter.** Tick **Include shape adapter** to connect a
> **1⅜"-18 threaded driver with a 25 mm acoustic bore**, a custom flange, or
> a standard **1" / 1.4" / 2" bolt-on** driver; the app builds the
> round-to-shape transition. **Morph length inside horn** replaces the first
> part of the flare, so it does not increase horn depth. Only the flange or
> threaded socket may protrude behind the throat plane.

**Note / notes:**
- Per **Radial** e **Iwata** alcune flange non sono disponibili (la bocca è
  curva o il profilo è speciale): l'app te lo dice. / some flanges are disabled
  for Radial/Iwata; the app tells you.
- Il bottone **🔧 Recalculate flanges** riallinea le misure delle flange dopo
  che hai cambiato la tromba. / re-aligns flange sizes after you change the horn.

---

## 3. Generate Assembly — crea il file / build the file

**IT** —
1. Lascia **Include horn** spuntato (la tromba vera e propria).
2. Premi **Generate Assembly STL**.
3. Aspetta lo spinner: l'app fonde tromba + flange + adattatore in **un solo
   pezzo a tenuta stagna**.
4. Scarica con **📥 Download STL** (o **STEP** per il CAD).

**EN** —
1. Keep **Include horn** ticked.
2. Press **Generate Assembly STL**.
3. Wait for the spinner: horn + flanges + adapter are merged into **one
   watertight piece**.
4. Download with **📥 Download STL** (or **STEP** for CAD).

Se compare un errore rosso, cambia leggermente i parametri (spesso una flangia
troppo grande o una bocca troppo piccola) e rigenera. / On a red error, nudge the
parameters (often an oversized flange or a tiny mouth) and regenerate.

---

## 4. Slice STL — taglia per la stampa / cut it for printing

Serve quando la tromba **non ci sta** nel piatto della stampante. / For when the
horn doesn't fit the print bed.

**Source:** usa l'**assembly appena generato** oppure **carica un tuo .stl**.

Due modi di taglio / two slicing modes:

### A) Axial / petals — anelli e spicchi
- **❶ Slice axially** — taglia la tromba in **fette** lungo l'asse. Scegli per
  *numero* di segmenti o *ogni quanti mm*. / cut into stacked rings; by count or by mm.
- **❷ Apply petals** — divide ogni fetta in **spicchi** (petali) verticali, per
  trombe larghe. / split each ring into vertical petals.
- **Axial joint lip** e **Radial joint (tongue & groove)** aggiungono incastri
  maschio/femmina così i pezzi si allineano e si incollano bene. In vista lasci
  solo la **profondità**; il resto è sotto *Advanced*. / joints add male/female
  interlocks; only depth is up front, the rest under *Advanced*.

### B) Print volume boxes — scatole a misura di stampante
- Imposti **Max X / Y / Z** = il tuo volume di stampa.
- Scegli il **Packing** (consigliato: *Center-up core first*).
- **Box joints** opzionali per gli incastri.
- Premi **Slice to print volume**.

### Scaricare i pezzi / download the pieces
- **📦 Download all as ZIP** — tutti i pezzi in un colpo. / all pieces at once.
- Oppure ogni pezzo singolarmente, con la sua altezza Z indicata. / or each piece
  individually, with its Z range.

> Il bottone **Reset slicer cache** svuota i pezzi calcolati se qualcosa sembra
> "rimasto indietro" dopo che hai cambiato i parametri. / clears cached pieces if
> something looks stale after you changed parameters.

---

## Ricetta veloce / quick recipe

**IT** — Una tromba Salmon tonda, pronta in un minuto:
1. Profile = **Salmon**, Section = **Circular**.
2. Throat Ø = 25, Fc = 600, Axial length = 90.
3. Lascia le flange di default, premi **Generate Assembly STL**.
4. **📥 Download STL** → in slicer di stampa → stampa.

**EN** — A round Salmon horn in a minute:
1. Profile = **Salmon**, Section = **Circular**.
2. Throat Ø = 25, Fc = 600, Axial length = 90.
3. Keep default flanges, press **Generate Assembly STL**.
4. **📥 Download STL** → into your print slicer → print.

---

## Problemi comuni / common issues

| Sintomo / Symptom | IT | EN |
|---|---|---|
| Avviso giallo sulla bocca | Bocca troppo piccola per la Fc: allargala o alza Fc. | Mouth too small for the Fc: enlarge it or raise Fc. |
| Errore rosso alla generazione | Parametro estremo (flangia enorme, bocca minuscola): aggiusta e rigenera. | Extreme parameter: adjust and regenerate. |
| La tromba non entra in stampante | Usa **Slice STL** (petali o print-volume boxes). | Use **Slice STL** (petals or print-volume boxes). |
| Le misure delle flange sembrano vecchie | Premi **🔧 Recalculate flanges**. | Press **🔧 Recalculate flanges**. |
| I pezzi tagliati sembrano vecchi | Premi **Reset slicer cache**. | Press **Reset slicer cache**. |
| "Mesh non chiusa" nello slicer di stampa | Spesso ok per stampa; se buca, rigenera con parametri leggermente diversi. | Often fine; if it leaks, regenerate with slightly different params. |

---

Buona stampa. / Happy printing.
