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

## 4. Pipeline a Due Stadi con Selezione Top-K e Adaptive Sampling

La valutazione di un catalogo di $M$ driver con $K_{\text{opt}}$ iterazioni di ottimizzazione comporta un costo computazionale pari a:

$$C = \mathcal{O}(M \cdot K_{\text{opt}} \cdot N_{\text{grid}})$$

Per minimizzare il costo globale garantendo al contempo che i candidati ottimali non vengano scartati prematuramente, Load Forge impiega una strategia a due stadi *coarse-to-fine* con conservazione dei migliori $K$ candidati (*Top-K*).

```text
[ Catalogo Driver (M candidati) ]
               │
               ▼
┌────────────────────────────────────────────────────────┐
│ STADIO 1: Coarse Global Screening (N_base ≈ 30 pt)     │
│ - Griglia logaritmica full-band (10 - 300 Hz)          │
│ - Ottimizzazione rapida / pattern search               │
│ - Ranking preliminare di tutti i driver                │
└────────────────────────────────────────────────────────┘
               │
   [ Top-K Candidati per Topologia (default K = 5) ]
               │
               ▼
┌────────────────────────────────────────────────────────┐
│ STADIO 2: Accurate Refinement (N_refine + N_adaptive)  │
│ - Griglia locale attorno al knee [0.7 F3, 1.4 F3]      │
│   e/o ricalcolo full-band denso                        │
│ - Campionamento adattivo guidato dalla curvatura       │
│ - Estrazione metrica definitiva e ranking finale       │
└────────────────────────────────────────────────────────┘
```

### 4.1 Principio di Top-K Recall:
Lo Stadio 1 non ha il compito di decretare con certezza assoluta il vincitore finale (Top-1), bensì di garantire che il vero ottimo globale non venga escluso prima della fase ad alta precisione.
La metrica fondamentale di qualità dello Stadio 1 è la **Top-K Recall**:

$$R_K = P\left(x_{\text{reference}} \in \mathrm{TopK}_{\text{coarse}}\right)$$

dove $x_{\text{reference}}$ è l'ottimo identificato dalla simulazione ad alta risoluzione. L'obiettivo dello screening è massimizzare $R_K$ (valutando ad esempio $R_1, R_3, R_5$) al minor costo computazionale.

### 4.2 Stadio 2: Refinement Flessibile e Adaptive Sampling:
Nel secondo stadio, i pochi candidati finalisti ($K \ll M$) vengono raffinati impiegando:
1. **Refinement locale** mirato attorno alle frequenze di transizione ($F_3, F_6, F_{10}$) o valutazione full-band più densa.
2. **Adaptive sampling locale** basato sulla stima della derivata seconda discreta del livello SPL in dB:
   $$C_i = |y_{i+1} - 2y_i + y_{i-1}|$$
   - $C_i$ contenuto $\implies$ andamento quasi-lineare $\implies$ nessun campione aggiuntivo necessario;
   - $C_i$ elevato $\implies$ regione di forte curvatura o risonanza $\implies$ inserimento di campioni supplementari.

### 4.3 Architettura del Budget di Calcolo:
Il numero totale di valutazioni in frequenza per un driver è descritto dal modello:

$$\boxed{N_{\text{eval}} = N_{\text{base}} + N_{\text{adaptive}} + \mathbb{I}_{\text{Top-K}} \cdot N_{\text{refine}}}$$

dove $N_{\text{base}} \approx 30$, $N_{\text{adaptive}}$ dipende dalla complessità spettrale locale, e $N_{\text{refine}}$ è allocato esclusivamente ai candidati selezionati per la fase finale.

---

## 5. Euristiche di Ottimizzazione e Architettura Runtime

1. **Volume Warm-Start Heuristic:** Per ricerche orientate alla massima estensione con limite volumetrico, il volume iniziale è impostato a $V_{\text{init}} \approx 0.95 \cdot V_{\max}$. Questa euristica accelera la convergenza evitando iterazioni infruttuose di scalata volumetrica, ma non implica $V_{\text{opt}} \approx V_{\max}$: l'ottimo effettivo può risultare inferiore in presenza di penalizzazioni su ripple, escursione, ritardo di gruppo o velocità nei condotti.
2. **Multiprocessing Bounded:** Esecuzione parallela con pool di processi persistente e payload T/S compatti, progettata per minimizzare l'overhead di scheduling e serializzazione della memoria.

---

## 6. Validazione Numerica e Frontiera di Pareto

I parametri operativi ($N_{\text{base}}$, $\kappa$, $K$, densità di refinement) devono essere determinati e validati mediante benchmark offline contro una simulazione di riferimento ad alta densità ($N_{\text{reference}} \gg N_{\text{coarse}}$, es. $1000\text{--}2000$ punti o root-finding esatto).

### Metriche di Accuratezza:
Per ciascun candidato del benchmark vengono misurate le discrepanze assolute rispetto al riferimento:
- $|\Delta F_3|$, $|\Delta F_6|$, $|\Delta F_{10}|$ (Hz)
- $|\Delta \text{SPL}_{\text{peak}}|$ (dB)
- $|\Delta X_{\max}|$ (mm)
- $|\Delta \text{ripple}|$ (dB)

Per ogni metrica si analizza la distribuzione statistica: **Mediana**, **P95**, **P99** e **Worst Case**.

### Frontiera di Pareto:
La configurazione ottimale del Finder è individuata sulla frontiera di Pareto che massimizza il compromesso tra:

$$\text{Tempo di Esecuzione (Runtime)} \quad \longleftrightarrow \quad \text{Accuratezza Numerica} \quad \longleftrightarrow \quad \text{Top-K Recall } (R_K)$$

---

## 7. Quadro Epistemologico

| Categoria | Definizione | Esempi nel Documento |
|---|---|---|
| **Fatto Matematico** | Relazioni analitiche rigorose ed esatte | Definizione di $Q = \frac{\omega_0}{2\alpha}$; formula di interpolazione logaritmica; complessità $\mathcal{O}(M \cdot K_{\text{opt}} \cdot N_{\text{grid}})$. |
| **Motivazione Fisica** | Proprietà qualitative del dominio elettroacustico | Risonanze ad alto $Q$ richiedono campionamenti più fitti; pendenze asintotiche a $n \times 6\text{ dB/oct}$. |
| **Euristica Ingegneristica** | Scelte progettuali volte a ottimizzare il calcolo | Baseline $N_{\text{base}} = 30$; parametro $\kappa \approx 0.5$; volume warm-start $V_{\text{init}} \approx 0.95 V_{\max}$; $K = 5$. |
| **Risultato Empirico** | Prestazioni verificate sperimentalmente su benchmark | Valori di $R_K$; distribuzioni di errore P95/P99 su $F_3$; tempi di esecuzione effettivi. |

**Sintesi:** Load Forge adotta una metodologia *coarse-to-fine* fisicamente motivata che concentra il budget computazionale dove risiede l'informazione acustica critica, preservando la diversità dei candidati promettenti e demandando la conferma della precisione alla validazione numerica empirica.
