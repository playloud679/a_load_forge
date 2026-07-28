# Deploy su Google Cloud Run

Il repository contiene un `Dockerfile` per eseguire Load Forge su Cloud Run.
Il catalogo `data/` viene incluso nell'immagine ed è usato in sola lettura.

Prerequisiti locali: Docker, Google Cloud CLI, un progetto GCP con billing
attivo e Artifact Registry abilitato.

```bash
gcloud auth login
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

gcloud builds submit \
  --tag europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.6.9

gcloud run deploy load-forge \
  --image europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/load-forge:0.6.9 \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 8Gi \
  --cpu 4 \
  --min 0 \
  --max 5 \
  --concurrency 160 \
  --timeout 3600 \
  --port 8080
```

Per un SaaS autenticato sostituire `--allow-unauthenticated` con Identity
Platform o un reverse proxy autenticato. Cloud Run fornisce la porta tramite
`PORT`; il container la usa senza configurazioni locali aggiuntive.
