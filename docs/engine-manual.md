# Manuale del Motore Acustico di Load Forge (Engine User Manual)

Questo manuale è una guida tecnica e pratica per l'utilizzatore di **Load Forge**. Spiega nel dettaglio il funzionamento del motore acustico (`src/engine.py`), il significato fisico di ogni singolo parametro, il modo in cui influenza la simulazione e come interpretare correttamente grafici e metriche.

---

## 1. Architettura del Motore Acustico

Il motore di simulazione di Load Forge impiega una modellazione ibrida:
1. **Circuiti Acustici a Parametri Concentrati (Lumped Parameter Circuits)**:
   - Per carichi compatti (*DCCAV, Bass Reflex, Sealed, Bandpass del 4° e 6° ordine, Radiatore Passivo*), il sistema è modellato come una rete elettromeccanica-acustica equivalente in dominio di frequenza complesso ($\omega = 2\pi f$).
   - Vengono risolte le impedenze acustiche complesse del trasduttore, delle camere d'aria e dei risuonatori, calcolando la velocità volumetrica del cono $U_c(\omega)$ e dei condotti $U_p(\omega)$.
2. **Matrici di Trasferimento per Guide d'Onda Distribuite (Distributed Transmission Matrices)**:
   - Per condotti e linee acustiche estese (*Linee di Trasmissione TL, MLTL, Trombe Tapped e Back-Loaded*), il motore suddivide la guida d'onda in segmenti e applica matrici di trasmissione acustica $T$-matrix 2×2 che tengono conto della propagazione d'onda stazionaria, della rastremazione geometrica e delle perdite viscose/termiche del fonoassorbente.
3. **Radiazione Acustica in Semispazio (2π Half-Space)**:
   - La pressione acustica totale in campo lontano a 1 metro di distanza è calcolata dalla somma vettoriale coerente (modulo e fase) di tutte le sorgenti radianti:
     $$p_{\text{total}}(\omega) = j\omega \frac{\rho_0}{2\pi d} \left( U_{\text{cone}}(\omega) + \sum U_{\text{port}}(\omega) \right) e^{-j k d}$$
   - Dove $\rho_0 = 1.204\text{ kg/m}^3$ (densità dell'aria a 20°C) e $c = 343.2\text{ m/s}$ (velocità del suono).

---

## 2. Parametri Elettromeccanici del Trasduttore (Thiele & Small)

Questi parametri descrivono le proprietà fisiche del cono, del gruppo magnetico e della sospensione elastica del woofer in aria libera.

| Parametro | Unità | Nome Esteso | Significato Fisico e Impatto sulla Simulazione |
|---|---|---|---|
| **$F_s$** | $\text{Hz}$ | *Resonance Frequency* | Frequenza di risonanza naturale dell'altoparlante in aria libera. Dipende dalla massa mobile ($M_{ms}$) e dalla cedevolezza delle sospensioni ($C_{ms}$): $F_s = \frac{1}{2\pi \sqrt{M_{ms} C_{ms}}}$. Definisce il limite inferiore naturale di estensione del trasduttore. |
| **$V_{as}$** | $\text{Litri}$ | *Equivalent Acoustic Volume* | Volume d'aria la cui cedevolezza acustica equivale a quella delle sospensioni meccaniche del cono: $V_{as} = \rho_0 c^2 S_d^2 C_{ms}$. Valori alti indicano sospensioni molto morbide (richiedono box più grandi); valori bassi indicano sospensioni rigide. |
| **$Q_{ts}$** | adimensionale | *Total Quality Factor* | Fattore di merito totale a risonanza ($F_s$), dato dal parallelo tra perdite elettriche e meccaniche: $Q_{ts} = \frac{Q_{es} Q_{ms}}{Q_{es} + Q_{ms}}$. Determina l'allineamento naturale: $Q_{ts} < 0.35$ predilige reflex/DCCAV/trombe; $Q_{ts} \approx 0.38 - 0.45$ ideale per reflex QB3/B4; $Q_{ts} > 0.45$ predilige sospensione pneumatica (Sealed). |
| **$Q_{es}$** | adimensionale | *Electrical Quality Factor* | Fattore di merito per smorzamento elettromagnetico della bobina nel traferro: $Q_{es} = \frac{2\pi F_s M_{ms} R_e}{(B\cdot l)^2}$. Dipende direttamente dal fattore di forza $B\cdot l$ e dalla resistenza $R_e$. |
| **$Q_{ms}$** | adimensionale | *Mechanical Quality Factor* | Fattore di merito per attrito e smorzamento meccanico interno di centratore (spider) e bordo (surround): $Q_{ms} = \frac{2\pi F_s M_{ms}}{R_{ms}}$. Valori tipici tra 3.0 e 10.0. |
| **$R_e$** | $\Omega$ | *DC Resistance* | Resistenza ohmica in corrente continua della bobina mobile. Costituisce la componente resistiva primaria dell'impedenza d'ingresso e determina la corrente assorbita a bassa frequenza. |
| **$L_e$** | $\text{mH}$ | *Voice Coil Inductance* | Induttanza parassita della bobina mobile (misurata convenzionalmente a 1 kHz). Provoca la risalita dell'impedenza elettrica in gamma medio-alta ($Z_e = R_e + j\omega L_e$). |
| **$S_d$** | $\text{cm}^2$ | *Effective Piston Area* | Superficie emissiva utile del pistone radiante (cono + metà del bordo elastico). Determina l'accoppiamento acustico con l'aria e il volume d'aria spostato $V_d = S_d \cdot X_{max}$. |
| **$M_{ms}$** | $\text{g}$ | *Moving Mass* | Massa mobile totale in aria (cono, bobina mobile, supporto, centratore e carico d'aria d'irradiazione su entrambi i lati del cono). |
| **$C_{ms}$** | $\text{mm/N}$ | *Mechanical Compliance* | Cedevolezza meccanica della sospensione elastica (l'inverso della rigidità della molla). |
| **$B\cdot l$** | $\text{T}\cdot\text{m}$ | *Force Factor* | Prodotto tra l'induzione magnetica nel traferro ($B$) e la lunghezza del filo della bobina immerso nel campo ($l$). È il "motore" del cono: forza generata $F = B\cdot l \cdot I$. |
| **$X_{max}$** | $\text{mm}$ | *Maximum Linear Excursion* | Escursione lineare massima picco (one-way) della bobina mobile prima che esca dalla zona di linearità del campo magnetico ($B\cdot l$) o della sospensione ($C_{ms}$). Definisce il limite meccanico MOL/MIL del sistema. |
| **$P_e$** | $\text{Watt}$ | *Thermal Power Handling* | Potenza termica massima continua dissipabile dalla bobina senza danneggiarsi per sovratemperatura. |

### Correzione *Panel Air Loading* (Massa Aggiunta del Pannello)
Nel montaggio reale su pannello (baffle), il volume d'aria compreso nello spessore della flangia e la restrizione di gola aumentano la massa d'aria radiante che grava sul cono:
- Il motore calcola la massa virtuale aggiunta $\Delta M_{\text{air}} = \frac{8}{3\pi} \rho_0 \cdot r_{\text{piston}}^3 \cdot \alpha_{\text{coupling}}$.
- La frequenza di risonanza effettiva montata si abbassa: $F_{s, \text{mounted}} = F_s \sqrt{\frac{M_{ms}}{M_{ms} + \Delta M_{\text{air}}}}$.

---

## 3. Topologie di Carico Acustico (Enclosure Models)

### A. Bass Reflex (Accordo Semplice / Risuonatore di Helmholtz)
- **Parametri**:
  - $V_b$ (Litri): Volume netto interno della cassa.
  - $F_b$ (Hz): Frequenza di accordo del condotto o passivo.
- **Meccanica Acustica**:
  - L'aria nel box agisce come molla acustica ($C_{ab} = \frac{V_b}{\rho_0 c^2}$); l'aria nel condotto agisce come massa acustica ($M_{ap} = \frac{\rho_0 L_{\text{eff}}}{S_{\text{port}}}$).
  - Alla frequenza $F_b$, il condotto entra in risonanza ed emette la quasi totalità della pressione acustica, mentre l'escursione del cono crolla a un minimo locale, proteggendo il cono. Sotto $F_b$, il sistema perde il controllo e il roll-off è del 4° ordine (24 dB/ottava).

### B. DCCAV (Double Cavity Asymmetric Vent / Doppio Asimmetrico Serie)
- **Topologia**:
  $$\text{Driver} \longrightarrow V_h \parallel \text{Port } h \longrightarrow V_l \parallel \text{Port } l$$
- **Parametri**:
  - $V_h$ (Litri): Volume della prima camera (superiore), a diretto contatto con il retro del woofer.
  - $f_h$ (Hz): Frequenza di risonanza del condotto superiore (inter-camera).
  - $V_l$ (Litri): Volume della seconda camera (inferiore).
  - $f_l$ (Hz): Frequenza di risonanza del condotto inferiore (di uscita verso l'ambiente).
- **Vantaggi Acustici**:
  - Genera **due minimi distinti di escursione** del cono in gamma bassa (uno a $f_l$, l'altro a $f_h$).
  - Ampia banda passante di emissione controllata, escursione ridotta su un intervallo di frequenze molto più ampio rispetto al reflex tradizionale, e roll-off più graduale.

### C. Sospensione Pneumatica (Sealed Box / Closed Enclosure)
- **Parametri**:
  - $V_b$ (Litri): Volume chiuso ermetico.
- **Metriche Risultanti**:
  - $F_c = F_s \sqrt{1 + \frac{V_{as}}{V_b}}$ (Frequenza di risonanza del sistema chiuso).
  - $Q_{tc} = Q_{ts} \sqrt{1 + \frac{V_{as}}{V_b}}$ (Fattore di merito totale del sistema chiuso).
- **Caratteristiche**:
  - Roll-off dolce del 2° ordine (12 dB/ottava), eccellente risposta ai transienti e ritardo di gruppo minimo.
  - Allineamenti classici: $Q_{tc} = 0.5$ (Bessel, transiente ottimale), $Q_{tc} = 0.707$ (Butterworth B2, massima linearità in banda), $Q_{tc} > 0.9$ (picco d'impatto mid-bass).

### D. Bandpass del 4° Ordine (BP4)
- **Topologia**: Camera chiusa posteriore ($V_s$) + Camera accordata anteriore ($V_p, F_p$).
- **Funzionamento**: Emette solo dal condotto anteriore; agisce come un filtro passa-banda acustico (12 dB/ottava passa-alto, 12 dB/ottava passa-basso). Elimina la necessità di filtri passa-basso crossover complessi.

### E. Bandpass del 6° Ordine (BP6 - Parallelo o Serie)
- **Topologia**: Due camere accordate ($V_r, F_r$ posteriore; $V_p, F_p$ anteriore).
- **Funzionamento**: Due risonanze indipendenti; efficienza elevata nella banda utile con roll-off ripidi (24 dB/ottava alle due estremità).

### F. Radiatore Passivo (Passive Radiator)
- Sostituisce il condotto del bass reflex con un cono passivo dotato di massa mobile $M_{mp}$, cedevolezza $C_{mp}$ e superficie $S_p$.
- Elimina totalmente i fruscii da turbolenza dell'aria nei condotti e consente accordi sub-bassi in box ultra-compatti dove un tubo lungo non entrerebbe fisicamente.

---

## 4. Parametri dei Condotti e Risonatori (Port Sizing Directives)

La corretta dimensione del condotto è fondamentale per evitare compressione dinamica e rumori d'aria (*chuffing*).

1. **Diametro Utile del Condotto ($D_{\text{port}}$, cm)**:
   - Sezione geometrica $S_p = \pi (D_{\text{port}} / 2)^2$.
2. **Lunghezza Geometrica vs Efficace ($L_{\text{port}}$, cm)**:
   - L'aria in prossimità delle estremità del tubo si muove insieme all'aria interna. Il motore applica la correzione di terminazione (*end correction*):
     $$L_{\text{eff}} = L_{\text{geom}} + 0.732 \cdot D_{\text{port}} \quad (\text{flangiato/svasato})$$
     $$F_b = \frac{c}{2\pi} \sqrt{\frac{S_p}{V_b \cdot L_{\text{eff}}}}$$
3. **Golden Rule sulla Velocità dell'Aria ($v_{\text{air}}$, m/s)**:
   - **Verde ($\le 17\text{ m/s}$)**: Moto laminare pulito, assenza di rumori e compressione.
   - **Giallo ($17 - 25\text{ m/s}$)**: Inizio di turbolenza alle massime potenze; raccomandata svasatura (*flared port*).
   - **Rosso ($> 25\text{ m/s}$)**: Severa turbolenza, rumore d'aria udibile, decadimento dell'accordo per perdite non lineari.
4. **Volume Occupato dal Condotto ($V_{\text{duct}}$)**:
   - Il volume fisico occupato dal tubo deve essere sottratto dal volume lordo del mobile per determinare il volume netto $V_b$.

---

## 5. Fattori di Perdita e Smorzamento ($Q_{\text{abs}}, Q_{\text{leak}}, Q_{\text{port}}$)

Nessun cabinet è ideale; le perdite acustiche interne modificano la risposta e l'impedenza:

- **$Q_{\text{abs}}$ (Perdite per Assorbimento Termico/Viscoso del Fonoassorbente)**:
  - Box vuoto: $Q_{\text{abs}} \approx 30 - 50$.
  - Box foderato internamente: $Q_{\text{abs}} \approx 15 - 20$ (default standard 15.0).
  - Box riempito densamente: $Q_{\text{abs}} \approx 5 - 10$ (aumenta anche la cedevolezza apparente del volume fino al 10–15%).
- **$Q_{\text{leak}}$ (Perdite per Trafilamento d'Aria del Mobile)**:
  - Box perfettamente sigillato ed ermetico: $Q_{\text{leak}} \ge 1000$ (default 1000.0).
  - Box con leggere perdite su giunzioni/terminali: $Q_{\text{leak}} \approx 50 - 100$.
  - Perdite gravi: $Q_{\text{leak}} < 20$.
- **$Q_{\text{port}}$ (Perdite per Attrito Viscoso lungo le Pareti del Tubo)**:
  - Condotti lisci e ampi: $Q_{\text{port}} \approx 30 - 50$ (default 15.0 prudenziale).
  - Tubi stretti, lunghi o con curve a gomito: $Q_{\text{port}} \approx 5 - 15$.

---

## 6. Parametri Elettrici di Pilotaggio

- **Tensione di Pilotaggio ($V_{\text{RMS}}$)**:
  - Default nominale: **2.83 V** (corrispondente a 1 Watt su carico puramente resistivo da 8 $\Omega$).
  - Per valutare le massime prestazioni a una data potenza $P$, impostare: $V_{\text{RMS}} = \sqrt{P \cdot R_n}$.
- **Resistenza in Serie Parassita ($R_{\text{series}}$, $\Omega$)**:
  - Somma della resistenza dei cavi di potenza, dell'induttanza serie del filtro crossover passivo e della resistenza d'uscita dell'amplificatore (legata al fattore di smorzamento $DF = R_L / R_{\text{out}}$).
  - Aumenta il $Q_{es}$ apparente: $Q_{es}' = Q_{es} \cdot \left(1 + \frac{R_{\text{series}}}{R_e}\right)$, alzando il $Q_{ts}$ complessivo e incrementando l'enfasi/ripple sulla risonanza.

---

## 7. Metriche Risultanti e Interpretazione dei Grafici

### A. Risposta in Frequenza (SPL Curve)
- **SPL Total (dB)**: Livello di pressione acustica totale irradiata in semispazio a 1 m con la tensione impostata.
- **SPL Cone / SPL Vent**: Contributi separati di cono e condotti, con cancellazione di fase sotto l'accordo.
- **Frequenze di Taglio ($F_3, F_6, F_{10}$)**:
  - $F_3$ ($-3\text{ dB}$): Punto a metà potenza rispetto al livello di riferimento di banda utile. Definisce convenzionalmente il limite inferiore di riproduzione Hi-Fi.
  - $F_6$ ($-6\text{ dB}$): Utile per prevedere l'integrazione acustica con l'effetto *Room Gain* dell'ambiente d'ascolto (che rinforza le frequenze sotto i 40 Hz di circa 6–12 dB/ottava).
  - $F_{10}$ ($-10\text{ dB}$): Limite di estensione percepibile in ambiente chiuso.

### B. Escursione del Cono (Cone Excursion)
- Mostra lo spostamento del cono (in mm di picco) in funzione della frequenza.
- La linea tratteggiata rossa rappresenta $X_{max}$. Le frequenze in cui la curva supera $X_{max}$ indicano distorsione da compressione meccanica e rischio di sovraescursione.

### C. Limiti Massimi di Pressione e Potenza (MOL / MIL)
- **MOL (Maximum Output Level, dB SPL)**:
  - Il massimo livello sonoro indistorto che il sistema può generare a ciascuna frequenza, calcolato combinando contemporaneamente il limite termico di potenza ($P_e$) e il limite di escursione lineare ($X_{max}$).
- **MIL (Maximum Input Level, Watt)**:
  - La massima potenza elettrica applicabile all'altoparlante prima che si superi $X_{max}$ o $P_e$. Evidenzia dove il woofer è vulnerabile alle basse frequenze.

### D. Modulo e Fase dell'Impedenza Elettrica (Impedance & Phase)
- **Minimo d'Impedenza ($Z_{\text{min}}$, $\Omega$)**: Il punto più basso della curva (solitamente tra 100 e 200 Hz o tra i due picchi reflex). Non deve scendere sotto la capacità di carico dell'amplificatore (es. 3.2 $\Omega$ per un sistema nominale da 4 $\Omega$).
- **Picchi di Risonanza**:
  - Cassa Chiusa: 1 picco a $F_c$.
  - Bass Reflex / BP4: 2 picchi che circondano la sella dell'accordo $F_b$.
  - DCCAV / BP6: 3 picchi di risonanza ben definiti che delimitano le due camere accordate.

### E. Ritardo di Gruppo (Group Delay, ms)
- Definito come la derivata negativa della fase acustica rispetto alla frequenza: $\tau_g(\omega) = -\frac{d\phi(\omega)}{d\omega}$.
- Esprime il ritardo temporale con cui le diverse componenti di frequenza vengono emesse. Valori eccessivi ($> 20 - 30\text{ ms}$ sotto i 40 Hz) producono un basso "lento", gommoso e poco articolato.

---

## 8. Riepilogo Operativo per il Progettista

1. **Scelta del Woofer**:
   - Calcolare l'$EBP = F_s / Q_{es}$. Se $EBP < 50 \rightarrow$ Cassa Chiusa; se $EBP \approx 50 - 90 \rightarrow$ Reflex/DCCAV/Sealed; se $EBP > 90 \rightarrow$ Bass Reflex, DCCAV, Trombe.
2. **Dimensionamento Volume**:
   - Rispettare il volume ottimale suggerito dal motore o utilizzare l'ottimizzatore automatico per raggiungere il target di estensione $F_3$ con il minimo ingombro.
3. **Controllo Condotti**:
   - Verificare che la velocità dell'aria nel grafico *Ports* non superi $17\text{ m/s}$ alla potenza nominale.
4. **Verifica Escursione e Protezione**:
   - Osservare il grafico *Excursion* per posizionare l'eventuale filtro passa-alto subsonico (infrasonico) alla frequenza in cui l'escursione inizia a divergere sotto l'accordo.
