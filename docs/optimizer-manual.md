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

### 1.1 Coordinate native della topologia
Finder V2 separa i parametri mostrati nella UI dalle coordinate di ricerca.
Volumi e frequenze restano positivi tramite trasformazioni logaritmiche relative
allo starter; le frazioni di due camere usano il logit e BP8 usa due logits
softmax. Le coordinate sono:

| Carico | Coordinate optimizer |
|---|---|
| Sealed | volume relativo |
| Reflex | volume e accordo relativi |
| BP4 | volume totale, frazione Vs, Fp |
| BP6 | volume totale, frazione Vr, Fr, rapporto Fp/Fr |
| DCCAV | volume totale, frazione Vh, Fl, rapporto Fh/Fl |
| BP8 | volume totale, due frazioni softmax, F2, F3/F2, F1/F3 |

La trasformazione inversa garantisce volumi e frequenze positive e conserva la
somma dei volumi. I round-trip physical → optimizer → physical sono coperti da
regression test.

### 1.2 Algoritmo: Global Sniff + ricerca adattiva
L'ottimizzatore è deterministico:
1. valuta lo starter;
2. valuta una sequenza Halton fissa in un raggio locale;
3. seleziona il miglior basin feasible prima della discesa;
4. misura la sensibilità locale degli assi;
5. esegue compass search con un passo indipendente per asse;
6. prova una direzione pattern diagonale dopo spostamenti riusciti;
7. verifica i finalisti con campionamento spettrale adattivo.

Gli assi produttivi mantengono o espandono moderatamente il passo; quelli che
falliscono ripetutamente vengono dimezzati senza forzare la convergenza degli
altri assi. Non esiste alcuna scelta casuale.

### 1.3 Starter infeasible e fallback deterministico
Per estensione DCCAV viene incluso un seed a volume totale maggiore. Quando lo
starter viola già un hard constraint, vengono inoltre valutati punti al 25%,
50% e 75% della diagonale dei bounds. Tutti partecipano alla selezione del basin
prima della ricerca locale; non sono restart accodati dopo l'esaurimento del
budget.

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
- **Ripple Massimo (`max_ripple_db`)**: Differenza tra il valore massimo e minimo di SPL nella banda passante valutata. È un vincolo di fattibilità: i candidati fuori soglia entrano in un livello di score dedicato ($\ge 10^4$), graduato in base allo sforamento affinché la ricerca possa convergere verso la regione valida. Un vincitore ancora fuori soglia non viene restituito; l'ottimizzatore segnala esplicitamente che non ha trovato un allineamento conforme.
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

### 4.1 Ricerca coarse + verifica adattiva dei finalisti
Nelle ricerche batch (Bass Match / Finder) su migliaia di altoparlanti, la simulazione dell'intero spettro denso ad ogni iterazione sarebbe inefficiente:
1. **Fase 1 (Scansione Rapida)**: Vengono utilizzati **30 punti logaritmici** distribuiti sulla banda.
2. **Fase 2 (Verifica dei finalisti)**: I migliori candidati sono rivalutati su una base di almeno **80 punti**, con inserimenti deterministici intorno ad accordi, extrema e regioni ad alta curvatura, più **20 punti** intorno a $F_3$.
3. **Risposta Finale**: Il box scelto viene simulato sulla risoluzione richiesta dall'utente, normalmente **240 punti**. Il ripple viene ricalcolato su questa risposta e il candidato viene escluso se supera il limite.

Con un Ripple frequency ceiling attivo, sia la griglia coarse sia quella finale
usano i punti richiesti sotto il limite e una coda di 9 punti sopra: i 30 punti
coarse diventano normalmente 38 punti distinti.

Bass Match espone profili da **30/60/120 valutazioni di box per combinazione
driver × carico**, ridotte a 24 nel runtime Cloud Run. Questi sono
i tentativi complessivi: non vengono assegnati 30 tentativi a ciascuna
variabile. Infinite baffle e passive radiator non eseguono questa ricerca del
box: usano rispettivamente il modello senza box e lo starter fisico dedicato.
Il numero richiesto non viene mai superato e include starter, sniff,
sensitivity e pattern search. I campioni in frequenza di un box già valutato
sono un budget spettrale separato.
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
4. Risultato: l'ottimizzatore trova il volume e l'accordo che spingono $F_3$ al valore più basso possibile, valutando il ripple soltanto nella banda utile sotto gli 80 Hz. Il limite è un vincolo di fattibilità verificato anche sulla risposta finale.

### Scenario B: Diffusore Hi-Fi Lineare a 2 o 3 Vie
1. Imposta **Optimization goal** = `Flat response` o `Balanced`.
2. Imposta **Max ripple** = `1.5 dB` o `2.0 dB`.
3. Lascia **Ripple frequency ceiling** = `0` (banda intera).
4. Risultato: cabinet con smorzamento ottimale, assenza di code risonanti e raccordo dolce con la gamma media.

### Scenario C: Obiettivo di Frequenza Preciso (Es. 35 Hz per Home Theater)
1. Imposta **Target F3** = `35.0 Hz`.
2. Lascia **Max total volume** = `0` (o limite massimo).
3. Risultato: l'algoritmo calcolerà il box più piccolo possibile in grado di raggiungere 35 Hz, risparmiando spazio e legname.
