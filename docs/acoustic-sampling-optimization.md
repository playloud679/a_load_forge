# Criterio di Campionamento Acustico Spettrale e Ottimizzazione Adaptive del Finder

Questo documento descrive i principi fisici, matematici ed ingegneristici utilizzati nel motore di simulazione e nel sistema di ricerca altoparlanti (*Bass Match / Finder*) di **Load Forge**.

L'obiettivo è identificare una configurazione efficiente lungo la frontiera di Pareto tra **velocità di esecuzione** e **accuratezza numerica**, definendo un criterio di campionamento logaritmico fisicamente motivato dal massimo fattore di qualità dei risonatori e successivamente validabile numericamente. La precisione sub-hertziana nelle frequenze caratteristiche e sub-dB nella risposta in frequenza costituisce un target prestazionale da verificare empiricamente mediante benchmark dedicati.

---

## 1. Fondamenti: Rappresentazione Analitica e Sistemi Acustici

Molte delle topologie utilizzate nel Finder di Load Forge (cassa chiusa, bass reflex, DCCAV, bandpass del 4° e 6° ordine, passive radiator, nonché modelli 1-D per linee di trasmissione e trombe) possono essere rappresentate, esattamente o mediante modelli equivalenti/approssimati nel dominio di Laplace $s = \sigma + j\omega$, attraverso funzioni di trasferimento razionali $H(s) = \frac{N(s)}{D(s)}$ o matrici di trasferimento acustiche lineari:

- **Poli complessi coniugati:** $s = -\alpha \pm j\omega_d$, con frequenza di risonanza $\omega_0 = \sqrt{\alpha^2 + \omega_d^2}$ e fattore di merito $Q = \frac{\omega_0}{2\alpha}$. La posizione dei poli governa lo smorzamento e l'ampiezza delle risonanze.
- **Pendenze asintotiche:** Su scala logaritmica $[\ln f, \text{SPL}_{\text{dB}}]$, la risposta decade o cresce secondo pendenze asintotiche pari a $n \times 6\text{ dB/ottava}$ ($n \times 20\text{ dB/decade}$), dove $n$ è l'ordine del filtro (es. $n=2$ per sospensione pneumatica, $n=4$ per bass reflex, $n=6$ per DCCAV).
- **Group delay e fase:** Il ritardo di gruppo $\tau_g = -\frac{d\phi}{d\omega}$ presenta picchi in corrispondenza delle risonanze ad alto $Q$, costituendo una metrica sensibile alla risoluzione locale in frequenza.

---

## 2. Criterio di Campionamento Logaritmico Vincolato da Q

L'analogia con il teorema di Shannon-Nyquist temporale fornisce un'intuizione fisica guida: risonanze con fattore di merito $Q$ più elevato presentano larghezze di banda frazionarie più strette ($\Delta \omega / \omega_0 \approx 1/Q$) e variazioni di fase più rapide, richiedendo quindi una maggiore densità di campionamento in frequenza logaritmica. Questa analogia non costituisce una dimostrazione matematica universale, ma motiva un criterio di discretizzazione parametrico.

### Formulazione Parametrica:
Definito $Q_{\max}$ come il massimo fattore di qualità rilevante tra i risonatori del sistema, il passo di campionamento logaritmico $\Delta(\ln f)$ è vincolato dalla relazione:

$$\boxed{\Delta(\ln f) \le \frac{\kappa}{Q_{\max}}}$$

dove $\kappa$ è un coefficiente di calibrazione e sicurezza. Il valore $\kappa \approx 0.5$ può essere adottato come punto di partenza euristico e deve essere validato numericamente sulle topologie supportate.

### Requisiti di Densità per Ottava e per Decade:
Dalla disuguaglianza parametrica si ricavano:

- **Punti minimi per ottava:**
  $$N_{\text{oct}} = \frac{\ln 2}{\Delta(\ln f)} \ge \frac{\ln 2}{\kappa} Q_{\max}$$
  Con la scelta euristica $\kappa = 0.5$:
  $$N_{\text{oct}} \ge 2\ln(2) \cdot Q_{\max} \approx 1.386 \, Q_{\max}$$

- **Punti minimi per decade:**
  $$N_{\text{dec}} = \frac{\ln 10}{\Delta(\ln f)} \ge \frac{\ln 10}{\kappa} Q_{\max}$$
  Con la scelta euristica $\kappa = 0.5$:
  $$N_{\text{dec}} \ge 2\ln(10) \cdot Q_{\max} \approx 4.605 \, Q_{\max}$$

### Baseline Ingegneristica (Coarse Scan):
Nei carichi reflex, DCCAV e bandpass con tipiche perdite di cassa ($Q_b \approx 5 \dots 10$), i poli dominanti presentano $Q_{\max} \le 5$.
Per la scansione globale iniziale nel range $10\text{ Hz} \dots 300\text{ Hz}$ (circa 1.48 decadi), una griglia di riferimento:

$$N_{\text{coarse}} = 30 \text{ punti logaritmici}$$

costituisce una solida **baseline ingegneristica** per lo screening rapido. La sufficienza di tale risoluzione deve tuttavia essere verificata mediante benchmark rispetto a simulazioni ad alta densità.

---

## 3. Interpolazione Logaritmica delle Frequenze di Crossing

La determinazione delle frequenze di taglio caratteristiche ($F_3, F_6, F_{10}$) lungo i rami di roll-off non richiede una griglia uniformemente densa su tutta la banda:

### Formula di Stima Log-Lineare:
Dati due nodi adiacenti $(f_0, \text{SPL}_0)$ e $(f_1, \text{SPL}_1)$ che racchiudono il livello target $\text{SPL}_{\text{target}}$, la frequenza di crossing stimata $f_{\text{crossing}}$ è ottenuta mediante interpolazione lineare nello spazio $(\ln f, \text{SPL}_{\text{dB}})$:

$$f_{\text{crossing}} = \exp\left( \ln f_0 + \frac{\text{SPL}_{\text{target}} - \text{SPL}_0}{\text{SPL}_1 - \text{SPL}_0} \cdot \ln\left(\frac{f_1}{f_0}\right) \right)$$

Questa formulazione interpola linearmente l'attenuazione in dB rispetto al logaritmo della frequenza. Poiché i filtri acustici mostrano pendenze asintotiche quasi rettilinee nel piano $[\ln f, \text{dB}]$, questa tecnica fornisce stime generalmente superiori rispetto all'interpolazione lineare in Hz.

### Accuratezza e Curvatura Locale:
L'errore effettivo di interpolazione dipende dalla curvatura locale della risposta (prossimità del "ginocchio" di risonanza) e dalla distanza spettrale fra i campioni. Eventuali precisioni sub-hertziane (es. $< 0.05\text{ Hz}$) rappresentano risultati empirici da verificare contro simulazioni dense di riferimento e non proprietà analitiche universali.

---

## 4. Pipeline Corrente per Ogni Combinazione Driver × Carico

La valutazione di un catalogo di $M$ driver con $K_{\text{opt}}$ iterazioni di ottimizzazione comporta un costo computazionale pari a:

$$C = \mathcal{O}(M \cdot K_{\text{opt}} \cdot N_{\text{grid}})$$

La pipeline corrente riduce il costo con una strategia *coarse-to-fine* interna
a ciascun job. Non esegue uno screening Top-K globale dei driver: ogni
combinazione dichiarata **Ready simulation** riceve la propria ottimizzazione
e il proprio refinement.

```text
[ Un job: un driver × un carico ]
               |
               v
┌────────────────────────────────────────────────────────┐
│ STADIO 1: ricerca del box                               │
│ - fino a 30 box (24 su Cloud Run)                      │
│ - 30 frequenze per box; 38 con ripple ceiling attivo   │
│ - compass search deterministico in spazio logaritmico  │
└────────────────────────────────────────────────────────┘
               |
               v
┌────────────────────────────────────────────────────────┐
│ STADIO 2: refinement del box vincente                  │
│ - ricalcolo sui 30 punti larghi                        │
│ - 20 punti locali aggiuntivi attorno alla F3           │
│ - risposta finale a 240 punti (80 su Cloud Run)        │
└────────────────────────────────────────────────────────┘
               |
               v
[ filtri finali e ranking F3, F6, F10, Peak SPL ]
```

### 4.1 Budget di calcolo

Per un job ottimizzato senza Ripple frequency ceiling, indicando con
$B\leq30$ il numero effettivo di box provati e con $N_{\text{finale}}$ la
risoluzione scelta, il budget ordinario è:

$$\boxed{N_{\text{eval}}=30B+(30+20)+N_{\text{finale}}}$$

Con $B=30$ e $N_{\text{finale}}=240$ il massimo ordinario è 1.190 punti per
job. Il DCCAV può aggiungere fino a tre ricontrolli del vincitore quando la F3
raffinata richiede una correzione dell'accordo. Infinite baffle e passive
radiator non usano il Compass Search e pagano soltanto la risposta finale.
Con il ceiling attivo, la griglia aggiunge una coda sparsa di 9 punti sopra il
limite condividendo il punto di separazione: 30 punti diventano normalmente 38
e 240 diventano 248.

### 4.2 Perché non c'è una Top-K globale

Una Top-K preliminare farebbe risparmiare tempo, ma potrebbe eliminare un
driver il cui box cambia posizione dopo il refinement. La scelta corrente è
più costosa ma più leggibile: tutti i job ammessi ricevono lo stesso budget e
il ranking confronta metriche finali. La **Top-K recall** resta una metrica
utile per un eventuale benchmark futuro, non una funzione attiva del Finder.

---

## 5. Euristiche di Ottimizzazione e Architettura Runtime

1. **Volume Warm-Start Heuristic:** Per ricerche orientate alla massima estensione con limite volumetrico, il volume iniziale è impostato a $V_{\text{init}} \approx 0.95 \cdot V_{\max}$. Questa euristica accelera la convergenza evitando iterazioni infruttuose di scalata volumetrica, ma non implica $V_{\text{opt}} \approx V_{\max}$: l'ottimo effettivo può risultare inferiore in presenza di penalizzazioni su ripple, escursione, ritardo di gruppo o velocità nei condotti.
2. **Multiprocessing Bounded:** Esecuzione parallela con pool di processi persistente e payload T/S compatti, progettata per minimizzare l'overhead di scheduling e serializzazione della memoria.

---

## 6. Validazione Numerica e Frontiera di Pareto

I parametri operativi (budget di box, densità coarse e densità di refinement) devono essere determinati e validati mediante benchmark offline contro una simulazione di riferimento ad alta densità ($N_{\text{reference}} \gg N_{\text{coarse}}$, es. $1000\text{--}2000$ punti o root-finding esatto).

### Metriche di Accuratezza:
Per ciascun candidato del benchmark vengono misurate le discrepanze assolute rispetto al riferimento:
- $|\Delta F_3|$, $|\Delta F_6|$, $|\Delta F_{10}|$ (Hz)
- $|\Delta \text{SPL}_{\text{peak}}|$ (dB)
- $|\Delta X_{\max}|$ (mm)
- $|\Delta \text{ripple}|$ (dB)

Per ogni metrica si analizza la distribuzione statistica: **Mediana**, **P95**, **P99** e **Worst Case**.

### Frontiera di Pareto:
La configurazione ottimale del Finder è individuata sulla frontiera di Pareto che massimizza il compromesso tra:

$$\text{Tempo di Esecuzione (Runtime)} \quad \longleftrightarrow \quad \text{Accuratezza Numerica} \quad \longleftrightarrow \quad \text{stabilità del ranking}$$

---

## 7. Quadro Epistemologico

| Categoria | Definizione | Esempi nel Documento |
|---|---|---|
| **Fatto Matematico** | Relazioni analitiche rigorose ed esatte | Definizione di $Q = \frac{\omega_0}{2\alpha}$; formula di interpolazione logaritmica; complessità $\mathcal{O}(M \cdot K_{\text{opt}} \cdot N_{\text{grid}})$. |
| **Motivazione Fisica** | Proprietà qualitative del dominio elettroacustico | Risonanze ad alto $Q$ richiedono campionamenti più fitti; pendenze asintotiche a $n \times 6\text{ dB/oct}$. |
| **Euristica Ingegneristica** | Scelte progettuali volte a ottimizzare il calcolo | 30 frequenze coarse; 20 punti locali; volume warm-start $V_{\text{init}} \approx 0.95 V_{\max}$. |
| **Risultato Empirico** | Prestazioni verificate sperimentalmente su benchmark | Stabilità del ranking; distribuzioni di errore P95/P99 su $F_3$; tempi di esecuzione effettivi. |

**Sintesi:** Load Forge adotta una metodologia *coarse-to-fine* per ogni combinazione Ready, concentra il refinement sul box vincente di ciascun driver e demanda la conferma della precisione alla validazione numerica empirica.
