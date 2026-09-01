#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Load Forge Multi-Database Provisioning & Least-Privilege IAM Setup
# ==============================================================================
# Databases:
#   1. lf-private         (Tenant projects, revisions, accounts, credits)
#   2. lf-public          (Community publications, versions, discovery)
#   3. lf-catalog-runtime (Trusted canonical driver catalog, releases)
#   4. lf-catalog-staging (Untrusted crawler workspace, candidates)
#
# Service Accounts:
#   1. sa-loadforge-app       (Cloud Run Web App instance)
#   2. sa-loadforge-crawler   (Cloud Run Job Crawler Agent)
#   3. sa-loadforge-promoter  (CI/CD / Release promotion pipeline)
#   4. sa-loadforge-public    (Public embed / discovery worker)
# ==============================================================================

PROJECT_ID="${1:-${LOAD_FORGE_GCP_PROJECT:-civic-radio-502611-i8}}"
LOCATION="${2:-europe-west1}"

echo "============================================================"
echo "Configuring Load Forge Multi-Database Architecture"
echo "GCP Project: ${PROJECT_ID}"
echo "Region:      ${LOCATION}"
echo "============================================================"

# ------------------------------------------------------------------------------
# 1. Provision Named Databases
# ------------------------------------------------------------------------------

create_db_if_missing() {
  local db_name="$1"
  local enable_pitr="$2"
  local delete_protection="$3"

  echo "Checking database: ${db_name}..."
  if ! gcloud firestore databases describe --database="${db_name}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating database ${db_name}..."
    local args=(
      --database="${db_name}"
      --location="${LOCATION}"
      --type=firestore-native
      --project="${PROJECT_ID}"
    )
    if [ "${enable_pitr}" = "true" ]; then
      args+=(--enable-pitr)
    fi
    if [ "${delete_protection}" = "true" ]; then
      args+=(--delete-protection)
    fi
    gcloud firestore databases create "${args[@]}"
    echo "Created database ${db_name}"
  else
    echo "Database ${db_name} already exists."
  fi
}

create_db_if_missing "lf-private" "true" "true"
create_db_if_missing "lf-public" "true" "true"
create_db_if_missing "lf-catalog-runtime" "true" "true"
create_db_if_missing "lf-catalog-staging" "false" "false"

# ------------------------------------------------------------------------------
# 2. Provision Service Accounts
# ------------------------------------------------------------------------------

create_sa_if_missing() {
  local sa_name="$1"
  local display_name="$2"

  local sa_email="${sa_name}@${PROJECT_ID}.iam.gserviceaccount.com"
  echo "Checking service account: ${sa_email}..."
  if ! gcloud iam service-accounts describe "${sa_email}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating service account ${sa_name}..."
    gcloud iam service-accounts create "${sa_name}" \
      --display-name="${display_name}" \
      --project="${PROJECT_ID}"
    echo "Created ${sa_email}"
  else
    echo "Service account ${sa_email} already exists."
  fi
}

create_sa_if_missing "sa-loadforge-app" "Load Forge SaaS Cloud Run Runtime"
create_sa_if_missing "sa-loadforge-crawler" "Load Forge Crawler Ingestion Agent"
create_sa_if_missing "sa-loadforge-promoter" "Load Forge Catalog Promotion Pipeline"
create_sa_if_missing "sa-loadforge-public" "Load Forge Public & Embed Service"

# ------------------------------------------------------------------------------
# 3. Configure Least-Privilege IAM Bindings with Resource Conditions
# ------------------------------------------------------------------------------

apply_db_role() {
  local sa_name="$1"
  local role="$2"
  local condition_title="$3"
  local condition_expr="$4"

  local sa_email="${sa_name}@${PROJECT_ID}.iam.gserviceaccount.com"
  echo "Binding ${role} to ${sa_email} [Condition: ${condition_title}]..."
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${sa_email}" \
    --role="${role}" \
    --condition="title=${condition_title},expression=${condition_expr}" \
    --quiet
}

# A. sa-loadforge-app:
#    - Read/Write on lf-private and lf-public
#    - Read-Only on lf-catalog-runtime
#    - NO access to lf-catalog-staging
apply_db_role "sa-loadforge-app" "roles/datastore.user" "app_private_and_public_access" \
  "resource.name.endsWith('/databases/lf-private') || resource.name.endsWith('/databases/lf-public')"

apply_db_role "sa-loadforge-app" "roles/datastore.viewer" "app_catalog_runtime_readonly" \
  "resource.name.endsWith('/databases/lf-catalog-runtime')"

# B. sa-loadforge-crawler:
#    - Read/Write ONLY on lf-catalog-staging
#    - NO access to lf-private, lf-public, lf-catalog-runtime
apply_db_role "sa-loadforge-crawler" "roles/datastore.user" "crawler_staging_workspace_only" \
  "resource.name.endsWith('/databases/lf-catalog-staging')"

# C. sa-loadforge-promoter:
#    - Read ONLY on lf-catalog-staging
#    - Read/Write on lf-catalog-runtime
#    - NO access to lf-private, lf-public
apply_db_role "sa-loadforge-promoter" "roles/datastore.viewer" "promoter_read_staging" \
  "resource.name.endsWith('/databases/lf-catalog-staging')"

apply_db_role "sa-loadforge-promoter" "roles/datastore.user" "promoter_write_catalog_runtime" \
  "resource.name.endsWith('/databases/lf-catalog-runtime')"

# D. sa-loadforge-public:
#    - Read-Only on lf-public and lf-catalog-runtime
#    - NO access to lf-private or lf-catalog-staging
apply_db_role "sa-loadforge-public" "roles/datastore.viewer" "public_service_readonly" \
  "resource.name.endsWith('/databases/lf-public') || resource.name.endsWith('/databases/lf-catalog-runtime')"

echo "============================================================"
echo "IAM & Database Hardening Complete for ${PROJECT_ID}"
echo "============================================================"
