# Load Forge — manuale funzionale completo

Questo manuale descrive le funzioni operative di Load Forge, il significato dei
parametri e il modo in cui usarli durante selezione del trasduttore,
pre-progetto, ottimizzazione, verifica e finalizzazione del diffusore. I valori
calcolati sono strumenti di progetto: prima della costruzione vanno sempre
confrontati con datasheet ufficiale, ingombri reali, volume lordo/netto,
materiali, tolleranze e misura del prototipo.

Ambito della presente edizione:

- applicazione **Load Forge 0.11.0**;
- formato progetto **LFP v2**;
- catalogo proprietario con versione indipendente **1.0.0**.

La versione dell'app identifica interfaccia e motore; quella del catalogo
identifica i dati. Un aggiornamento del catalogo non implica quindi una nuova
versione del software e viceversa.

## 1. Struttura del software

L'app ha due ambienti principali:

1. **Bass Match** risponde alla domanda “quale driver e quale carico soddisfano
   meglio questo brief?”. Applica filtri parametrici, elimina a priori i
   candidati impossibili, simula quelli rimasti e li ordina.
2. **Box Design** risponde alla domanda “come si comporta questo driver in
   questo specifico carico e con questi parametri?”. Consente ottimizzazione,
   modifica manuale, analisi grafica, confronto ed export.

Il menu **Project** salva e ripristina driver, brief Bass Match, carico, box,
grafici e risultati. Il selettore di workspace consente di passare dalla
ricerca alla progettazione senza perdere lo stato.

### 1.1 Accesso e modalità operative

L'installazione può funzionare senza autenticazione, con account locali oppure
con Single Sign-On OIDC. Quando l'accesso è attivo:

- **Create account / Sign in** crea o apre l'identità abilitata;
- il profilo mostra nome, email e piano/abilitazioni correnti;
- **Sign out** chiude la sessione, non cancella file LFP o cataloghi;
- l'Open Beta può esporre tutte le funzioni anche se alcune sono marcate Pro.

Le due grandi schede **Bass Match** e **Box Design** sono workspace, non
progetti separati. Lo stato passa dall'una all'altra; la simulazione massiva
parte solo premendo **Run Bass Match**.

## 2. Flusso consigliato di un progetto

### Fase A — definire il brief

- scegliere uno o più carichi in Bass Match;
- impostare volume massimo realmente disponibile;
- definire banda utile, F3 massima, SPL/MOL richiesti e tensione;
- impostare ripple, escursione e ritardo soltanto quando sono requisiti reali;
- filtrare provenienza, produttore, diametro, classe e prezzo.

### Fase B — preselezionare il driver

- eseguire Bass Match;
- confrontare F3, volume, ripple, MOL a F3, impedenza minima, prezzo e classe;
- non scegliere soltanto la prima riga: confrontare almeno 3–5 candidati e
  verificare disponibilità, dimensioni meccaniche e fonte T/S;
- aprire i candidati promettenti in Box Design.

### Fase C — progettare il box

- scegliere **Max extension**, **Balanced** o **Flattest** come punto di
  partenza;
- fissare i vincoli di costruibilità;
- passare a **Manual** per modificare volume, accordi, perdite e radiatore;
- verificare risposta, escursione, impedenza, velocità nei condotti e ritardo.

### Fase D — robustezza e finalizzazione

- attivare la fascia di tolleranza T/S;
- confrontare carichi a volume simile e fissare (“Pin”) le risposte migliori;
- controllare F3/F6/F10, MOL/MIL, minimo d'impedenza e risonanze dei condotti;
- sottrarre dal volume lordo driver, condotti, rinforzi e radiatore;
- esportare CSV/FRD/ZMA e validare con misura o software esterno.

## 3. Bass Match parametrico

Bass Match non cerca un nome: costruisce lo stesso problema parametrico per
ogni driver ammesso, genera un box coerente per ogni carico selezionato,
simula e ordina i risultati. Il conteggio iniziale distingue:

- **Pre-qualified**: driver che superano i controlli economici prima della
  simulazione per almeno un carico;
- **Ready simulations**: combinazioni driver × carico che verranno realmente
  calcolate;
- **Skipped a priori**: combinazioni eliminate per dati mancanti o vincoli
  certamente non raggiungibili;
- **Duplicates removed**: righe equivalenti collassate prima della ricerca.

### 3.1 Load type

Si possono selezionare più carichi contemporaneamente. La ricerca valuta ogni
driver su ciascun carico attivo e conserva la soluzione migliore per il brief.

| Carico | Quando usarlo nella selezione |
|---|---|
| Infinite baffle | porta, parete, baffle molto grande o installazione con onda posteriore completamente isolata; nessun volume/accordo |
| Sealed | priorità a semplicità, transitorio, protezione del cono e roll-off regolare |
| Bass reflex | efficienza ed estensione con un volume moderato; richiede verifica rigorosa del condotto |
| Bass reflex con passive radiator | quando il condotto sarebbe troppo lungo o rumoroso; richiede area, massa, Qmp ed escursione del PR |
| Bandpass 4th order | banda limitata, filtraggio acustico e buon controllo sotto banda con una camera chiusa |
| Bandpass 6th order | maggiore efficienza/banda regolabile, con due camere accordate e maggiore sensibilità agli errori |
| Bandpass 8th order | tre volumi e tre risonatori per controllo avanzato della banda; costruzione e taratura complesse |
| DCCAV | doppia cavità asimmetrica per modellare due accordi e l'estensione con forte interazione fra volumi/porte |

### 3.2 Performance filters

| Controllo | Significato | Uso pratico |
|---|---|---|
| Maximum F3 | esclude progetti con frequenza a −3 dB superiore al limite | fissare il limite di estensione richiesto, non una frequenza “ideale” arbitraria |
| Minimum MOL at F3 | livello massimo ottenibile a F3 rispettando escursione e potenza termica | utile per subwoofer che devono mantenere output proprio all'estremo inferiore |
| Minimum SPL | minimo picco SPL simulato alla tensione scelta | preselezione di sensibilità/output; non sostituisce MOL |
| Optimization goal | obiettivo usato per generare ogni box | mantenere lo stesso obiettivo per confronti equi |
| Allowed response ripple | massima variazione picco-valle nella banda valutata | 1–3 dB per risposta controllata; valori più alti ammettono allineamenti più aggressivi |
| Ripple frequency ceiling | ignora il ripple sopra una frequenza scelta | per un subwoofer impostare tipicamente il limite della banda che verrà realmente usata, per esempio 70–100 Hz |
| Maximum excursion | massimo rapporto fra corsa calcolata e Xmax pubblicato | 1,0 resta entro Xmax; 0 disattiva; candidati senza Xmax non possono offrire una verifica completa |
| Maximum group delay | limite al ritardo di gruppo nella banda LF | usarlo se il transitorio/integrazione è un requisito; limiti troppo rigidi eliminano box profondi |
| Maximum Mms | massa mobile massima pubblicata | limita inerzia e indirizza verso driver più leggeri; con filtro attivo i dati Mms mancanti vengono esclusi |
| Maximum Le | induttanza nominale/1 kHz massima | evita forte roll-off induttivo e perdita di banda alta; Le10k non viene sostituita a Le |
| Evaluation range start/end | estremi della banda simulata e valutata | comprendere tutta la banda utile senza far pesare regioni estranee al progetto |
| Simulation resolution | numero di punti in frequenza | aumentare per controlli finali/risonanze strette; ridurre per scansioni rapide |
| Reset Finder defaults | ripristina il profilo pratico iniziale | utile quando vincoli accumulati rendono vuota la ricerca |

**Optimization goal** ha tre modalità:

- **Max extension** privilegia la F3 più bassa entro i vincoli;
- **Balanced** bilancia estensione, regolarità e praticità del box;
- **Flattest** privilegia il passband più regolare, anche sacrificando volume o
  estensione.

### 3.3 Library filters

| Filtro | Funzione |
|---|---|
| Search preset | cerca produttore o part number |
| Provenance | limita il catalogo sorgente; “Load Forge database” indica il catalogo proprietario |
| Manufacturer | seleziona uno o più marchi; vuoto significa tutti |
| Size | diametro nominale/classe dimensionale |
| Class | subwoofer, woofer/midbass o altra classe ricavata dalla banda utile |
| Price currency | valuta di confronto; i prezzi vengono normalizzati con tassi ECB quando disponibili |
| Filter by max price | applica un tetto al prezzo normalizzato; i record senza prezzo non possono dimostrare di rispettarlo |
| Candidate pool | nessuna selezione usa tutti i filtrati; una selezione multipla limita il prossimo run ai soli driver scelti |

### 3.4 Lettura della tabella risultati

Le colonne principali sono:

- **Driver, Load, Config**: identità, topologia e configurazione multi-driver;
- **Nominal/Size**: dimensioni nominali dichiarate; classe e area mobile restano
  disponibili nei filtri e nei dati interni, ma sono nascoste nella tabella
  compatta;
- **Fs, Qts, Vas**: nucleo T/S usato nell'allineamento;
- **F3, Ripple, Peak SPL**: estensione e forma della risposta alla tensione di
  confronto;
- **MOL**: output massimo fisicamente sostenibile a F3;
- **Min impedance**: carico minimo visto dall'amplificatore;
- **Vb/Vtot e accordi**: volume netto e frequenze del box proposto;
- **Mms, Le/Le10k**: indicatori di massa e banda elettrica;
- **Price/CUR/Value**: costo, valuta abbreviata e rapporto fra
  prestazioni/costo quando disponibile.

Un risultato Bass Match diventa un progetto editabile aprendolo in Box Design.
Le condizioni del brief rimangono associate al risultato; se un filtro cambia,
l'app segnala che occorre rieseguire la ricerca.

Se sono presenti prezzi, **Rank by F3** mantiene la graduatoria acustica mentre
**Best value** ordina per il prodotto F3 × prezzo: un valore minore rappresenta
il modo economicamente più conveniente di raggiungere una certa estensione,
non la qualità assoluta del driver. **Download candidate CSV** esporta la
tabella. Selezionando una riga la si apre in Box Design; selezionando da due a
otto righe si creano varianti confrontabili e indipendentemente editabili.

Il pannello **Candidate pool** è il catalogo filtrato sottostante. Nessuna
selezione significa “simula tutti i driver ammessi”; una selezione multipla
limita il run. Per mantenere reattiva l'interfaccia, con migliaia di candidati
la tabella visualizza al massimo le prime 500 righe: ricerca e filtri agiscono
comunque sull'intero insieme.

### 3.5 Quante simulazioni esegue davvero Bass Match

Il numero **Ready simulations** non indica il numero di box provati
internamente. Indica i *job* ammessi dopo la preselezione:

$$N_{\text{job}}=\sum_{c\in\text{carichi}}N_{\text{driver ammessi per }c}$$

Con un solo carico, 5.087 Ready simulations significano quindi 5.087 driver
da valutare su quel carico. Con due carichi, lo stesso driver può produrre due
job distinti. Ogni job viene eseguito indipendentemente e nessun driver viene
saltato perché non appartiene a una Top-K preliminare.

Per ciascun job ottimizzato, Bass Match usa questo budget:

1. fino a **30 allineamenti di box** sul runtime normale, oppure 24 su Cloud
   Run (`K_SERVICE`);
2. ogni allineamento provvisorio è simulato su **30 frequenze**; se è attivo
   il Ripple frequency ceiling diventano 30 punti sotto il limite più 9 sopra,
   con il punto di separazione condiviso, quindi normalmente 38;
3. il solo box vincente viene ricalcolato sulla griglia larga e con **20 punti
   locali** aggiuntivi attorno alla F3;
4. il box vincente viene infine simulato sulla risoluzione scelta dall'utente,
   normalmente **240 punti**; il servizio Cloud limita questa fase a 80 punti.
   Anche qui il ceiling attivo aggiunge la coda sparsa sopra il limite.

Il limite di 30/24 è un massimo globale per quel job, non “30 prove per ogni
parametro”. L'ottimizzatore può terminare prima quando il passo di ricerca è
già sceso sotto la soglia. I carichi usano i seguenti parametri liberi:

| Carico | Parametri cercati | Prove di box per driver |
|---|---|---:|
| Infinite baffle | nessuno | 0; una sola risposta finale |
| Sealed | volume Vb | fino a 30/24 |
| Bass reflex a condotto | volume Vb e accordo Fb | fino a 30/24 |
| Bass reflex con passive radiator | starter fisico Vb, area/massa/Q/Xmax del PR | 0; una sola risposta finale |
| Bandpass 4th order | Vs, Vp, Fp | fino a 30/24 |
| Bandpass 6th order | Vr, Fr, Vp, Fp | fino a 30/24 |
| Bandpass 8th order | V1, F1, V2, F2, V3, F3 | fino a 30/24 |
| DCCAV | Vh, Vl, Fl e rapporto Fh/Fl | fino a 30/24 |

Il budget è uguale per topologia, non proporzionale al numero di variabili.
Di conseguenza Sealed esplora un solo asse con 30 tentativi, mentre DCCAV ne
distribuisce al massimo 30 su quattro assi e Bandpass 8th order su sei: è una
scelta orientata alla velocità del catalogo, ma rende la ricerca dei carichi
più complessi meno fitta rispetto a quella della cassa chiusa.

Esempio riferito a **5.087 job DCCAV Ready**, 240 punti finali, runtime normale
e Ripple frequency ceiling disattivato. Nel caso massimo il run può effettuare:

- $5.087\times30=152.610$ allineamenti provvisori;
- $152.610\times30=4.578.300$ soluzioni box-frequenza nella ricerca;
- $5.087\times(30+20)=254.350$ punti per ricontrollare e raffinare i vincitori;
- $5.087\times240=1.220.880$ punti per le curve finali.

Il totale massimo ordinario è quindi circa **6,05 milioni di soluzioni
box-frequenza**, non 5.087 sole prove. Può essere inferiore per convergenza
anticipata; un DCCAV che non supera il controllo di credibilità dopo il
refinement può richiedere fino a tre correzioni aggiuntive dell'accordo.

### 3.6 Strategia con cui sceglie il box vincente

La ricerca è deterministica e avviene nello spazio logaritmico: modificare un
volume o un accordo equivale così a esplorare variazioni percentuali, non
incrementi assoluti. Si parte dall'allineamento suggerito per il driver e il
carico; con **Max extension** e DCCAV viene considerato anche un punto di
partenza a camere più grandi. Se il punto iniziale non è costruibile vengono
provati riavvii deterministici al 75%, 25% e 50% della diagonale dello spazio
ammesso.

Il *compass search* usa inizialmente un passo logaritmico di 0,4. Per ogni asse
prova la direzione positiva e negativa, accetta soltanto uno score migliore e,
quando nessuna direzione migliora, dimezza il passo. Si ferma sotto 0,02 o al
raggiungimento del budget di 30/24 valutazioni. Non usa casualità: stesso
driver, stesso brief e stessa versione del motore producono la stessa scelta.

Prima del confronto dello score vengono applicate barriere di costruibilità:

- F3 e simulazione devono essere valide;
- il condotto richiesto non può superare il 95% del limite geometrico di 60 cm;
- il condotto non può occupare oltre il 10% della camera accordata né essere
  più lungo della dimensione interna utile;
- il DCCAV deve rispettare il rapporto minimo di credibilità fra F3 e Fl;
- il bandpass deve produrre una banda passante valida.

Fra i box costruibili vince lo score numericamente più basso. Le pesature
principali sono:

| Obiettivo | Peso F3 | Peso ripple | Effetto pratico |
|---|---:|---:|---|
| Max extension | 1,00 | 0,15 | fa dominare la discesa; le penalità consultive di escursione e group delay sono attenuate, ma i limiti costruttivi restano rigidi |
| Balanced | 0,55 | 0,55 | compromesso equivalente fra estensione e regolarità |
| Flattest | 0,20 | 1,10 | privilegia nettamente la risposta uniforme |

Lo score comprende anche il superamento del ripple richiesto, escursione,
group delay, SPL minimo e una piccola regolarizzazione del volume. Se è
impostata una Target F3, una volta raggiunta l'estensione richiesta cresce la
preferenza per il box più piccolo: non vengono premiati litri che non servono.

### 3.7 Come confronta i driver dopo avere scelto i box

La scelta avviene su due livelli distinti:

1. **dentro ogni job driver × carico**, lo score dell'ottimizzatore sceglie il
   box migliore per quel solo driver;
2. **fra i risultati finali**, vengono applicati i filtri richiesti e le righe
   sono ordinate per F3 crescente, poi F6, F10 e infine Peak SPL decrescente
   come spareggio.

Con **Best value** l'ordinamento principale diventa F3 × prezzo normalizzato;
le righe senza prezzo restano disponibili ma non possono vincere il confronto
economico. Non esiste oggi una selezione Top-K globale prima del refinement:
ogni combinazione Ready riceve la propria ricerca coarse, il refinement del
proprio box vincente e la simulazione finale.

## 4. Box Design — Driver

### 4.1 Preset, ricerca e acquisto

**Search preset** restringe il menu. **Driver preset** carica T/S, fonte,
prezzo, URL e dati meccanici. Il link **Buy** è informativo e non sostituisce la
verifica della variante d'impedenza. **Mechanical drawing** riporta, quando
pubblicati, diametro esterno, foro, profondità, circonferenza fori e peso.

Il preset **Custom** abilita l'inserimento manuale. I parametri minimi devono
essere coerenti; in particolare deve valere Qms > Qts perché Qes sia fisico.

### 4.2 Parametri Thiele/Small

| Parametro | Significato | Effetto progettuale |
|---|---|---|
| Fs (Hz) | risonanza libera del driver | influenza il limite inferiore; non basta da sola a prevedere la F3 |
| Qts | smorzamento totale a Fs | basso Qts tende a favorire carichi accordati; alto Qts sealed/IB, con molte eccezioni |
| Qms | qualità meccanica | insieme a Qts permette di ricavare Qes; influenza le perdite meccaniche |
| Qes | qualità elettrica derivata o pubblicata | usata per EBP e comportamento elettromeccanico |
| Re (Ω) | resistenza DC della bobina | determina corrente e parte elettrica dell'impedenza; non è l'impedenza nominale |
| Vas (L) | volume d'aria con cedevolezza equivalente | scala fortemente il volume del box; Vas elevato non significa automaticamente “bassi migliori” |
| Sd (cm²) | area efficace del pistone | determina volume spostato, sensibilità e accoppiamento acustico |
| Piston diameter | alternativa geometrica a Sd | l'app converte il diametro efficace in area; non usare automaticamente il diametro esterno del cestello |
| Xmax (mm) | corsa lineare monodirezionale | limita l'output meccanico; controllare la definizione adottata dal produttore |
| Pe (W) | potenza termica ammessa | limita l'output termico/MIL; non garantisce che Xmax non venga superato |
| Le (mH) | induttanza bobina nominale/1 kHz | aumenta impedenza e roll-off alle frequenze superiori |
| Le10k (mH) | induttanza riportata a 10 kHz | solo informativa nell'app, non sostituisce Le nella simulazione |
| Mms (g) | massa mobile totale | influenza Fs, efficienza e inerzia; se assente può essere ricavata dal set coerente |
| Cms (mm/N) | cedevolezza sospensione | Cms alta = sospensione più cedevole |
| Bl (T·m) | fattore di forza | misura l'accoppiamento motore-bobina; entra in sensibilità e controllo |

### 4.3 Panel air loading

**Panel air loading** aggiunge la quota di massa d'aria accoppiata al pistone
montato su pannello. **Panel coupling** va da 0 (nessuna correzione) a 1
(correzione completa del modello). L'app mostra massa aggiunta e Fs montata.
Serve a evitare che una Fs libera venga trattata come identica alla condizione
montata; non sostituisce una misura reale sul baffle definitivo.

### 4.4 Driver configuration

La configurazione applica serie/parallelo e array identici fino a otto driver,
oltre ad array isobarici fino a sedici unità. L'app aggiorna il T/S composito:
Sd radiativa, Vas, Re e Pe. In un isobarico una coppia usa due motori ma un solo
pistone radiativo e circa metà Vas di un singolo driver; offre volume ridotto a
costo di efficienza, costo e complessità.

## 5. Box Design — strategia e pilotaggio

### 5.1 Box strategy

- **Max extension**, **Balanced**, **Flattest** rieseguono automaticamente
  l'ottimizzatore quando cambiano driver, carico o vincoli;
- **Manual** ripristina/consente i valori modificati a mano;
- **Infinite baffle** non ha una strategia box.

### 5.2 Vincoli dell'ottimizzatore

| Parametro | Uso |
|---|---|
| Max total volume | limite sul volume netto totale delle camere; 0 disattiva |
| Max ripple | limite passband picco-valle |
| Ripple ceiling | frequenza massima entro cui il ripple conta |
| Excursion limit | rapporto massimo escursione/Xmax |
| Target F3 | cerca una F3 specifica; 0 chiede la più bassa compatibile |
| Max group delay | limite al ritardo LF |

L'ottimizzatore impone anche costruibilità dei condotti: diametro minimo,
lunghezza positiva, frazione di volume occupata e lunghezza compatibile con il
box. Se non trova una soluzione costruibile, l'app mantiene uno starter e
mostra l'errore.

### 5.3 Voltage e Series R

**Voltage** è la tensione RMS applicata. Per una resistenza puramente nominale
8 Ω, 2,83 V corrispondono circa a 1 W; su 4 Ω sono circa 2 W. L'impedenza del
driver varia con la frequenza, quindi la potenza reale non è costante.

**Series R** rappresenta resistenza d'uscita amplificatore, cavo e DCR della
bobina del crossover. Aumenta smorzamento elettrico apparente, riduce tensione
al driver e può cambiare risposta/accordo. Bass Match e ottimizzatore ordinano
invece a 0 Ω per confronti uniformi; la resistenza va verificata nel progetto
finale.

## 6. Parametri delle topologie

Tutti i volumi sono **netti acustici**. Per il volume interno lordo aggiungere
spostamento di driver, condotti, radiatori, rinforzi e componenti.

### 6.1 Infinite baffle

Nessun volume o accordo. Il modello assume onda posteriore completamente
isolata da quella anteriore. Va usato per pareti/porte/baffle realmente grandi
rispetto alla cedevolezza del driver; una piccola cassa non è un infinite
baffle.

### 6.2 Sealed

- **Vb sealed**: volume netto chiuso;
- **Fc**: risonanza del sistema montato;
- **Qtc**: smorzamento totale del sistema;
- **Qabs sealed**: perdite per assorbimento interno;
- **Qleak sealed**: perdite per fughe.

Qtc intorno a 0,7 è un riferimento classico di compromesso, non una regola
universale. Qtc più basso tende a risposta più smorzata e box grande; più alto
a maggiore enfasi/ring e box piccolo.

### 6.3 Bass reflex con condotto

- **Vb**: volume netto della camera;
- **Fb**: accordo di Helmholtz;
- **Qabs, Qleak, Qport**: perdite di assorbimento, tenuta e condotto;
- geometria del condotto: diametro/area, lunghezza, velocità, volume occupato,
  prima risonanza di tubo.

Sotto Fb l'escursione cresce rapidamente: controllare sempre Excursion e MOL.
Un diametro maggiore riduce la velocità ma richiede maggiore lunghezza e volume.

### 6.4 Bass reflex con radiatore passivo

- **Sp**: area efficace del radiatore;
- **Fp**: risonanza libera del PR;
- **Qmp**: qualità meccanica;
- **Mmp**: massa mobile;
- **Added mass**: massa aggiunta, che abbassa la Fs effettiva a Cms costante;
- **PR Xmax**: corsa del radiatore, spesso superiore a quella del driver.

Il PR evita rumore e lunghezze estreme del condotto ma può raggiungere la sua
corsa prima del driver. L'app mostra Fp effettiva e stima dell'accordo box+PR.

### 6.5 Bandpass 4th order

- **Vs**: camera posteriore chiusa;
- **Vp**: camera anteriore accordata;
- **Fp**: accordo anteriore;
- perdite separate per camera chiusa, camera accordata e porta.

La camera chiusa controlla il cono sotto banda; la camera accordata determina
gran parte della banda passante. È adatto quando la banda utile è nota e il
filtraggio acustico è desiderato.

### 6.6 Bandpass 6th order

- **Vr/Fr**: volume e accordo posteriori;
- **Vp/Fp**: volume e accordo anteriori;
- Qabs/Qleak/Qport separati sui due risonatori.

I due accordi definiscono estremi e forma della banda. Piccoli errori di volume,
porta o perdite possono produrre grandi variazioni: usare tolleranze e
prototipazione.

### 6.7 Bandpass 8th order

- **V1/F1**: camera/porta anteriore;
- **V2/F2**: camera/porta posteriore;
- **V3/F3**: plenum/porta radiativa;
- Qabs/Qleak/Qport indipendenti per le tre sezioni.

Offre molti gradi di libertà ma richiede controllo rigoroso di volume totale,
porte, impedenza, ritardo e sensibilità alle tolleranze.

### 6.8 DCCAV

- **Vh/fh**: volume e accordo superiori;
- **Vl/fl**: volume e accordo inferiori;
- perdite Qabs/Qleak/Qport indipendenti;
- volume totale Vh+Vl e due geometrie di porta.

I due accordi non vanno trattati come due reflex indipendenti: camere e porte
formano un unico circuito acustico. La modifica di un volume o accordo altera
entrambi i contributi, l'escursione e l'impedenza.

### 6.9 Significato dei fattori di perdita

Un Q più alto rappresenta perdite minori/risonanza più netta; un Q più basso
maggiore dissipazione. **Qabs** descrive assorbimento, **Qleak** tenuta del box,
**Qport** perdite viscose/turbolente del risonatore. Non usare valori estremi
per “aggiustare” la curva: se non sono misurati, mantenere i default e verificare
la sensibilità.

### 6.10 Topologie disponibili nel motore ma non nell'interfaccia principale

Il motore contiene anche transmission line uniforme/segmentata, MLTL,
quarter-wave, back-loaded horn e tapped horn. Sono API tecniche validate dai
test ma non compaiono oggi tra le sette schede operative di Bass Match/Box
Design. Non vanno quindi descritte come funzioni UI già utilizzabili; richiedono
un futuro contratto completo di controlli, preset, grafici e test d'interfaccia.

## 7. Grafici e analisi

### 7.1 Response

Mostra SPL totale e, quando disponibili, contributi driver/porte. Le soglie
**F3, F6, F10** sono i primi attraversamenti coerenti a −3/−6/−10 dB rispetto
al riferimento della banda. Il cursore consente un marker; lo slider cambia
solo lo zoom, non la banda simulata.

- **Compare loads** sovrappone topologie a volume comparabile;
- **Tolerance band** esegue Monte Carlo sui T/S e mostra percentili 5–95;
- **T/S tolerance** controlla l'ampiezza percentuale della variazione;
- **Tuning markers** mostra gli accordi;
- **Pin response** conserva fino a otto curve durante le modifiche;
- **Reset zoom/Clear pins** ripristinano la vista.

### 7.2 Excursion

Mostra corsa del cono contro frequenza e linea Xmax. È essenziale sotto gli
accordi e alle alte tensioni. Una risposta SPL regolare non implica escursione
sicura.

### 7.3 Impedance

Mostra modulo e fase del carico elettrico. Controllare minimo d'impedenza,
picchi di risonanza e compatibilità con amplificatore/crossover. Re non è il
minimo d'impedenza in uso.

### 7.4 Ports / passive radiator

Per ogni porta riporta accordo, diametro, lunghezza, velocità di picco, volume
occupato e risonanza del tubo. La linea guida di velocità segnala rischio di
compressione/chuffing ma geometria delle estremità e potenza musicale restano
responsabilità del progettista. Con PR viene mostrata la corsa del radiatore.

### 7.5 Group Delay

È la derivata della fase rispetto alla frequenza e indica ritardo energetico.
Va letto nella banda effettivamente riprodotta: valori grandi molto sotto il
passband possono essere irrilevanti se filtrati.

### 7.6 Atlas

Mappa lo spazio di progetto variando coppie di parametri del box e mostrando
metriche come F3/ripple. Serve a capire robustezza, compromessi e vicinanza a
regioni sensibili, non soltanto a trovare un singolo optimum.

## 8. Metriche, limiti e indicatori

| Metrica | Interpretazione |
|---|---|
| F3/F6/F10 | estensione ai tre livelli di attenuazione |
| Peak LF SPL | massimo livello nella finestra simulata alla tensione impostata |
| Max excursion | massima corsa calcolata del driver |
| MIL | maximum input level: limite d'ingresso imposto da potenza/escursione |
| MOL | maximum output level: SPL massimo risultante dai limiti fisici |
| MOL @ F3 | headroom disponibile esattamente alla frequenza di estensione |
| Min impedance | punto più impegnativo per l'amplificatore |
| Z peaks | frequenze dei principali picchi d'impedenza |
| Eta0/SPL 1W/SPL 2.83V | riferimenti di efficienza/sensibilità derivati |
| EBP = Fs/Qes | indicatore classico: <50 sealed/IB, >100 ported, zona 50–100 mista; non è una regola assoluta |
| VC corner | Re/(2πLe), indicatore del limite induttivo della bobina |
| Forge Score | indice euristico 0–100 che sottrae punti per warning, escursione e porte impratiche; non è una misura fisica né un criterio unico di scelta |

I badge (porta entro linea guida, F3 sotto una soglia, model checks passed)
sono scorciatoie visive. Non sostituiscono l'analisi delle curve.

## 9. Confronto e gestione delle varianti

- **Compare loads** confronta topologie sullo stesso driver;
- **Pin response** conserva curve mentre si cambiano parametri;
- i **design tabs** consentono varianti editabili senza perdere l'originale;
- la gestione dei pin permette rinomina/rimozione;
- selezionando più risultati Bass Match si apre un confronto coerente nel
  workspace di progetto.

Per confronti corretti mantenere uguali tensione, resistenza serie, banda,
risoluzione e definizione del volume netto.

## 10. Project

Il menu progetto gestisce:

- **Project name**: nome usato nel file esportato;
- **Download .lfp**: salva driver, carico, box, controlli Bass Match e risultati
  della ricerca;
- **Open .lfp project or CRW driver**: importa un progetto LFP/JSON oppure i
  T/S di un driver CRW;
- **Restore previous design**: annulla l'ultimo caricamento di preset,
  progetto o link condiviso quando esiste uno snapshot precedente;
- **New / Reset design**: azzera lo stato del progetto e ripristina i default;
- **Share via URL**: comprime i parametri del design nel parametro `d` del
  link; **Clear share link** lo rimuove dall'URL.

Nessuna di queste azioni elimina righe del catalogo. **New / Reset design**
agisce soltanto sulla sessione corrente; un file LFP già scaricato resta
disponibile. Le schede di confronto hanno azioni distinte: duplica, mostra/
nascondi, prepara download CRW e chiudi la variante.

## 11. Export

- **CSV**: frequenza e serie numeriche della simulazione per analisi generica;
- **FRD**: frequenza/SPL/fase per VituixCAD, XSim, REW e strumenti compatibili;
- **ZMA**: frequenza/modulo/fase dell'impedenza;
- **AFW** (DCCAV): progetto AUDIO for Windows derivato da template verificato;
  i campi geometrici delle porte ereditati dal template non rappresentano
  automaticamente le dimensioni reali del progetto corrente;
- **CRW**: driver della variante attiva, utile per scambio con AUDIO for
  Windows e strumenti compatibili;
- **LFP**: progetto Load Forge completo e ricaricabile;
- **Candidate CSV**: graduatoria Bass Match senza le sparkline grafiche.

## 12. Cataloghi, prezzi e provenienza

L'app mantiene distinti catalogo proprietario e sorgenti esterne. Il loader
valida fisica e identità, quindi il numero di righe JSON può essere superiore
al numero di preset utilizzabili mostrati nell'app a causa di deduplicazione,
record incompleti o conflitti.

La provenienza deve essere letta così:

- produttore/datasheet ufficiale: fonte tecnica primaria;
- retailer autorizzato/specializzato: prezzo, disponibilità e scoperta modello;
- database esterno: fonte opzionale separata, non automaticamente “proprietaria”.

Il prezzo è associato a marca, modello e variante d'impedenza con un livello di
confidenza. Prima dell'acquisto verificare SKU e valuta sul link originale.

### 12.1 Catalog Maintenance amministrativa

La vista protetta **Catalog Maintenance** è separata dall'uso normale. Consente
all'amministratore di scegliere catalogo, cercare, correggere identità, Xmax,
Pmax, Le, prezzo, valuta, link e disponibilità, duplicare o eliminare record,
scaricare un backup JSON e ripristinarlo. I campi meccanici verificati vengono
mostrati con metriche di copertura.

Qui **Delete selected** cancella davvero record dal catalogo selezionato: è
un'operazione amministrativa diversa da **New / Reset design** e dalla chiusura
di una scheda di confronto. Prima di usarla va sempre scaricato il backup; non
è coinvolta nel crawler automatico staging-only.

## 13. Crawler e report catalogo

Il riquadro **Catalog crawl · latest report** in fondo alla sidebar mostra:

- fase e aggiornamento del ciclo;
- copertura delle etichette brand;
- target ufficiali unici e alias;
- marchi ancora da scoprire o etichette da pulire;
- report retail con osservazioni, match esatti e gap potenziali;
- stato `staging_only` e conferma che il catalogo esistente sia invariato.
- ultimo batch approvato append-only, con nuovi driver pubblicati, totale del
  catalogo e numero realmente visibile nell'app. Il contatore distingue il
  totale del ciclo di revisione dal numero aggiunto nell'ultimo lotto. Lo stato
  usa testo compatto, così non viene confuso con il completamento di Bass Match.

Il crawler manufacturer-first non inserisce valori inventati e non modifica,
committa o pubblica il catalogo. Finizio, Masori e RG Sound sono sorgenti retail
per gap/prezzi; i parametri tecnici di un nuovo driver devono essere confermati
dal produttore. Un risultato `observed_only` significa pagine realmente
visitate ma nessun set T/S completo; `no_pages` significa zero pagine;
`succeeded` richiede candidati completi.
La promozione successiva è separata dal crawler automatico: il report
`Reviewed catalog additions` appare solo dopo validazione esplicita e conferma
che nessuna riga preesistente sia stata modificata.

## 14. Scenari pratici

### Subwoofer home theater compatto

Sealed/reflex/PR, volume massimo reale, F3 25–35 Hz, MOL a F3 coerente con la
distanza d'ascolto, ripple 2–3 dB, ceiling 80–100 Hz, escursione 1×Xmax. Poi
verificare gruppo delay, rumore porta e tolleranza T/S.

### Subwoofer car audio SPL

Reflex/BP6/DCCAV, tensione e Re della configurazione corretta, volume netto
disponibile, MOL e impedenza minima prioritari. Verificare corsa sotto accordo,
potenza termica, compressione e robustezza meccanica; il solo wattaggio “max”
commerciale non è un parametro di progetto.

### Woofer hi-fi a due/tre vie

Sealed/reflex, ripple basso, ceiling vicino alla futura frequenza di crossover,
Le e Mms controllate, sensibilità e impedenza compatibili. Esportare FRD/ZMA e
proseguire nel simulatore di crossover.

### Installazione in porta/infinite baffle

Selezionare IB, controllare Qts, Fs montata, Xmax e MOL; il volume della porta o
del bagagliaio deve essere sufficientemente grande e l'onda posteriore isolata.
Considerare perdite e tenuta reali non modellate dall'IB ideale.

### Progetto bandpass

Definire prima banda utile e filtri elettronici. Usare optimizer come starter,
poi Atlas/tolleranza. Controllare singolarmente ogni volume/accordo, velocità di
ogni porta, MOL e group delay. Prevedere accesso per misura e correzione dei
condotti sul prototipo.

## 15. Limiti e buone pratiche

- il modello è lumped/1-D: non calcola modi 3-D del mobile, vibrazione pannelli,
  diffrazione completa o non-linearità termiche avanzate;
- T/S dipendono da rodaggio, temperatura, livello e tolleranza di produzione;
- Xmax e Pe hanno definizioni commerciali non uniformi;
- la geometria del condotto reale richiede correzioni di estremità, flare,
  pieghe e volume occupato;
- una curva simulata eccellente non garantisce bassa distorsione;
- verificare sempre misura d'impedenza, near-field/ground-plane e tenuta del
  prototipo prima della costruzione definitiva.

## 16. Riferimenti tecnici interni

Per approfondire formule e implementazione:

- `docs/engine-manual.md`: motore, T/S, carichi e grafici;
- `docs/optimizer-manual.md`: ricerca e funzione di costo;
- `docs/load-forge-innovations-manual.md`: Forge Score, MIL/MOL, tolleranze e
  direttive porte;
- `docs/acoustic-sampling-optimization.md`: griglia e refinement;
- `docs/autonomous_crawler_daemon.md`: catalogo e crawler staging-only;
- `docs/catalog-maintenance.md`: manutenzione amministrativa del catalogo.
