# Manuale Operativo: Parametri e Innovazioni Esclusive di Load Forge

Questo manuale è una guida operativa avanzata pensata per il progettista acustico. Spiega in modo dettagliato tutti i parametri operativi di **Load Forge**, con un focus speciale sulle **innovazioni e sui parametri esclusivi** sviluppati in questo motore rispetto ai simulatori standard tradizionali (WinISD, BassBox Pro, VituixCAD, Hornresp, LEAP).

---

## 1. Perché Load Forge è Diverso dai Simulatori Tradizionali

I simulatori classici si limitano a calcolare curve lineari in piccolo segnale (Small Signal) su carichi convenzionali (reflex o cassa chiusa), assumendo driver ideali in aria libera e trascurando i vincoli fisici reali della cassa, della produzione e del segnale reale.

Load Forge introduce una suite di parametri, algoritmi e metriche proprietarie progettate per:
1. **Risolvere topologie complesse a doppio risuonatore serie (DCCAV)** non supportate dai simulatori standard.
2. **Prevedere i limiti fisici combinati di potenza ed escursione (MOL/MIL)** istante per istante.
3. **Isolare il comportamento acustico del subwoofer dalle risalite di gamma media** (*Ripple Ceiling Cutout* e *Saddle Coherence*).
4. **Valutare la qualità ingegneristica complessiva dell'allineamento** (*Forge Score*).
5. **Simulare la realtà costruttiva** (*Panel Air Loading*, *Barriere di fattibilità geometrica del condotto*, *Monte Carlo Tolerance Band*).

---

## 2. Parametri e Concetti Esclusivi di Load Forge

Di seguito l'analisi approfondita dei parametri esclusivi introdotti in Load Forge, con significato fisico, formule e impatto sul progetto.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         INNOVAZIONI ESCLUSIVE LOAD FORGE                         │
├──────────────────────────┬──────────────────────────┬────────────────────────────┤
│ 1. Topologia & Fisica    │ 2. Ottimizzazione & Bounding│ 3. Limiti Dinamici & Qualità│
├──────────────────────────┼──────────────────────────┼────────────────────────────┤
│ • DCCAV (Vh, fh, Vl, fl) │ • Ripple Max Freq Cutout │ • Forge Score (0-100)      │
│ • Panel Air Loading & α  │ • Segmented Grid 2-Tier  │ • MOL / MIL @ F3 e Banda   │
│ • Saddle Coherence       │ • Q-Constrained Sampling │ • Duct Volume Directives   │
│ • Bandwidth Classifier   │ • Compass Coordinate Opt │ • Monte Carlo Band         │
└──────────────────────────┴──────────────────────────┴────────────────────────────┘
```

---

### A. Parametri della Topologia DCCAV (Double Cavity Asymmetric Vent)

A differenza del bass reflex standard (1 volume $V_b$, 1 condotto $F_b$), il **DCCAV** adotta due camere risonanti asimmetriche in serie:

$$\text{Driver} \longrightarrow V_h \parallel \text{Port } h \longrightarrow V_l \parallel \text{Port } l$$

| Parametro | Unità | Significato Operativo | Valore Tipico / Regola di Progetto |
|---|---|---|---|
| **$V_h$** (*Upper Chamber*) | Litri | Volume della camera primaria (posteriore al cono). Determina la prima cavità acustica. | Tipicamente dal **45% al 65%** del volume totale ($V_{\text{tot}} = V_h + V_l$). |
| **$f_h$** (*Upper Port*) | Hz | Accordo del condotto interno di comunicazione tra camera superiore e inferiore. | Accordo superiore: tipicamente **1.4 × – 1.8 ×** rispetto a $f_l$ (es. 55–80 Hz). |
| **$V_l$** (*Lower Chamber*) | Litri | Volume della camera secondaria (di sfogo). | Tipicamente dal **35% al 55%** del volume totale. |
| **$f_l$** (*Lower Port*) | Hz | Accordo del condotto esterno di uscita verso l'ambiente. | Accordo inferiore: estende la risposta in frequenza verso il limite sub-basso (es. 25–45 Hz). |

#### Perché è superiore al reflex standard:
- **Doppio Notch di Escursione**: Nel grafico *Excursion*, l'altoparlante presenta **due valli di escursione minima** (a $f_l$ e a $f_h$) anziché una sola, dimezzando la distorsione armonica e la modulazione di intermodulazione (IMD) su un'ottava intera.
- **Roll-off Controllato**: Il passaggio tra banda passante e roll-off è più progressivo rispetto al 4° ordine puro (24 dB/oct) del bass reflex.

---

### B. Driver Panel Air Loading (Massa Aggiunta della Flangia di Montaggio)

Nei simulatori standard, il driver viene simulato con la sua massa mobile nominale $M_{ms}$ in aria libera. Nella realtà, quando l'altoparlante è montato su un pannello spesso (baffle in MDF/multistrato da 18–30 mm) con flangia incassata o cono posteriore flangiato, l'aria intrappolata nel condotto di montaggio si muove solidale al cono, aggiungendo massa.

| Parametro | Tipo / Unità | Significato Operativo |
|---|---|---|
| **`Panel air loading`** | Toggle (On/Off) | Abilita la correzione fisica per la massa virtuale d'aria del pannello. |
| **`Panel coupling (α)`** | Fattore (0.0 – 1.0) | Grado di accoppiamento geometrico del pannello (default 0.90 per montaggi standard). |

#### Formula applicata:
$$\Delta M_{\text{air}} = \frac{8}{3\pi} \cdot \rho_0 \cdot r_{\text{piston}}^3 \cdot \alpha_{\text{coupling}}$$
$$F_{s, \text{mounted}} = F_s \cdot \sqrt{\frac{M_{ms}}{M_{ms} + \Delta M_{\text{air}}}}$$

**Effetto pratico**: Abbassa la reale $F_s$ montata di 1–3 Hz e incrementa leggermente il $Q_{ts}$ reale, evitando di progettare un accordo reflex disallineato rispetto alla risposta effettiva in cassa.

---

### C. Ripple Max Frequency Cutout (`ripple_max_freq_hz` / `f_max_hz`)

**Problema dei simulatori standard**: Quando si ottimizza o si valuta un woofer/subwoofer (es. 12" o 15" ad alta sensibilità), la risposta del cono sale naturalmente a 200–400 Hz (sensibilità di gamma media). I software convenzionali considerano questa risalita come "ripple" o come livello di riferimento, penalizzando l'allineamento o calcolando un $F_3$ errato a 80 Hz su un subwoofer che in realtà scende lineare a 25 Hz.

| Parametro | Unità | Funzione Operativa |
|---|---|---|
| **`Max ripple frequency (Cutout)`** | Hz | Imposta il tetto di frequenza oltre il quale il motore **ignora completamente** le variazioni di risposta, calcolando ripple, sensibilità di riferimento $SPL_{\text{ref}}$ e marker $F_3/F_6/F_{10}$ **esclusivamente nella banda sub-bassa utile**. |

- **Subwoofer dedicato (taglio xover 70–80 Hz)**: Impostare `Cutout = 70–80 Hz`. L'ottimizzatore renderà piatta e profonda la risposta da 20 a 70 Hz, disinteressandosi di cosa avviene a 300 Hz.
- **Mid-Woofer 2 vie (taglio xover 1.5–2 kHz)**: Lasciare Cutout a 0 (disabilitato) per ottimizzare l'intera banda fino a 300–500 Hz.

---

### D. Algoritmo di Coerenza di Soglia su Selle e Ripiani (Saddle & Shelf Coherence)

Nei sistemi accordati molto in basso (*Extended Bass Shelf - EBS*) o con woofer ad alta risalita in gamma media:
- Il livello a 200 Hz può essere 86 dB, mentre il ripiano reflex a 28 Hz è a 81.5 dB.
- A 50 Hz c'è un leggero avvallamento (sella) a 81 dB.
- **Errore standard**: I simulatori convenzionali vedono che $86 - 3 = 83\text{ dB}$ viene incrociato a **73 Hz** (durante la discesa verso la sella) e battezzano $F_3 = 73\text{ Hz}$, mentre $F_6$ viene trovato a **24 Hz**.
- **Soluzione Load Forge**: Il motore rileva la presenza della sella e ri-ancora coerentemente il riferimento al ripiano acustico reale della cassa, garantendo la **stretta monotonicità fisica**:
  $$F_{10} \le F_6 \le F_3 \quad \text{(sempre sul ginocchio di roll-off effettivo)}$$

---

### E. Griglia di Frequenza Segmentata a Due Stadi (`segmented_frequency_grid`)

Nei calcoli di ranking batch (*Bass Match*) o nell'ottimizzazione iterativa:
- La griglia standard a 240–300 punti logaritmici su tutta la banda spreca la maggior parte del tempo di calcolo tra 100 e 500 Hz.
- **Load Forge Segmented Grid**: Alloca una densità spettrale elevatissima (es. 200 punti) al di sotto del Cutout di frequenza (la zona critica per accordo, escursione e velocità aria) e solo **9 punti ancora** nella zona superiore.
- **Risultato**: Velocità di calcolo **5× – 10× superiore**, permettendo a Bass Match di simulare e classificare 40 combinazioni di altoparlanti e carichi in meno di 1 secondo.

---

### F. Forge Score (Indice di Qualità dell'Allineamento 0–100)

Il **Forge Score** è una metrica di merito proprietaria che assegna un punteggio ingegneristico complessivo al progetto, pesando simultaneamente:

1. **Estensione alle basse frequenze ($F_3$)**: Premia accordi profondi rispetto alla $F_s$ del driver.
2. **Linearità in banda passante (Ripple penalty)**: Penalizza picchi sporgenti ($> 1.5 - 2\text{ dB}$) o avvallamenti eccessivi.
3. **Compattezza del volume ($V_{\text{box}} / V_{as}$)**: Premia l'economia di spazio a parità di estensione.
4. **Fattibilità aerodinamica del condotto**: Penalizza condotti con velocità dell'aria $> 17\text{ m/s}$ o tubi troppo lunghi per entrare nel box.
5. **Stabilità temporale (Group Delay)**: Penalizza ritardi di gruppo eccessivi ($> 25 - 30\text{ ms}$) in banda udibile.

Un punteggio $\ge 85/100$ certifica un allineamento bilanciato, pronto per la costruzione reale senza controindicazioni fisiche.

---

### G. Metriche Dinamiche di Potenza ed Escursione (MOL e MIL)

Mentre i software standard mostrano solo la curva SPL a 1 Watt (o 2.83V), Load Forge calcola i limiti dinamici massimi su tutto lo spettro:

| Metrica | Unità | Significato Fisico |
|---|---|---|
| **MOL** (*Maximum Output Level*) | dB SPL @ 1m | Il **massimo livello di pressione acustica indistorta** che il sistema può generare a quella frequenza prima che la bobina superi $X_{max}$ o che venga raggiunta la potenza termica $P_e$. |
| **MIL** (*Maximum Input Level*) | Watt | La **massima potenza elettrica applicabile** all'altoparlante prima di mandarlo a fondo corsa meccanico o bruciarne la bobina. |
| **MOL @ $F_3$** | dB SPL | Il livello sonoro massimo disponibile esattamente alla frequenza di taglio inferiore. È il vero indicatore della dinamica di un subwoofer in gamma profonda. |

---

### H. Direttive di Costruzione del Condotto (Port Sizing & Feasibility Directives)

Load Forge applica vincoli fisici rigidi durante la simulazione e l'ottimizzazione per impedire progetti impossibili da realizzare:

1. **Golden Rule sulla Velocità dell'Aria**:
   - $v_{\text{air}} \le 17\text{ m/s}$: Condotto perfetto (verde).
   - $17 < v_{\text{air}} \le 25\text{ m/s}$: Rischio fruscio ad alto volume (giallo - consiglia svasatura).
   - $v_{\text{air}} > 25\text{ m/s}$: Turbolenza severa, chuffing udibile e perdita dell'accordo (rosso).
2. **Duct Volume Directive ($V_{\text{port}} / V_{\text{box}} \le 15\%$)**:
   - Se il tubo reflex richiede un diametro così grande da occupare più del 15% del volume interno della cassa, il sistema segnala errore di fattibilità e l'ottimizzatore scarta la soluzione.
3. **Port Length Directive ($L_{\text{port}} \le L_{\text{box\_max}}$)**:
   - Impedisce che il simulatore suggerisca condotti più lunghi della diagonale interna del cabinet. In questo caso consiglia automaticamente il passaggio al **Radiatore Passivo** o al **DCCAV**.

---

### I. Classificatore Automatico di Banda (Driver Bandwidth Classifier)

Load Forge analizza istantaneamente i parametri T/S del trasduttore ($F_s, Q_{ts}, EBP, S_d, X_{max}, V_d$) e assegna una categoria funzionale oggettiva, superando le denominazioni commerciali dei produttori:

- **Subwoofer**: $F_s \le 35\text{ Hz}$, $EBP < 100$, $X_{max} \ge 6\text{ mm}$, $V_d$ elevato.
- **Woofer**: $F_s = 35 - 60\text{ Hz}$, $X_{max} \ge 3.5\text{ mm}$, bilanciamento estensione/sensibilità.
- **Midbass**: $F_s > 55\text{ Hz}$, $EBP > 120$, $Q_{ts} < 0.35$, $X_{max} < 4\text{ mm}$, elevata efficienza ($> 94\text{ dB}$).
- **Midrange / Extended Range**: $F_s > 80\text{ Hz}$, $S_d$ ridotta, non idoneo per carico sub-basso.

---

### J. Fascia di Tolleranza Monte Carlo (T/S Tolerance Band)

Gli altoparlanti reali presentano tolleranze di produzione ($\pm 5\% - 15\%$ sui parametri dichiarati) e variazioni termiche/meccaniche durante l'uso.
- Nel grafico di risposta, attivando **Tolerance Band**, Load Forge esegue una simulazione Monte Carlo stocastica variando simultaneamente $F_s, V_{as}, Q_{es}, R_e$.
- Mostra l'area ombreggiata di dispersione della risposta acustica, permettendo di valutare se il progetto è robusto o se rischia di diventare rimbombante con un esemplare di produzione leggermente fuori specifica.

---

## 3. Riepilogo Operativo: Come Usare i Parametri nei Tuoi Progetti

| Obiettivo di Progetto | Parametri Chiave da Regolare in Load Forge |
|---|---|
| **Progettare un Subwoofer Ultra-Basso e Compatto** | Selezionare carico **DCCAV** o **Reflex con Radiatore Passivo**; impostare `Max ripple frequency = 70 Hz`; verificare $MOL @ F_3 \ge 105\text{ dB}$. |
| **Evitare Rumori di Sfiato nel Condotto** | Andare nel tab *Ports*; verificare che a massima tensione di pilotaggio la velocità rimanga verde ($\le 17\text{ m/s}$); se il tubo diventa troppo lungo ($> 35\text{ cm}$), aumentare il volume o passare a passivo. |
| **Massimizzare la Tenuta in Potenza** | Consultare il grafico *MIL*; impostare un filtro passa-alto subsonico (DSP/crossover) 3–5 Hz sotto la frequenza di accordo per impedire lo svuotamento dell'escursione. |
| **Cercare il Miglior Altoparlante nel Budget** | Usare **Bass Match**; filtrare per dimensione ($S_d$) e volume massimo cassa; ordinare per *Deepest bass (F3)* o *Best value (F3 × price)*; aprire direttamente il design preferito in Box Design. |
