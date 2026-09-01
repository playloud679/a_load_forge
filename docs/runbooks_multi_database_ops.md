# Operational Runbooks — Multi-Database Architecture

This document defines standard operating procedures for managing, recovering, and maintaining Load Forge's 4 isolated Firestore databases:
1. `lf-private`
2. `lf-public`
3. `lf-catalog-runtime`
4. `lf-catalog-staging`

---

## Runbook 1: Disaster Recovery & Project Restoration for `lf-private`

### Incident Scenarios
* Accidental user project deletion or overwriting.
* Tenant data corruption or localized data loss.
* Full database restoration following catastrophic region event.

### Procedure A: Single Project Restoration via Application Revision (Least Invasive)
1. Determine `tenant_id` and `project_id`.
2. Inspect available revisions via `PrivateStore.list_revisions(user, project_id)`.
3. Invoke `restore_revision(user, project_id, revision=N, app_version=...)`:
   * This appends a new current revision with the historical parameters.
   * Revision history remains completely intact and continuous.

### Procedure B: Restoration from Point-in-Time Recovery (PITR - within 7 days)
If the project was deleted past application Trash retention:
1. Identify the exact UTC timestamp before the incident (`TIMESTAMP_UTC`).
2. Read the historical document state using Firestore PITR read timestamp:
   ```bash
   gcloud firestore databases restore \
     --source-database="lf-private" \
     --destination-database="lf-private-restore-tmp" \
     --recovery-time="2026-09-01T10:00:00Z" \
     --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
3. Extract the target `tenants/{tenant_id}/projects/{project_id}` and `revisions/` subcollection.
4. Copy the restored record back to the live `lf-private` database.
5. Delete the temporary restore database `lf-private-restore-tmp`:
   ```bash
   gcloud firestore databases delete --database="lf-private-restore-tmp" --project="${LOAD_FORGE_GCP_PROJECT}"
   ```

### Procedure C: Full Database Restore from Scheduled Backup (Outside PITR Window)
1. List available backups:
   ```bash
   gcloud firestore backups list --location=europe-west1 --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
2. Restore to a verified target database:
   ```bash
   gcloud firestore backups restore "${BACKUP_NAME}" \
     --destination-database="lf-private-recovered" \
     --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
3. Run verification check using `tools/migrate_private_data.py --source-db=lf-private-recovered --target-db=lf-private`.

---

## Runbook 2: Catalog Release Rollback for `lf-catalog-runtime`

### Incident Scenarios
* A promoted driver catalog release contains incorrect T/S parameters, bad frequency curves, or unverified prices.
* Bass Match recommendations produce non-physical box sizes due to a bad catalog batch.

### Instant Rollback Procedure
1. Identify the previous known good release ID (`releases/manufacturer-YYYYMMDD`).
2. Execute the rollback pipeline tool with explicit operator authorization:
   ```bash
   .venv/bin/python tools/promote_catalog_release.py \
     --rollback="manufacturer-20260815" \
     --approved-by="lead-engineer@loadforge.app" \
     --commit
   ```
3. The tool atomically updates `catalog_metadata/active_release` to point to `manufacturer-20260815`.
4. Invalidate application preset caches:
   * Next request or deployment immediately serves the rolled-back canonical catalog.
   * Zero downtime, zero mutation of historical release manifests.

---

## Runbook 3: Cleanup & Quarantine Purge for `lf-catalog-staging`

### Incident Scenarios
* Crawler job encountered a malformed or spam-injected retailer catalog.
* Memory limit exceeded during bulk crawler harvest.
* Staging collection size exceeds operational quota.

### Purge Procedure (`lf-catalog-staging` is completely disposable)
1. Stop any active crawler jobs:
   ```bash
   gcloud run jobs executions list --job=load-forge-crawler-agent --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
2. Delete corrupted staging candidate collections:
   ```bash
   gcloud firestore databases delete --database="lf-catalog-staging" --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
3. Re-create a clean staging database:
   ```bash
   gcloud firestore databases create \
     --database="lf-catalog-staging" \
     --location=europe-west1 \
     --type=firestore-native \
     --project="${LOAD_FORGE_GCP_PROJECT}"
   ```
4. Verify that `lf-catalog-runtime`, `lf-private`, and `lf-public` are completely unaffected:
   ```bash
   .venv/bin/python tests/test_storage_boundaries.py
   ```

---

## Runbook 4: Emergency Database Switchover & IAM Audit Checklist

### Environment Variable Verification
Ensure Cloud Run services are configured with explicit named databases:
```text
LF_FIRESTORE_PRIVATE_DB=lf-private
LF_FIRESTORE_PUBLIC_DB=lf-public
LF_FIRESTORE_CATALOG_RUNTIME_DB=lf-catalog-runtime
LF_FIRESTORE_CATALOG_STAGING_DB=lf-catalog-staging
LOAD_FORGE_STRICT_MULTI_DB=true
```

### IAM Permission Audit
Run the IAM policy audit to verify that no service account has cross-database privileges:
```bash
gcloud projects get-iam-policy "${LOAD_FORGE_GCP_PROJECT}" \
  --flatten="bindings[].members" \
  --format="table(bindings.role, bindings.members, bindings.condition.title)"
```
Verify:
* `sa-loadforge-crawler` has NO bindings on `lf-private`, `lf-public`, or `lf-catalog-runtime`.
* `sa-loadforge-app` has NO write binding on `lf-catalog-runtime`.
* `sa-loadforge-promoter` has NO binding on `lf-private` or `lf-public`.
