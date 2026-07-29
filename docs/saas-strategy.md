# Strategia SaaS e monetizzazione

Stato: proposta operativa
Data di riferimento: 29 luglio 2026

Questo documento raccoglie le considerazioni strategiche per trasformare Load
Forge in un servizio SaaS senza anticipare complessità di pagamento e senza
ridurre il controllo degli utenti sui propri dati. Le scelte tecniche
dell'infrastruttura SaaS sono descritte separatamente in [saas.md](saas.md).

## Obiettivi

- Validare che Load Forge venga usato con continuità prima di fissare prezzi e
  limiti.
- Rendere semplice la prima adozione: nessuna carta e nessun abbonamento
  durante la beta.
- Monetizzare il risparmio di tempo e gli strumenti professionali, non la
  correttezza del calcolo acustico.
- Conservare crawler e catalogo come servizio separato dall'applicazione SaaS.
- Lasciare all'utente il controllo esplicito di salvataggio e caricamento dei
  propri progetti.
- Evitare di custodire dati di pagamento o di costruire un sistema di billing
  proprietario.

## Decisione iniziale: Open Beta gratuita

Load Forge viene offerto gratuitamente con tutte le funzionalità abilitate per
un periodo iniziale di osservazione.

Condizioni della beta:

- registrazione necessaria per usare le funzioni SaaS;
- nessuna carta richiesta;
- nessun cliente o abbonamento Stripe creato;
- nessun rinnovo o addebito automatico;
- tutte le funzioni disponibili agli account della beta;
- salvataggio e caricamento dei progetti soltanto su azione esplicita
  dell'utente;
- comunicazione chiara che funzionalità, limiti e prezzi potranno cambiare al
  termine della beta.

La finestra proposta è di 90 giorni, con una verifica intermedia dopo 60
giorni. La data non deve però essere l'unico criterio: se il campione è ancora
insufficiente, la beta può essere estesa invece di definire prezzi senza dati.

### Rappresentazione applicativa consigliata

Durante la beta l'account può continuare ad avere il piano interno `free`. Un
interruttore globale, per esempio `OPEN_BETA_ENABLED`, gli assegna
temporaneamente gli entitlement completi.

Questo evita:

- di creare un finto abbonamento;
- di migrare successivamente un piano `beta`;
- di coinvolgere Stripe prima che esista un'offerta commerciale;
- di mescolare lo stato commerciale con l'accesso promozionale temporaneo.

L'interruttore deve essere valutato dal server e non deve essere controllabile
dal browser.

## Informazioni da raccogliere durante la beta

L'obiettivo non è sorvegliare il lavoro dell'utente, ma capire se il prodotto
risolve un problema ricorrente.

Metriche minime:

- numero di registrazioni verificate;
- utenti che completano almeno una simulazione valida;
- utenti attivi settimanali;
- ritorno dopo 7 e 30 giorni;
- conteggio delle funzioni utilizzate;
- numero di salvataggi e caricamenti richiesti esplicitamente;
- esportazioni e confronti eseguiti;
- tempo di risposta, errori applicativi e costo infrastrutturale medio;
- richieste di supporto e funzionalità maggiormente richieste.

Non è necessario registrare:

- parametri T/S inseriti dall'utente;
- contenuto o nome dei progetti;
- configurazioni acustiche;
- file esportati;
- cronologia dettagliata delle azioni;
- dati di pagamento.

È sufficiente conservare eventi aggregabili come `simulation_completed` o
`project_saved`, associati quando necessario a un identificatore tecnico
pseudonimo. La telemetria deve essere documentata nell'informativa privacy e
avere una conservazione limitata.

## Criteri per concludere la beta

La monetizzazione non deve iniziare soltanto perché sono trascorsi 90 giorni.
Prima della transizione devono essere soddisfatte almeno queste condizioni:

1. Il servizio mantiene sessioni e account in modo affidabile su Cloud Run.
2. Gli errori applicativi e i problemi di perdita dello stato sono monitorati.
3. Salvataggio e caricamento manuali sono prevedibili e testati.
4. Esiste un gruppo misurabile di utenti che torna a usare il prodotto.
5. È chiaro quali funzioni producono valore professionale.
6. Il costo medio per utente è noto con sufficiente approssimazione.
7. Privacy policy, condizioni d'uso e procedura di assistenza sono disponibili.
8. Il futuro flusso di pagamento è stato verificato integralmente in ambiente
   Stripe di test.

Se questi criteri non sono soddisfatti, la priorità rimane l'affidabilità,
non l'introduzione del pagamento.

## Principio di differenziazione

La simulazione di base deve rimanere scientificamente completa e corretta
anche nel piano gratuito. Il piano a pagamento deve vendere produttività,
capacità e comodità.

Ipotesi iniziale, da validare con l'uso reale:

| Area | Free | Pro |
|---|---|---|
| Simulazioni acustiche fondamentali | Complete | Complete |
| Catalogo driver e Finder | Disponibili con limiti ragionevoli | Limiti elevati |
| Salvataggio/caricamento locale | Disponibile | Disponibile |
| Progetti cloud | Pochi progetti | Quota elevata |
| Confronti simultanei | Essenziali | Multipli e avanzati |
| Ottimizzazione e calcoli batch | Limitati o assenti | Inclusi |
| Esportazioni | Formati essenziali | Report ed esportazioni avanzate |
| Driver privati | Limitati | Quota elevata |
| Cronologia e versioni | Assente o breve | Estesa |
| Assistenza | Standard | Prioritaria |

I limiti numerici non vanno fissati prima di conoscere uso, costi e valore
percepito. Devono inoltre essere applicati lato server.

## Strategia per i primi utenti

Gli utenti della beta hanno contribuito a validare e migliorare il prodotto.
È opportuno registrarli come coorte `founding_user`, indipendente dal piano.

Possibili benefici:

- sconto del 50% per i primi sei mesi di Pro;
- prezzo promozionale bloccato per un periodo definito;
- badge Founding User;
- accesso anticipato alle nuove funzioni;
- canale diretto per feedback.

Non è consigliato promettere Pro gratuito a vita: una promessa permanente
precede la conoscenza dei costi futuri e può diventare insostenibile. Anche
l'eventuale vantaggio Founding User deve essere comunicato con durata e
condizioni precise.

## Transizione dalla beta al modello Free/Pro

La transizione proposta è intenzionale e non automatica:

1. Comunicare piani, prezzi e limiti almeno 30 giorni prima.
2. Mostrare a ciascun utente quali funzioni usa e cosa cambierà.
3. Conservare tutti i progetti esistenti.
4. Consentire l'esportazione prima e dopo la transizione.
5. Portare gli account che non scelgono un abbonamento al piano Free.
6. Attivare Pro soltanto dopo una scelta esplicita e un pagamento confermato.
7. Non richiedere retroattivamente il pagamento per il periodo di beta.
8. Non cancellare automaticamente dati quando un abbonamento termina.

Se un account supera le future quote Free, i dati esistenti devono rimanere
leggibili e scaricabili. Si possono impedire nuovi salvataggi oltre quota, ma
non rendere i progetti ostaggio dell'abbonamento.

## Contratto sui dati degli utenti

Il modello commerciale non modifica il principio di controllo manuale:

- nessun autosalvataggio;
- nessun caricamento automatico;
- nessuna modifica invisibile dei progetti;
- nessuna cancellazione automatica al downgrade;
- nessun uso del contenuto dei progetti per profilazione commerciale;
- salvataggio e caricamento avvengono solo dopo un comando esplicito;
- l'utente deve poter esportare una copia portabile dei propri dati.

Il sistema di autorizzazione può conoscere proprietario, quota, data di
aggiornamento e dimensione del record. Non deve analizzare il progetto per
decidere prezzi o pubblicità.

## Pagamenti: complessità rinviata, non ignorata

Stripe deve essere introdotto soltanto quando il piano Pro è definito.
All'inizio è sufficiente un unico prodotto a prezzo fisso, preferibilmente con
opzione mensile e annuale.

Separazione delle responsabilità:

- il provider di identità conserva l'identità dell'utente;
- Stripe conserva carte, pagamenti, fatture e abbonamenti;
- Load Forge conserva soltanto l'identificatore Stripe e lo stato minimo degli
  entitlement;
- un webhook verificato aggiorna l'accesso alle funzioni;
- un reindirizzamento di successo nel browser non concede da solo Pro.

Stripe Checkout e Customer Portal evitano che Load Forge gestisca direttamente
carte e operazioni amministrative. I riferimenti tecnici di partenza sono:

- [Stripe Checkout](https://docs.stripe.com/payments/checkout)
- [Stripe Customer Portal](https://docs.stripe.com/customer-management)
- [Stripe subscription webhooks](https://docs.stripe.com/billing/subscriptions/webhooks)
- [Stripe Entitlements](https://docs.stripe.com/billing/entitlements)
- [Stripe Billing test clocks](https://docs.stripe.com/billing/testing)

## Crawler e catalogo

Il crawler agent-driven resta un'applicazione di servizio distinta dal SaaS:

```text
siti originali autorizzati
        -> crawler agent
        -> staging e revisione
        -> release immutabile del catalogo
        -> Load Forge
```

Il crawler:

- acquisisce dati da siti originali, non copia altri database;
- rispetta policy, provenienza e revisione umana;
- non accede agli account o ai progetti degli utenti;
- non dipende dallo stato Free/Pro;
- pubblica versioni del catalogo consumabili in sola lettura dall'app.

In futuro si potrà differenziare la frequenza di aggiornamento o gli strumenti
di analisi del catalogo, non la provenienza e l'affidabilità dei dati.

## Rischi principali

| Rischio | Contromisura |
|---|---|
| Gli utenti percepiscono il pagamento come una sottrazione | Annuncio anticipato, Free realmente utile e beneficio Founding User |
| La beta non produce dati sufficienti | Estensione della beta e interviste qualitative |
| Si monetizzano funzioni poco apprezzate | Decisioni basate su uso ricorrente e feedback |
| Costi Cloud Run/Firestore non noti | Misurazione per account e limiti di sicurezza |
| Perdita o blocco dei progetti | Salvataggio esplicito, export portabile, backup e test di ripristino |
| Stato pagamento non coerente | Webhook idempotente e riconciliazione periodica con Stripe |
| Complessità prematura | Un solo piano Pro e nessun billing a consumo iniziale |
| Crawler confuso con dati degli utenti | Servizio, credenziali e datastore separati |

## Decisioni rinviate

Non sono ancora decisioni definitive:

- prezzo mensile e annuale;
- quote esatte del piano Free e Pro;
- durata e valore del beneficio Founding User;
- introduzione di una prova Pro dopo la beta;
- piano Team e gestione delle organizzazioni;
- fatturazione a consumo;
- funzioni esatte da riservare a Pro.

Questi elementi vanno decisi dopo la fase di osservazione e non devono essere
presentati pubblicamente come impegni già assunti.

## Sequenza operativa consigliata

1. Rendere affidabili registrazione, login e sessione su Cloud Run.
2. Implementare l'Open Beta come entitlement globale lato server.
3. Confermare che Save e Load restino azioni manuali.
4. Aggiungere telemetria minima e rispettosa del contenuto dei progetti.
5. Pubblicare condizioni della beta e informativa privacy.
6. Osservare utilizzo e costi, con revisione al giorno 60.
7. Proporre Free/Pro usando evidenze raccolte.
8. Comunicare la transizione con almeno 30 giorni di anticipo.
9. Integrare e collaudare Stripe in sandbox.
10. Aprire volontariamente gli abbonamenti Pro senza addebiti automatici agli
    utenti della beta.

## Sintesi della strategia

La scelta raccomandata è offrire inizialmente Load Forge come Open Beta
completa e gratuita. La beta serve a verificare affidabilità, uso ricorrente,
valore professionale e costo operativo. La successiva versione Free deve
continuare a produrre simulazioni corrette; Pro deve premiare chi necessita di
maggiore produttività. Pagamenti e differenziazione entrano soltanto dopo una
comunicazione anticipata, senza conversioni automatiche e senza perdere,
leggere o trattenere i progetti degli utenti.
