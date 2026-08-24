# Crawler Agent service

The crawler is a separate service application, not part of the interactive
Load Forge SaaS process.  It is packaged by
`services/crawler_agent/Dockerfile` and is designed for Cloud Run Jobs.

## Responsibility boundary

```text
coverage objective + approved source manifest
                    |
                    v
          crawler-agent planner
                    |
          policy-valid crawl tasks
                    |
                    v
       staging candidate catalogs + run report
                    |
           explicit human approval
                    |
                    v
        immutable manufacturer catalog release
                    |
                    v
          Load Forge SaaS read-only mount
```

The agent may prioritize targets, choose the next bounded crawl and react to
coverage gaps.  It cannot write the production manufacturer catalog.
`services/crawler_agent/release.py` is a separate promotion command requiring
both `release_id` and `approved_by`; it creates a new output file and refuses
to overwrite an existing release.

## Legal/source policy

`AgentManifest` accepts only:

- `official_manufacturer_site`;
- `official_archive`;
- `authorized_retailer`.

Every target must declare exact domains and direct HTTP(S) seeds/sitemaps.
Subdomains must be listed explicitly; an allow-list for the parent domain does
not silently authorize them.
Names or paths suggesting LSDB, VituixCAD, Speaker Box Lite or another
aggregated driver database are rejected before execution.  The user agent must
contain a contact URL or email, request delay is at least 0.5 seconds,
`robots.txt` remains enforced by `tools/crawl_thiele_small.py`, and the crawl
has explicit page/depth/confidence limits.

The service extracts factual T/S values and retains exact URL, timestamp,
method, raw fields and confidence.  Page prose, database dumps and unrelated
copyrighted content are not publication artifacts.

This technical policy reduces provenance and redistribution risk; it is not a
legal opinion.  Before enabling a domain, review its terms, applicable
database rights and crawl restrictions.  An allow-list entry is an explicit
operator decision, not a conclusion made by the agent.

## Agent plan

The current planner is deterministic and auditable.  It scores enabled,
policy-valid targets by:

- manifest priority;
- brands missing from the current direct-source catalog;
- the number and density of missing published-only `Xmax`, `Pe` and `Le`
  cells for brands already present;
- availability of a bounded sitemap;
- preference for first-party sources;
- estimated page cost.

Price gaps are intentionally excluded from this source score: catalog crawling
fills technical observations, while retailer prices are handled by the
separate confidence-checked completion cycle.

This is deliberately a hard policy layer.  A future LLM planner may propose
target priorities or source adapters, but its output must still pass
`AgentManifest` validation and it must never receive production-write
credentials.

Preview a plan without network access:

```bash
.venv/bin/python -m services.crawler_agent.agent plan \
  --manifest services/crawler_agent/manifest.example.json \
  --catalog data/manufacturer_drivers.json
```

Load Forge does not require operators to maintain a brand-by-brand manifest by
hand. `tools/build_official_source_registry.py` inventories every brand and its
catalog provenance, excludes retailers/aggregators, collapses aliases and
writes the real `services/crawler_agent/manifest.loadforge.json`. Unresolved
brands remain visible in `data/official_source_registry.json` and are processed
by `tools/discover_official_manufacturer_sites.py`; they are never silently
dropped from coverage reporting.

The registry builder also consumes
`services/crawler_agent/official_source_seeds.json`. It contains reviewed
manufacturer category/archive entry points and explicit legacy-brand aliases
that automatic spelling/domain inference cannot establish safely. These seeds
only choose bounded crawl targets: extracted candidates still go to staging
and the proprietary catalog remains unchanged.

Execute into an isolated writable staging directory:

```bash
.venv/bin/python -m services.crawler_agent.agent run \
  --manifest /config/crawler-agent-manifest.json \
  --catalog /catalog/current/manufacturer_drivers.json \
  --run-root /workspace/runs
```

Each run creates `plan.json`, per-target logs/checkpoint/candidate catalog and
`run_report.json` with `publication_state=staging_only`. Target results report
real `visited`, `extracted` and failure counts. A zero-page run is `no_pages`,
a crawl with only partial observations is `observed_only`, and only a crawl
with complete extracted candidates is `succeeded`.

## Cloud Run Job

Build the crawler image independently from the interactive SaaS image:

```bash
CRAWLER_IMAGE=europe-west1-docker.pkg.dev/PROJECT_ID/load-forge/crawler-agent:SAAS_TAG

gcloud builds submit . \
  --config services/crawler_agent/cloudbuild.yaml \
  --substitutions _IMAGE="$CRAWLER_IMAGE"
```

Create a dedicated job.  `/config` should contain the reviewed manifest and
`/workspace` should be a staging-only Cloud Storage mount:

```bash
gcloud run jobs create load-forge-crawler-agent \
  --image "$CRAWLER_IMAGE" \
  --region europe-west1 \
  --service-account load-forge-crawler@PROJECT_ID.iam.gserviceaccount.com \
  --cpu 2 \
  --memory 2Gi \
  --task-timeout 3600s \
  --max-retries 1
```

Configure the two volume mounts according to the chosen Secret Manager and
Cloud Storage FUSE setup, then schedule
`gcloud run jobs execute load-forge-crawler-agent`.  Do not attach the
Firestore role or any production catalog write role to this job.

## Promotion

After reviewing the reports and candidates:

```bash
.venv/bin/python -m services.crawler_agent.release \
  --manifest /config/crawler-agent-manifest.json \
  --baseline /catalog/current/manufacturer_drivers.json \
  --candidate /workspace/runs/RUN/TARGET/candidate_catalog.json \
  --output /catalog/releases/manufacturer-YYYYMMDD.json \
  --release-id manufacturer-YYYYMMDD \
  --approved-by REVIEWER_ID
```

Promotion binds every artifact directory to an enabled manifest target,
revalidates the exact source label and domain, T/S physics and extraction
confidence, merges without overwriting populated baseline fields, writes
approval metadata and calculates a SHA-256 digest.

## Cloud isolation

Use a dedicated Cloud Run Job, service account, staging bucket and quotas.
The crawler identity may write only its staging prefix.  A separate release
identity may read staging and write new immutable release objects.  The SaaS
runtime identity receives read-only access to the approved release prefix and
sets `LOAD_FORGE_MANUFACTURER_CATALOG_PATH` to its mounted release file.
