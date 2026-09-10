# Load Forge · Documento di Recap Esecutivo, Funzionale, Accounting e Visione Futura

**ID Documento:** `LF-EXEC-RECAP-2026`  
**Data:** Settembre 2026  
**Versione Software Riferimento:** `0.16.7` (Catalogo `1.0.0`, Schema LFP `v2`)  
**Autore:** Playloud Engineering / Antigravity AI  
**Scopo:** Quadro completo su cosa sia Load Forge, catalogo di tutte le funzioni operative, analisi dettagliata del sistema di account & billing, posizionamento tecnologico e base di discussione per l'evoluzione futura del prodotto.

---

## 1. Cos'è Load Forge: Identità, Visione e Posizionamento

### 1.1 Definizione e Scopo
**Load Forge** è una suite ingegneristica integrata per l'**elettroacustica applicata e la progettazione avanzata di diffusori acustici**.
Nata per superare i limiti storici del software acustico (applicativi Windows legacy fermi agli anni '90 o 2000, privi di connettività, con motori chiusi e interfacce obsolete), Load Forge propone una **pipeline digitale continua e moderna**:

$$\text{Metrologia (Hardware)} \longrightarrow \text{Simulazione (Fisica Non-Lineare)} \longrightarrow \text{Ottimizzazione (Algoritmica)} \longrightarrow \text{CAD & Manifattura (3D)}$$

Il software unisce:
1. **Un motore analitico lumped-parameter di livello accademico**: matrici di impedenza elettro-mecano-acustica nel dominio di Laplace, con calcolo rigoroso dei limiti non lineari (escursione $X(f)$ vs $X_{\max}$, limiti termici/meccanici MIL/MOL, velocità e compressione nei condotti).
2. **Un motore di ricerca algoritmica di mercato (Bass Match)**: non un semplice archivio, ma un risolutore euristico/Pareto su un catalogo continuo di oltre 10.000 altoparlanti con prezzi reali aggiornati dal web.
3. **Uno studio di fabbricazione digitale parametrica (Port CAD / Flare Forge)**: generazione istantanea di quote 2D SVG e mesh 3D STL a spessore normale costante pronte per la stampa 3D additiva.
4. **Un'architettura SaaS moderna, ibrida e collaborativa**: fruibile via web/cloud (Streamlit reattivo con tema Cyber Dark/Emerald), con autosalvataggio NoSQL distribuito (Firestore), cronologia versioni immutabile, condivisione sociale e compatibilità locale-first (`.lfp`, `.frd`, `.zma`).

---

### 1.2 L'Ecosistema Allargato: "Playloud Acoustic Forge Suite"
Load Forge è il pilastro centrale di una suite modulare:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              PLAYLOUD ACOUSTIC FORGE SUITE                             │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ 1. Z_bench (Port 8502)   │ 2. Load Forge (Port 8501)│ 3. Flare Forge & Port CAD        │
│ • Metrologia Hardware    │ • Simulatore Multi-Carico│ • CAD Parametrico                │
│ • Dayton Audio DATS V3   │ • Finder "Bass Match"    │ • Offset Normale Costante        │
│ • Misura Complessa Z(f)  │ • Limiti MIL / MOL       │ • Esportazione 3D STL Slicer     │
│ • Bridge Cloud Firestore │ • Catalogo 10.000+ SKU   │ • Trombe (Tractrix, OS-SE, LeCl.)│
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

* **Z_bench**: banco di laboratorio collegato all'hardware Dayton Audio DATS V3 (codec audio Texas Instruments PCM2900C). Esegue sweep sinusoidale sincrono con calibrazione a due step (resistenza cavi + riferimento $1\text{ k}\Omega$) e ricava i parametri T/S reali con il metodo delle masse aggiunte (anche con monete calibrate EUR/USD), inviando i dati con 1-click al cloud o al catalogo locale di Load Forge.
* **Autonomous Catalog Crawler Daemon**: demone autonomo in background (gestito nel workspace dedicato `load_forge_crawler`) che setaccia costantemente siti ufficiali di produttori e oltre 20 distributori internazionali (Thomann, TLHP, Parts Express, Masori, SoundImports, ecc.) estraendo parametri T/S verificati e prezzi reali.

---

### 1.3 Posizionamento Competitivo nel Mercato

| Software | Limiti storici / Confronto con Load Forge |
|---|---|
| **WinISD** | Gratuito ma fermo da oltre 15 anni. Solo Windows desktop, nessun database moderno con prezzi, nessun calcolo MOL/MIL avanzato, nessuna topologia esotica come DCCAV, zero esportazione 3D per stampa. |
| **BassBox Pro** | Software commerciale a pagamento, interfaccia anni '90, chiuso, rigido, nessuna ricerca inversa algoritmica sul mercato, nessun supporto web o cloud. |
| **Hornresp** | Estremamente potente sul piano teorico ma con curva di apprendimento ripidissima, interfaccia scarna, nessuna nozione di catalogo commerciale, prezzi o vincoli di producibilità CAD. |
| **VituixCAD** | Strumento eccellente per la simulazione del crossover e diffrazione baffle, ma non funge da ottimizzatore di volume/box né da crawler di mercato. (Load Forge si interfaccia perfettamente con VituixCAD tramite export `.frd` e `.zma`). |
| **AUDIO for Windows (AFW)** | Riferimento storico per carichi complessi come il DCCAV. Load Forge integra un modulo di esportazione template `.afw` nativo per verificare i calcoli del doppio risonatore. |

**Il "Moat" (Vantaggio Difendibile) di Load Forge**:  
È l'unico software al mondo che **risolve il problema inverso**: *"Dato un volume massimo di $40\text{ litri}$, un budget di $150\text{ €}$ e un obiettivo di $F_3 \le 30\text{ Hz}$, quale altoparlante sul mercato reale offre le massime prestazioni al costo minimo e con quale condotto costruibile?"*.

---

## 2. Tutte le Funzioni del Software: Catalogo Tecnico

L'applicazione si articola in ambienti primari e strumenti trasversali:

```text
Aree Principali:
[ Manage Projects ] ◄──► [ Bass Match (Finder) ] ◄──► [ Box Design (Laboratorio) ] ◄──► [ Explore ]
```

---

### 2.1 Bass Match (Il Finder Algoritmico & Pareto Optimizer)
È la **killer feature** di Load Forge. Non si limita a filtrare una lista, ma simula fisicamente ogni candidato compatibile generando un box ottimizzato per ciascuno.

* **Filtri di Brief Acustico**:
  * **Volume Massimo Ammesso ($V_{\text{total}}$)**: limite volumetrico reale del baule o della stanza.
  * **Massima $F_3$**: limite rigido post-simulazione (vengono scartati i progetti con punto a $-3\text{ dB}$ superiore).
  * **Minimo MOL a $F_3$**: garantisce che a bassa frequenza ci sia sufficiente pressione sonora prima del clipping meccanico ($X_{\max}$) o termico ($P_e$).
  * **SPL Minimo**: soglia di sensibilità/output alla tensione impostata.
  * **Allowed Response Ripple & Ripple Frequency Ceiling**: controllo del ripple (es. $\le 2\text{ dB}$) con possibilità di disattivare il controllo oltre una soglia (es. $80\text{–}100\text{ Hz}$ per i subwoofer), evitando di penalizzare curve che salgono naturalmente prima dell'incrocio crossover.
  * **Limiti Fisici**: Massima escursione consentita ($\le 1.0 \times X_{\max}$), massimo ritardo di gruppo (Group Delay), massa mobile massima ($M_{ms}$), induttanza bobina massima ($L_e$).
* **Strategie di Ottimizzazione**:
  * `Max extension`: prioritizza la discesa in frequenza ($F_3$ più profonda possibile).
  * `Balanced`: equilibrio perfetto tra estensione, volume compatto e linearità di risposta.
  * `Flattest`: massima linearità nel passband, minimizzando il ripple.
* **Architettura di Calcolo a Due Stadi**:
  * *Stadio 1 (Screening & Compass Search Logaritmico)*: griglia spettrale a 30 punti per testare fino a 24–30 combinazioni di parametri del box per ogni driver, applicando rigide barriere di costruibilità (lunghezza condotto $< 60\text{ cm}$, ingombro condotto $< 10\%$ del volume camera, velocità aria contenuta).
  * *Stadio 2 (Refinement Locale & Finalizzazione)*: ricampionamento a 240 punti con analisi locale concentrata attorno a $F_3$.
* **Prequalifica e Deduplicazione Automatica**:
  * Eliminazione a priori di driver incoerenti o privi dei dati minimi.
  * Collasso degli SKU identici (stessa marca, modello e impedenza) favorendo il catalogo verificato e il prezzo migliore.
* **Metriche di Graduatoria e Best Value**:
  * Ordinamento per estensione pura ($F_3, F_6, F_{10}$).
  * Ordinamento **Best Value** ($F_3 \times \text{Prezzo}$): premia il driver che garantisce l'estensione richiesta al costo più basso per hertz.
* **Confronto Multi-Design Diretto**:
  * Selezione singola: apertura istantanea in Box Design.
  * Selezione multipla (da 2 a 8 altoparlanti): generazione automatica di schede (*tabs*) parallele in Box Design per il confronto interattivo immediato.
  * Download graduatoria in formato CSV.

---

### 2.2 Box Design (Laboratorio e Simulatore di Carico)
L'ambiente in cui l'ingegnere o l'appassionato scolpisce i dettagli del box.

#### A. Le Topologie Acustiche Supportate (Trattate come "Peers"):
1. **Infinite Baffle (Baffle Infinito / Parete)**:
   * Radiazione posteriore completamente isolata ($V_b \to \infty$).
   * Calcolo dell'escursione libera e del livello massimo indistorto.
2. **Acoustic Suspension / Sealed (Cassa Chiusa)**:
   * Molla d'aria ideale e perdite interne del box ($Q_{abs}, Q_{leak}$).
   * Calcolo automatico della risonanza del sistema montato $F_c$ e del fattore di merito $Q_{tc}$.
3. **Bass Reflex (Cassa Accordata con Condotto)**:
   * Risonatore di Helmholtz con modellazione dettagliata del condotto.
   * Fattori di perdita camera e tubo ($Q_{abs}, Q_{leak}, Q_{port}$).
   * Calcolo delle risonanze d'organo del tubo (pipe resonances) e correzioni d'estremità.
4. **Bass Reflex con Radiatore Passivo (PR)**:
   * Sistema a doppio risonatore senza problemi di turbolenza d'aria.
   * Parametri del PR: area mobile $S_p$, frequenza propria $F_p$, massa mobile $M_{mp}$, $Q_{mp}$, massa aggiunta tarabile in grammi ed escursione massima del passivo $X_{\max,PR}$.
5. **Bandpass 4° Ordine**:
   * Camera posteriore chiusa ($V_s$) + camera anteriore accordata ($V_p, F_p$).
   * Filtraggio acustico passa-banda e protezione del cono a bassissima frequenza.
6. **Bandpass 6° Ordine**:
   * Doppia camera accordata ($V_r, F_r$ posteriore, $V_p, F_p$ anteriore).
   * Elevata efficienza e pendenze asimmetriche.
7. **Bandpass 8° Ordine**:
   * Tripla camera accordata ($V_1, F_1, V_2, F_2, V_3, F_3$) con plenum radiativo finale.
   * Progettazione complessa per sistemi subwoofer ad altissima selettività.
8. **DCCAV (Double Cavity Coupled Asymmetric Reflex)**:
   * Modello esclusivo ad alta complessità analitica: driver montato su una prima camera accordata ($V_h, F_h$), la quale scarica in una seconda camera accordata ($V_l, F_l$) che comunica con l'esterno.
   * Riduzione vistosa dell'escursione del cono su una banda più estesa rispetto al reflex tradizionale e sella d'impedenza asimmetrica caratteristica.
9. *Linee di Trasmissione, MLTL, Tapped Horn e Back-loaded Horn*:
   * Codice e solutore già presenti nel motore fisico (`src/engine.py`), pronti per l'attivazione UI.

#### B. Modulo Driver Elettroacustico & Multi-Driver:
* **T/S Completi**: $F_s, Q_{ts}, Q_{es}, Q_{ms}, R_e, V_{as}, S_d, X_{\max}, P_e, L_e @ 1\text{kHz}, L_e @ 10\text{kHz}, M_{ms}, C_{ms}, Bl$.
* **Panel Air Loading**: correzione fisica per la massa d'aria aggiunta dovuta all'interazione tra pistone e baffle montato (ricalcolo automatico della $F_s$ montata reale).
* **Array Multi-Driver & Isobarico**:
  * Configurazione serie, parallelo o serie/parallelo fino a 8 altoparlanti.
  * Caricamento Isobarico (Compound) fino a 16 unità (dimezzamento del $V_{as}$ equivalente, ideale per box ultracompatti).

#### C. Analisi Grafica e Curve Diagnostiche:
* **Response (SPL)**: curva di risposta complessiva e scomposizione dei contributi (cono vs porte); soglie $F_3, F_6, F_{10}$; marker di accordo; zoom interattivo.
* **Excursion**: andamento dell'escursione dinamica $X(f)$ a confronto diretto con il limite fisico di fabbrica $X_{\max}$.
* **Impedance**: modulo e fase di $Z(f)$; evidenziazione del minimo di impedenza e dei picchi di risonanza per la sicurezza dello stadio finale dell'amplificatore.
* **Ports / Air Velocity**: velocità dell'aria nella gola e nella bocca del condotto in m/s; soglia di turbolenza colorata (allarme se $v_{\text{air}} > 15\text{–}20\text{ m/s}$); calcolo del volume sottratto dal tubo al mobile.
* **Group Delay**: ritardo di gruppo in millisecondi lungo la banda udibile.
* **Atlas 2D**: mappa bidimensionale a gradiente di colore che esplora lo spazio dei parametri (es. variazione volume vs accordo) per testare la robustezza del progetto.
* **Fascia di Tolleranza Monte Carlo**: simulazione stocastica su deviazioni dei parametri T/S (da $\pm 5\%$ a $\pm 15\%$) visualizzando i percentili 5°–95° per verificare come suonerà il box con altoparlanti reali di serie.
* **Pin Response**: funzione memo per fissare a schermo fino a 8 risposte e confrontare al volo le modifiche volumetriche o di accordo.
* **Compare Loads**: commutazione con 1-click tra Sealed, Reflex, DCCAV e Bandpass sullo stesso altoparlante a parità di ingombro.

#### D. Metriche Ingegneristiche di Limite:
* **MIL (Maximum Input Level)**: tensione massima RMS applicabile a ciascuna frequenza prima di rompere il limite termico ($P_e$) o meccanico ($X_{\max}$).
* **MOL (Maximum Output Level)**: massima pressione acustica reale in dB SPL @ 1m generabile al confine del MIL.
* **Forge Score (0–100)**: indice olistico proprietario che penalizza progetti con condotti irrealizzabili, velocità eccessiva, escursione fuori limite o perdite anomale.
* **EBP, VC Corner, Rendimento $\eta_0$ ed Efficienza nominale**.

---

### 2.3 Parametric Port CAD & Stampa 3D (`src/port_cad.py`)
Load Forge trasforma i calcoli acustici in oggetti fisici fabbricabili:
* **Algoritmo a Spessore Normale Costante**: a differenza dei semplici estrusi assiali che assottigliano la parete nelle svasature, calcola il vettore normale $\hat{n}$ su ogni punto del profilo (svasature Aeroport, Hourglass, profili esponenziali), garantendo che la parete stampata mantenga esattamente i millimetri impostati (es. $4.0\text{ mm}$).
* **Blueprint 2D SVG**: disegno tecnico quotato con diametro interno, esterno, svasatura e lunghezza complessiva.
* **Esportazione 3D STL**: file binario watertight (a tenuta stagna) pronto per l'importazione diretta negli slicer per stampanti 3D (Bambu Studio, PrusaSlicer, OrcaSlicer, Cura).

---

### 2.4 Misure Fisiche Reali e Validazione Sperimentale (`src/measurements.py`)
Load Forge non è solo simulazione teorica:
* **Importazione Curve di Laboratorio**: supporta file di misura da **REW (Room EQ Wizard)**, **DATS**, **ARTA**, **CLIO**, **Klippel**, oltre a curve standard `.frd` e `.zma`.
* **Overlay Grafico di Confronto**: sovrappone la curva reale misurata del prototipo alla curva simulata dal motore.
* **Metriche di Discrepanza**: calcolo automatico dell'errore quadratico medio (RMSE in dB) e dello scostamento della frequenza di accordo ($\Delta F_b$ reale vs simulata).

---

### 2.5 Formati di Interscambio, Backup ed Export
* **`.lfp` (Load Forge Project v2)**: formato nativo JSON rigoroso che salva lo stato completo: parametri driver, geometrie box, brief Bass Match, storico candidati calcolati e note di progetto.
* **`.frd`**: file di risposta acustica (frequenza, dB SPL, fase) compatibile con simulatori di crossover (VituixCAD, XSim).
* **`.zma`**: file di impedenza elettrica (frequenza, Ohm, fase elettrica).
* **`.csv`**: esportazione tabellare grezza di tutte le serie di dati simulati.
* **`.afw` & `.crw`**: file di scambio con lo storico software AUDIO for Windows.
* **URL Shareable**: compressione stateless dei parametri direttamente nel link web (`?d=...`).

---

### 2.6 Spazio "Manage Projects", Cloud & Community (`src/saas.py`)
* **Autosalvataggio Reattivo**: scrittura su Google Cloud Firestore con rilevamento ottimistico dei conflitti tra finestre o dispositivi diversi.
* **Controllo Versioni Immutabile**: ogni salvataggio genera una revisione progressiva numerata (`rev_000000000X`). È possibile tornare indietro nel tempo a qualsiasi stato precedente.
* **Cestino con Retention a 30 Giorni**: cancellazione sicura con soft-delete.
* **Community Hub & Explore (`?explore=1`)**:
  * Vetrina pubblica e unlisted per condividere progetti con la community mondiale.
  * Forking con provenienza: clonazione di un progetto pubblico con attribuzione automatica dell'autore originale.
  * Statistiche social: contatore visualizzazioni, like, clonazioni (forks).
  * Classifica "Top Audio Engineers".
  * Allegato foto del prototipo reale o render (ottimizzazione automatica in WebP).
* **Embed Widget (`?p=<id>&embed=1`)**: modalità iframe minimale senza menu, inseribile all'interno di forum (DIYAudio, Reddit) e blog tecnici con grafico interattivo.
* **Generazione Automatica Schede Tecniche**: export Markdown per la stampa e metadati OpenGraph / Schema.org `TechArticle`.

---

## 3. Il Modello di Accounting, Identità e Monetizzazione

Load Forge implementa un'architettura **SaaS Zero-Liability** completa, sicura e scalabile (`src/saas.py` e `src/billing.py`).

### 3.1 Filosofia di Base: Nessun Debito di Responsabilità (Zero-Liability)
1. **Nessuna password nei server di produzione**: autenticazione delegata interamente a provider standard OIDC (Google OIDC / Firebase Auth). Il server riceve un JWT verificato e normalizza l'utente in `SaaSUser(uid, email, name, tenant_id, plan)`.
2. **Nessun dato di pagamento o carta di credito nei database**: tutti i flussi di pagamento, le fatture e la conformità IVA europea sono gestiti da **Stripe Hosted Checkout** e **Stripe Customer Portal**.
3. **Local-First & Privacy Garantita**: gli utenti possono lavorare al 100% offline o in sessione anonima salvando i file `.lfp` sul proprio computer. Il database cloud interviene solo su autenticazione volontaria.

---

### 3.2 Il Concetto di "Crediti di Calcolo" (Monetizzare il Valore, Non la Fisica)
Un principio cardine del modello commerciale è:
> **La fisica di base e la simulazione del singolo box in Box Design sono e rimarranno sempre gratuite e illimitate.** Non si fa pagare la visualizzazione di una curva SPL o l'export di un file STL per una cassa reflex.

**Cosa viene monetizzato? La potenza computazionale massiva e il tempo risparmiato (Bass Match)**:
* Eseguire una scansione su 10.000 altoparlanti con fino a 30 box testati per ciascuno significa risolvere **oltre 6 milioni di sistemi complessi di matrici**. Questo costa CPU, memoria e manutenzione del catalogo.
* Per questo motivo, le ricerche Bass Match consumano crediti:
  * **Run Standard**: 1 credito per candidato analizzato.
  * **Run Deep / Exhaustive**: 2 crediti per candidato analizzato.
* Gli account Amministratore godono di crediti infiniti ($100.000+$ autoricaricati) ed esenzione da qualsiasi blocco di calcolo.

---

### 3.3 Struttura dei Piani (Tiers & Entitlements)

La matrice dei piani configurata a livello applicativo (`PLAN_ENTITLEMENTS`) prevede:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              MATRICE DEI PIANI LOAD FORGE                              │
├─────────────────┬──────────────┬──────────────┬───────────────┬────────────────────────┤
│ Livello (Plan)  │ Prezzo Indic.│ Progetti Cloud│ Crediti / Mese│ Destinazione d'uso     │
├─────────────────┼──────────────┼──────────────┼───────────────┼────────────────────────┤
│ Free            │ 0,00 €       │ Illimitati*  │ 10.000 / mese │ Appassionati DIY,      │
│                 │              │              │               │ studenti, verifiche box│
├─────────────────┼──────────────┼──────────────┼───────────────┼────────────────────────┤
│ Hobby           │ ~5,00 €/mese │ Illimitati*  │ 60.000 / mese │ Costruttori amatoriali │
│                 │              │              │               │ e confronti frequenti  │
├─────────────────┼──────────────┼──────────────┼───────────────┼────────────────────────┤
│ Pro             │ 9,00 €/mese  │ Illimitati*  │ 300.000 / mese│ Installatori pro,      │
│                 │ 79,00 €/anno │              │               │ progettisti diffusori  │
├─────────────────┼──────────────┼──────────────┼───────────────┼────────────────────────┤
│ Team            │ Su misura    │ Illimitati*  │ 1.000.000/mese│ Reparti R&D, aziende,  │
│                 │              │              │ (10 licenze)  │ costruttori conto terzi│
└─────────────────┴──────────────┴──────────────┴───────────────┴────────────────────────┘
* I progetti salvabili sono virtualmente illimitati (ceiling tecnico 999.999).
```

* **Reset Mensile delle Quote**: la quota mensile di crediti si rigenera automaticamente il primo giorno di ogni mese (`quota_reset_at`).
* **Pacchetti Ricarica Crediti Una-Tantum (Credit Packs via Stripe)**:
  Se un utente termina i crediti mensili prima del rinnovo ma deve completare un progetto urgente, può acquistare pacchetti singoli senza cambiare abbonamento:
  * **Starter Pack**: 100.000 crediti a **5,00 €** (ottimo per test mirati).
  * **Popular Pack**: 300.000 crediti a **12,00 €** (scansioni multi-topologia estese).
  * **Power Pack**: 1.000.000 di crediti a **29,00 €** (scansione totale di tutto il catalogo mondiale senza limiti).

---

### 3.4 Meccanismo di Open Beta (Promotional Override)
Nel codice è presente l'interruttore server-side `LOAD_FORGE_OPEN_BETA_ENABLED=true`.
* Consente di offrire la piattaforma in **Open Beta completa** senza barriere di pagamento: chiunque si registri ottiene i privilegi del piano Pro/Full Access.
* Il piano dell'account rimane registrato come `free` nei database, ma l'applicazione applica il profilo Pro a runtime.
* Questo consente di raccogliere feedback e dati di utilizzo reali senza generare complessità contabile prematura, disattivando poi la beta con un semplice flag quando il mercato è pronto per il paywall.

---

### 3.5 Architettura Tecnica del Billing Stripe
Il modulo di fatturazione (`src/billing.py` e il microservizio `webhooks/main.py`) opera con precisione transazionale:
1. **Checkout & Portal**:
   * Chiamata a `create_checkout_session()` $\to$ reindirizzamento al checkout ospitato su Stripe con metadati utente (`uid`, `tier`, `interval`).
   * Chiamata a `create_customer_portal_session()` $\to$ apertura del portale cliente Stripe in cui l'utente può scaricare le fatture Quietanzate, cambiare carta o disdire.
2. **Microservizio Webhook su Cloud Run**:
   * Servizio FastAPI dedicato (`load-forge-webhooks`).
   * Verifica crittografica rigorosa della firma dello stream (`Stripe-Signature` contro `STRIPE_WEBHOOK_SECRET`).
   * Idempotenza garantita tramite la collezione Firestore `stripe_events`: nessun evento viene processato due volte anche in caso di retry di rete.
   * Gestione degli eventi di ciclo di vita:
     * `checkout.session.completed`: creazione abbonamento o accredito crediti da pacchetto ricarica.
     * `customer.subscription.created / updated`: sincronizzazione stato (`active`, `past_due`, `canceled`) ed estensione periodo di validità.
     * `customer.subscription.deleted`: downgrade pulito al piano Free mantenendo tutti i progetti cloud intatti e consultabili.

---

## 4. Inquadramento del Software e Discussione sul Futuro

Per una discussione strategica ad alto livello con stakeholder, investitori o collaboratori tecnici, ecco l'analisi approfondita su punti di forza, criticità attuali e traiettorie future di crescita.

---

### 4.1 I 4 Pilastri di Forza Attuali (L'Asset di Valore)

1. **Unicità dell'Ecosistema Chiuso ma Interoperabile**:  
   Nessun software combina *Misura Hardware reale (DATS)* + *Simulazione Fisica Non Lineare* + *Motore di Ricerca Commerciale* + *CAD per Stampa 3D*. L'utente non deve saltare tra tre programmi diversi e copiare a mano decine di parametri.
2. **Algoritmo di Progettazione Inversa (Bass Match)**:  
   La stragrande maggioranza dei costruttori parte chiedendosi quale altoparlante comprare. Risolvere questo problema in 10 secondi esaminando migliaia di schede tecniche reali crea un valore di risparmio orario immenso per studi di progettazione e makers.
3. **Proprietà Intellettuale & Topologie Uniche (DCCAV)**:  
   La formalizzazione matematica del doppio carico asimmetrico in serie conferisce al software una chiara identità accademica e brevettabile, differenziandolo da qualsiasi simulatore generico open-source.
4. **Resilienza e Portabilità del Dato (Local-First + Cloud)**:  
   Il formato `.lfp` garantisce che l'utente non sia mai tenuto "in ostaggio" dal cloud. Se il server fosse irraggiungibile, i progetti rimangono file JSON validati apribili localmente.

---

### 4.2 Criticità Attuali e Debito Tecnico da Affrontare

1. **Monolite Streamlit (`ui_app.py`)**:
   * Il file principale dell'interfaccia supera i 600 KB di codice Python. Sebbene sia ottimizzato in modo maniacale (frammenti di persistenza, caching di Vega-Lite, pool di worker separati per non bloccare l'UI), Streamlit è nato per prototipazione rapida di data science, non per complesse applicazioni desktop-class multi-finestra.
   * *Problema Cloud Run*: le sessioni WebSocket aperte impediscono al container di "scalare a zero", generando costi fissi di server anche a traffico scarso.
2. **Limiti del Modello Acustico 1D a Parametri Concentrati (Lumped)**:
   * Il motore simula i circuiti acustici come elementi puntiformi ideali. Non calcola:
     * Le onde stazionarie interne tridimensionali (modi del mobile e risonanze di cavità).
     * La flessione strutturale delle pareti in legno (pannelli non perfettamente rigidi).
     * La diffrazione dei bordi del baffle (Edge Diffraction) sulla risposta in frequenza verso le medie frequenze.
3. **Complessità della Governance di Catalogo**:
   * Mantenere aggiornati i prezzi e la disponibilità di 10.000 altoparlanti da decine di siti web richiede una costante manutenzione dei parser contro i cambiamenti di layout HTML dei distributori e blocchi anti-scraping (Cloudflare).

---

### 4.3 Roadmap e Direzioni Future di Sviluppo

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               LOAD FORGE: VISION ROADMAP                               │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ 1. EVOLUZIONE ARCHITETTURA│ 2. MONETIZZAZIONE COMMERC.│ 3. EVOLUZIONE ACUSTICA & AI     │
│ • Disaccoppiamento FastAPI│ • Affiliazioni E-Commerce│ • Diffrazione Baffle & Box FEM  │
│ • Client Mobile Flutter  │ • Configurator B2B Brand │ • Assistente Acustico AI (LLM)  │
│ • Hosting Costo Zero/Fisso│ • Certificazione Hardware│ • Loop Chiuso Z_bench Validation│
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

#### Direzione 1: Disaccoppiamento Headless & Client Nativo Mobile (FastAPI + Flutter)
* **API REST pura (`src/api_app.py`)**: esporre il solutore fisico già perfettamente incapsulato in `src/engine.py` tramite endpoint JSON (`/api/v1/simulate`, `/api/v1/bass-match`, `/api/v1/cad-stl`).
* **App Nativa per Tablet/Smartphone**: un frontend Flutter o React Native per iPad/Android, ideale per tecnici sul campo, installatori car-audio e banchi di officina, con rendering grafico a 120 Hz fluido e zero overhead di rerun.
* **Infrastruttura di Hosting a Costo Minimo**: abbandonare i costi variabili di Google Cloud Run in favore di server a costo fisso imbattibile (es. Hetzner Cloud a ~3,80 €/mese per 2 vCPU / 4 GB RAM o le istanze ARM Always-Free di Oracle Cloud).

#### Direzione 2: Monetizzazione B2B & Affiliazione E-Commerce (Oltre il SaaS)
* **Affiliate Marketing con i Distributori**:
  Ogni volta che un utente clicca sul tasto `Buy` per acquistare il driver vincente trovato da Bass Match su Thomann, SoundImports o Parts Express, Load Forge può incassare una commissione di affiliazione (tipicamente tra il 3% e l'8% sul valore dell'ordine). Con driver che costano tra 80 € e 500 €, questa linea di entrate può superare i ricavi degli abbonamenti SaaS.
* **Widget "Powered by Load Forge" per Produttori (B2B SaaS)**:
  Produttori di rilievo (FaitalPRO, B&C Speakers, Ciare, Dayton Audio, SICA) spendono molte risorse per fornire application notes con box consigliati. Load Forge può vendere ai produttori un configuratore white-label integrabile sul loro sito web aziendale: l'utente finale seleziona l'altoparlante della casa e vede istantaneamente i caricamenti consigliati con logo ufficiale.

#### Direzione 3: Fisica Avanzata (Diffrazione 3D & Correzione del Baffle)
* Integrare un modulo analitico di diffrazione del bordo del pannello frontale (basato su formulazioni di Rayleigh-Sommerfeld o simulazione a dischi/edge). Questo permetterà di prevedere sia la risposta in cassa sul semispazio $2\pi$ sia l'irradiazione reale nello spazio aperto $4\pi$, rendendo Load Forge un concorrente diretto e completo dei software di simulazione globale.

#### Direzione 4: L'Assistente Acustico AI Integrato (Intelligenza Diagnostica)
* Implementare un agente AI specializzato in acustica che analizzi l'allineamento generato evidenziando criticità e suggerendo correzioni:
  * *"Attenzione: il condotto scelto presenta una risonanza di tubo a 380 Hz a soli -12 dB di attenuazione. Se intendi incrociare questo woofer a 400 Hz con un crossover a 12 dB/ottava, la risonanza del condotto sarà chiaramente udibile. Si consiglia di ridurre il diametro a 7 cm o prevedere una camera a labirinto."*
  * *"La bobina mostra un valore di $L_e$ elevato ($2.4\text{ mH}$); il polo induttivo a 530 Hz attenuerà le frequenze vocali. Considera una cella di compensazione di Zobel."*

#### Direzione 5: Il Loop Chiuso Sperimentale "Digital Twin Acustico"
* Completare il ponte bidirezionale con la scheda DATS/Z_bench:
  1. Si misura il driver grezzo appena estratto dalla scatola con DATS $\to$ T/S reali.
  2. Load Forge adatta istantaneamente il progetto del box ai T/S misurati.
  3. Si invia il file STL del condotto alla stampante 3D.
  4. Si assembla il prototipo e si misura l'impedenza del mobile finito con DATS.
  5. Load Forge confronta la curva simulata con la misura reale, calcola i litri effettivi e il fattore di smorzamento delle fibre assorbenti, memorizzando il modello corretto per la produzione in serie.

---

## 5. Tabella Riepilogativa di Sintesi

| Aspetto | Stato Attuale (v0.16.7) | Visione Futura Proposta |
|---|---|---|
| **Interfaccia Utente** | Streamlit Web (Dark Cyber, Plotly, Vega-Lite) | Webapp PWA + App Nativa Flutter per tablet/mobile |
| **Architettura Backend** | Monolite Python modulare + microservizi webhook | Headless API FastAPI su Hetzner / Oracle Free |
| **Calcolo Acustico** | Lumped parameters 1D + Limiti Non Lineari (MIL/MOL) | Lumped 1D + Diffrazione Baffle 2D/3D + Analisi Modi Box |
| **Carichi Supportati** | Sealed, Reflex, PR, BP4, BP6, BP8, DCCAV, IB | Attivazione UI per Linee di Trasmissione, Horn e Karlson |
| **Ottimizzazione** | Bass Match algoritmico su 10.000+ driver | Bass Match + Suggeritore Acustico con AI (LLM diagnostico) |
| **CAD & Manifattura** | Port CAD parametrico con STL uniforme e blueprint SVG | Generatore completo Box in pannelli DXF per taglio legno CNC |
| **Modello Account** | OIDC Zero-Liability, Firestore, multi-tenant | SSO unificato, profili studio/team con ruoli e permessi |
| **Monetizzazione** | Piani Free/Pro/Team + Pacchetti Crediti Stripe | Abbonamenti SaaS + Commissioni di affiliazione distributori |
| **Hardware** | Bridge Z_bench verso Dayton Audio DATS V3 | Suite integrata di misura e validazione loop-chiuso |

---

*Questo documento costituisce la base di allineamento per le future decisioni architetturali, commerciali e di sviluppo della suite Load Forge.*
