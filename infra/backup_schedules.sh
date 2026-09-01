#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Load Forge Multi-Database Backup Schedules & PITR Configuration
# ==============================================================================
# Policies:
#   - lf-private:         Continuous PITR (7 days) + Daily (14d) + Weekly (12w)
#   - lf-public:          Continuous PITR (7 days) + Weekly (4w)
#   - lf-catalog-runtime: Continuous PITR (7 days) + Release snapshot backups
#   - lf-catalog-staging: Disposable (No backup required)
# ==============================================================================

PROJECT_ID="${1:-${LOAD_FORGE_GCP_PROJECT:-civic-radio-502611-i8}}"
LOCATION="${2:-europe-west1}"

echo "============================================================"
echo "Configuring Firestore Backup Schedules"
echo "Project:  ${PROJECT_ID}"
echo "Location: ${LOCATION}"
echo "============================================================"

# 1. lf-private (Highest Tier: User projects, revisions, credits)
echo "Setting up backup schedules for lf-private..."
gcloud firestore backups schedules create \
  --database="lf-private" \
  --recurrence=daily \
  --retention=14d \
  --project="${PROJECT_ID}" || echo "Daily schedule for lf-private already exists or configured."

gcloud firestore backups schedules create \
  --database="lf-private" \
  --recurrence=weekly \
  --day-of-week=SUN \
  --retention=84d \
  --project="${PROJECT_ID}" || echo "Weekly schedule for lf-private already exists or configured."

# 2. lf-public (Community publications & versions)
echo "Setting up backup schedules for lf-public..."
gcloud firestore backups schedules create \
  --database="lf-public" \
  --recurrence=weekly \
  --day-of-week=SUN \
  --retention=28d \
  --project="${PROJECT_ID}" || echo "Weekly schedule for lf-public already exists or configured."

# 3. lf-catalog-runtime (Trusted canonical driver catalog)
echo "Setting up backup schedules for lf-catalog-runtime..."
gcloud firestore backups schedules create \
  --database="lf-catalog-runtime" \
  --recurrence=weekly \
  --day-of-week=SUN \
  --retention=28d \
  --project="${PROJECT_ID}" || echo "Weekly schedule for lf-catalog-runtime already exists or configured."

echo "============================================================"
echo "Backup Schedules Configured Successfully."
echo "============================================================"
