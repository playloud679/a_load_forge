# Deploy su Google Cloud Run

Il repository contiene un `Dockerfile` per eseguire Load Forge su Cloud Run.
L'immagine non include l'intera directory di lavoro `data/`: Docker e Cloud
Build applicano la stessa whitelist e copiano soltanto i cataloghi normalizzati
usati da `src/presets.py` più `driver_prices.json`. Restano fuori i datasheet
PDF, gli asset sorgente, i checkpoint dei crawler, i report e i database di
provenienza. In questo modo il payload dati del runtime è circa 79 MiB anziché
oltre 600 MiB, senza rimuovere driver dall'applicazione.

La whitelist è dichiarata in `.dockerignore`, `.gcloudignore` e nel `COPY`
esplicito del `Dockerfile`. Quando viene aggiunto un nuovo catalogo runtime,
aggiornare insieme tutti e tre i file; la suite verifica che rimangano
sincronizzati.

Prerequisiti locali: Docker, Google Cloud CLI, un progetto GCP con billing
attivo e Artifact Registry abilitato.

```bash
gcloud auth login
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

gcloud builds submit \
  --tag europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.12.26

gcloud run deploy load-forge \
  --image europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.12.26 \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 8Gi \
  --cpu 4 \
  --min 0 \
  --max 20 \
  --concurrency 160 \
  --timeout 3600 \
  --port 8080
```

Per un SaaS autenticato sostituire `--allow-unauthenticated` con Identity
Platform o un reverse proxy autenticato. Cloud Run fornisce la porta tramite
`PORT`; il container la usa senza configurazioni locali aggiuntive.

## Configurazione SaaS

Il branch `saas` mantiene la modalità account disattivata finché non vengono
impostate le variabili esplicite. Nel progetto di produzione corrente il branch
è distribuito nel servizio `load-forge`; se serve mantenere in parallelo anche
un deployment pubblico senza account, creare per quello un servizio distinto.

```bash
gcloud run deploy load-forge \
  --image europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:SAAS_TAG \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 8Gi \
  --cpu 4 \
  --max 20 \
  --concurrency 8 \
  --timeout 3600 \
  --port 8080
```

`--allow-unauthenticated` permette al browser di raggiungere Streamlit e il
callback OIDC; l'applicazione blocca il workspace finché `st.user` non contiene
un'identità autenticata. Le modalità locali
`LOAD_FORGE_LOCAL_ACCOUNTS` e `LOAD_FORGE_AUTH_BYPASS` vengono rifiutate quando
Cloud Run espone `K_SERVICE`.

Creare un secret `load-forge-oidc` il cui valore sia un file TOML conforme a
`.streamlit/secrets.example.toml`, quindi montarlo come file e abilitare il
backend Firestore:

```bash
gcloud run services update load-forge \
  --region europe-west1 \
  --update-env-vars=LOAD_FORGE_SAAS_ENABLED=true,LOAD_FORGE_OPEN_BETA_ENABLED=true,LOAD_FORGE_SAAS_BACKEND=firestore,LOAD_FORGE_GCP_PROJECT=PROJECT_ID \
  --update-secrets=/app/.streamlit/secrets.toml=load-forge-oidc:latest \
  --session-affinity
```

`LOAD_FORGE_OPEN_BETA_ENABLED=true` concede temporaneamente agli account
registrati l'accesso Pro senza modificare il piano memorizzato e senza creare
abbonamenti. Rimuovere o disattivare la variabile ripristina gli entitlement
normali; non migra né cancella i progetti esistenti.

Il service account di `load-forge` deve avere soltanto il ruolo necessario
per leggere e scrivere i documenti (`roles/datastore.user`) e l'accesso alla
versione del secret.  Se il database `(default)` non esiste ancora, crearlo in
Native mode nella regione scelta prima di attivare il servizio:

```bash
gcloud firestore databases create \
  --database='(default)' \
  --location=europe-west1 \
  --type=firestore-native \
  --delete-protection
```

L'affinità di sessione riduce i cambi istanza durante i reconnect, ma i
progetti persistenti restano la fonte autorevole: non affidare dati utente alla
memoria del container.

## Crawler-agent come applicazione separata

Il crawling non gira nel processo Streamlit e non condivide l'identità del
SaaS. È un Cloud Run Job autonomo, costruito con
`services/crawler_agent/Dockerfile`, che può leggere il catalogo approvato e
scrivere soltanto artifact di staging. Non importa LSDB, VituixCAD, Speaker
Box Lite o altri database aggregati: il manifest accetta esclusivamente domini
web esplicitamente autorizzati.

La promozione è un secondo comando con identità distinta e approvazione umana;
crea una release immutabile. Il SaaS monta quella release in sola lettura e
imposta:

```text
LOAD_FORGE_MANUFACTURER_CATALOG_PATH=/catalog/releases/manufacturer-RELEASE.json
```

Build, configurazione del job, policy delle sorgenti e procedura di promozione
sono descritti in [crawler-agent-service.md](crawler-agent-service.md).
