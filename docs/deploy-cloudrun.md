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
  --tag europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.13.1

gcloud run deploy load-forge \
  --image europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.13.1 \
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
  --update-env-vars=LOAD_FORGE_SAAS_ENABLED=true,LOAD_FORGE_OPEN_BETA_ENABLED=true,LOAD_FORGE_SAAS_BACKEND=firestore,LOAD_FORGE_GCP_PROJECT=PROJECT_ID,LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS=30 \
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

## Firestore backup e disaster recovery

Cloud autosave and application revisions reduce common project-loss risks, but
they do not replace database-level disaster recovery. The operator must enable
and periodically verify the following Google Cloud settings; the application
does not pretend to configure them.

1. Enable billing, open **Firestore > Databases > (default) > Disaster
   Recovery**, edit the settings and enable **Point-in-time recovery**. PITR is
   disabled by default and, once its window has filled, retains minute-level
   recovery points for seven days. For a newly created database, add
   `--enable-pitr` to `gcloud firestore databases create`. See the official
   [PITR procedure](https://cloud.google.com/firestore/native/docs/use-pitr).
2. Create one daily scheduled backup with an operational retention suited to
   the budget (recommended baseline: 14 days), for example:

   ```bash
   gcloud firestore backups schedules create \
     --database='(default)' \
     --recurrence=daily \
     --retention=14d
   ```

3. Add a weekly schedule with longer retention (recommended baseline: 12
   weeks) if the current Google Cloud limits and budget allow it. Verify the
   active flags against the current official
   [scheduled backup documentation](https://cloud.google.com/firestore/native/docs/backups)
   before automation because this is an operator-controlled cloud feature.
4. Quarterly, restore a recent backup into a separate temporary Firestore
   database. Verify tenant project counts, open representative current
   payloads and revisions, and validate account/credit documents. Record the
   test date and delete the temporary database only after verification.
5. Back up the global driver catalog separately from user projects. Preserve
   immutable released JSON catalog artifacts plus the `driver_presets`
   Firestore collection (if used) in versioned Cloud Storage; test that a clean
   deployment can rebuild both tiers without reading user projects.

### Recovering one deleted or corrupted project

Use the least invasive source in this order:

1. If the project is in application Trash, use **Restore from Trash**.
2. If a valid application revision exists, explicitly restore it; this creates
   a new current revision and does not mutate history.
3. Within the PITR window, read only the affected
   `tenants/{tenant_id}/projects/{project_id}` document and its `revisions`
   subcollection at a time before the incident, validate the payload, then
   write it back as a new revision. Do not replace the entire live database for
   one project.
4. Outside the PITR window, restore the scheduled backup into a separate
   database, inspect and validate the affected project, then copy that project
   into the live database as a new revision.
5. If the user has an `.lfp`, import it and let autosave create a new cloud
   project. Never mark a historical revision current by directly editing only
   `current_revision`; use the application restore API or an audited recovery
   script that writes parent and revision atomically.

Permanent Trash cleanup is a separate scheduled process. It may delete only
projects with `status=trashed` and `deleted_at` older than 30 days. Application
revision retention targets the latest 30 revisions; prune older revision
documents only in that maintenance process and never delete the active
revision.

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
