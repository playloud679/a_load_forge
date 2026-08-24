# Manuale Tecnico dell'Ottimizzatore Acustico (Load Forge)

L'ottimizzatore acustico di Load Forge è un motore deterministico di calcolo non-lineare vincolato progettato per determinare la configurazione geometrica e di accordo ideale di un dato altoparlante su tutte le topologie di carico supportate:
- **DCCAV** (*Double Chamber Cascaded Asymmetric Venting*)
- **Bass Reflex** (accordo con condotto o con radiatore passivo)
- **Cassa Chiusa** (*Sealed / Suspension Pneumatic*)
- **Passa-Banda del 4° Ordine** (*Single-tuned Bandpass*)
- **Passa-Banda del 6° Ordine** (*Dual-tuned Bandpass*)
- **Passa-Banda dell'8° Ordine** (*Triple-tuned Bandpass*)

---

## 1. Architettura e Algoritmo di Ricerca

### 1.1 Spazio di Ricerca Logaritmico
Tutti i parametri dimensionali (volumi in litri $V$, frequenze di accordo in Hertz $F$) vengono mappati internamente nello spazio dei logaritmi naturali:
$$\mathbf{p} = \begin{bmatrix} \ln(V) \\ \ln(F) \end{bmatrix}$$
Questo garantisce una variazione percentuale uniforme lungo ogni asse ed evita asimmetrie numeriche tra volumi ampi e piccole variazioni di frequenza.

### 1.2 Algoritmo: Coordinate Descent (Compass Search)
L'ottimizzatore adotta un metodo di **Coordinate Descent deterministico (Compass Search)**:
1. **Passo Iniziale**: Si parte da un passo logaritmico $\Delta = 0.4$.
2. **Esplorazione degli Assi**: Per ciascun parametro $p_i$, l'algoritmo valuta lo score acustico a $p_i + \Delta$ e $p_i - \Delta$.
3. **Discesa**: Se viene trovato un miglioramento significativo ($\Delta \text{score} > 10^{-9}$), la nuova coordinata viene accettata e l'esplorazione prosegue lungo quella direzione.
4. **Dimezzamento del Passo**: Se nessun asse produce un miglioramento, il passo viene dimezzato ($\Delta \leftarrow \Delta / 2$) fino al raggiungimento della convergenza fine ($\Delta < 0.02$).
5. **Completamente Riproducibile**: Non vi è alcun elemento stocastico/casuale; lo stesso set di parametri T/S e di vincoli produce sempre l'allineamento identico al millesimo di Hertz.

### 1.3 Superamento dei Minimi Locali e Punti di Riavvio (Restarts)
Nei carichi complessi come il DCCAV o nei reflex ad alta escursione (dove le dimensioni del condotto possono rendere certe regioni non costruibili), il Compass Search locale potrebbe rimanere intrappolato:
- **Seed per Estensione Profonda (DCCAV)**: Per `objective="extension"`, viene valutato un secondo punto di partenza a volumi maggiori $\ln(V_0 \cdot 3.0)$ per catturare il bacino sub-basso profondo.
- **Ripartizioni Determinate sulla Diagonale**: Se il punteggio iniziale viola i vincoli di costruibilità ($\text{score} \ge 10^5$), l'algoritmo esegue ulteriori tentativi a frazioni predeterminate (25%, 50%, 75%) della diagonale dello spazio di ricerca, garantendo sempre una via d'uscita verso allineamenti fisicamente realizzabili.

---

## 2. Obiettivi di Ottimizzazione (`objective`)

L'utente può selezionare tre pesature fondamentali:

| Obiettivo | Peso $F_3$ | Peso Ripple | Comportamento |
|---|---|---|---|
| **Max extension** | 1.0 | 0.15 | Fa dominare la discesa in frequenza sub-bassa ($F_3$ minimo); le penalità consultive di escursione e group delay pesano meno, ma ripple e barriere costruttive mantengono il loro peso. |
| **Balanced** | 0.55 | 0.55 | Bilanciamento equivalente tra estensione in frequenza, regolarità di risposta e compattezza del volume. |
| **Flat response** | 0.2 | 1.1 | Priorità netta alla planarità della curva di risposta utile, anche a costo di estensione. |

---

## 3. Funzione di Costo e Vincoli (`_score_alignment`)

La funzione di costo restituisce un valore numerico in cui valori minori indicano allineamenti migliori. La formula integra barriere rigide, penalità acustiche e termini di regolarizzazione:

$$\text{Score} = \text{Score}_{\text{base}} + \text{Penalità}_{\text{costruzione}} + \text{Penalità}_{\text{acustica}} + \text{Regolarizzazione}_{\text{volume}}$$

### 3.1 Barriere Rigide di Costruibilità (Score $\ge 10^5$)
Se una configurazione viola le leggi fisiche o geometriche, viene scartata con uno score enorme:
1. **Diametro Minimo del Condotto**: Calcolato in base al criterio di spostamento volumetrico $S_d \cdot X_{\max}$ e al limite sulla velocità dell'aria ($v_{\text{air}} \le 17\text{ m/s}$). Il limite geometrico configurato è 60 cm e la barriera dell'ottimizzatore scatta oltre il 95% del limite, cioè 57 cm.
2. **Frazione di Volume del Condotto**: Il condotto non può occupare più del 10% del volume netto della camera che accorda ($\text{Vol}_{\text{port}} / V_{\text{box}} \le 0.10$).
3. **Lunghezza Massima del Condotto**: Il condotto in linea retta non può eccedere la diagonale massima interna del cabinet ($L_{\text{port}} / L_{\text{box}} \le 1.0$).
4. **Credibilità Acustica DCCAV**: In DCCAV, la frequenza $F_3$ non può essere inferiore al limite asintotico di risonanza $0.65 \cdot F_l$.

### 3.2 Vincoli Acustici Utente
- **Ripple Massimo (`max_ripple_db`)**: Differenza tra il valore massimo e minimo di SPL nella banda passante valutata. Qualsiasi eccesso oltre la soglia riceve una penalità severa ed immediata:
  $$\text{Penalità}_{\text{ripple}} = 5.0 \cdot (\text{Ripple} - \text{MaxRipple})$$
- **Limite Superiore Frequenza Ripple (`ripple_max_freq_hz`)**: Se impostato (es. $70\text{ Hz}$ o $80\text{ Hz}$ per subwoofer), la finestra di calcolo del ripple viene troncata a tale frequenza:
  $$\text{Banda Ripple} = [1.2 \cdot F_3, \min(\text{Upper}, F_{\text{ripple\_max}})]$$
  Le variazioni di SPL a frequenze superiori vengono ignorate, permettendo all'altoparlante di raggiungere l'estensione massima senza essere penalizzato per ciò che accade fuori dalla banda d'uso.
- **Escursione Massima (`max_excursion_ratio`)**: Controlla che il picco di escursione della membrana non superi un multiplo di $X_{\max}$ (default $1.0$).
- **Group Delay Massimo (`max_group_delay_ms`)**: Penalizza ritardi di gruppo eccessivi nella banda sub-bassa.
- **Target $F_3$ specifico (`target_f3_hz`)**: Se impostato, l'ottimizzatore ricerca il box più compatto possibile in grado di raggiungere esattamente quella frequenza di taglio, smettendo di spendere litri inutili.

### 3.3 Regolarizzazione Dimensionale
A parità di prestazioni acustiche, l'ottimizzatore privilegia sempre il cabinet più compatto:
$$\text{Regolarizzazione} = w_{\text{size}} \cdot \frac{V_{\text{total}}}{V_{\text{as}}}$$
dove $w_{\text{size}}$ aumenta fortemente non appena il target di estensione desiderato viene raggiunto.

---

## 4. Griglia di Calcolo e Prestazioni

### 4.1 Griglia a Due Stadi (Broad Scan + Winner Refinement)
Nelle ricerche batch (Bass Match / Finder) su migliaia di altoparlanti, la simulazione dell'intero spettro denso ad ogni iterazione sarebbe inefficiente:
1. **Fase 1 (Scansione Rapida)**: Vengono utilizzati **30 punti logaritmici** distribuiti sulla banda.
2. **Fase 2 (Raffinamento del Vincitore)**: Solo sull'allineamento vincente viene applicata una seconda passata a **20 punti densi** centrati nell'intorno di $F_3$ con interpolazione sub-Hertziana.
3. **Risposta Finale**: Il box scelto viene simulato sulla risoluzione richiesta dall'utente, normalmente **240 punti** e al massimo 80 nel runtime Cloud Run.

Con un Ripple frequency ceiling attivo, sia la griglia coarse sia quella finale
usano i punti richiesti sotto il limite e una coda di 9 punti sopra: i 30 punti
coarse diventano normalmente 38 punti distinti.

Bass Match consente al Compass Search al massimo **30 valutazioni di box per
combinazione driver × carico**, ridotte a 24 nel runtime Cloud Run. Questi sono
i tentativi complessivi: non vengono assegnati 30 tentativi a ciascuna
variabile. Infinite baffle e passive radiator non eseguono questa ricerca del
box: usano rispettivamente il modello senza box e lo starter fisico dedicato.
Il budget non cresce con la dimensionalità: Sealed usa un asse, DCCAV quattro
e Bandpass 8th order sei. I carichi complessi vengono quindi esplorati meno
densamente per variabile, in cambio di un tempo batch prevedibile.
L'API generale `optimize_alignment()`, usata fuori dal Finder, conserva invece
default più larghi di 260 valutazioni e 160 frequenze, senza refinement locale
se il chiamante non lo richiede.

### 4.2 Griglia Segmentata per Subwoofer (`segmented_frequency_grid`)
Quando è attivo un tetto di frequenza per il ripple ($F_{\text{ripple\_max}}$):
- **Banda Utile Sub-Bassa ($10\text{ Hz} \to F_{\text{ceiling}}$)**: Campionamento logaritmico denso per la massima precisione su $F_3$, risonanze e velocità nei condotti.
- **Banda Superiore ($F_{\text{ceiling}} \to 500\text{ Hz}$)**: Solo **9 punti sparsi**, sufficienti per stimare la sensibilità di riferimento senza sovraccaricare la CPU.

---

## 5. Guida Rapida all'Uso Pratico

### Scenario A: Progettazione di un Subwoofer Pura Estensione
1. Imposta **Optimization goal** = `Max extension`.
2. Imposta **Max total volume** = volume massimo accettabile nel tuo ambiente (es. `60 L`).
3. Imposta **Ripple frequency ceiling** = frequenza di incrocio del passa-basso (es. `70 Hz` o `80 Hz`).
4. Risultato: l'ottimizzatore trova il volume e l'accordo che spingono $F_3$ al valore più basso possibile, valutando il ripple soltanto nella banda utile sotto gli 80 Hz. Il limite è una penalità di score, non una garanzia assoluta: il risultato finale va verificato nella tabella.

### Scenario B: Diffusore Hi-Fi Lineare a 2 o 3 Vie
1. Imposta **Optimization goal** = `Flat response` o `Balanced`.
2. Imposta **Max ripple** = `1.5 dB` o `2.0 dB`.
3. Lascia **Ripple frequency ceiling** = `0` (banda intera).
4. Risultato: cabinet con smorzamento ottimale, assenza di code risonanti e raccordo dolce con la gamma media.

### Scenario C: Obiettivo di Frequenza Preciso (Es. 35 Hz per Home Theater)
1. Imposta **Target F3** = `35.0 Hz`.
2. Lascia **Max total volume** = `0` (o limite massimo).
3. Risultato: l'algoritmo calcolerà il box più piccolo possibile in grado di raggiungere 35 Hz, risparmiando spazio e legname.
