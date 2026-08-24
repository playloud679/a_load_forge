# Autonomous catalog crawler

`tools/autonomous_crawler_daemon.py` reviews every brand in the proprietary
catalog against first-party manufacturer sites. It is a staging producer: it
does not edit `data/catalog_proprietario.json`, invalidate its cache, commit, or
push. Existing catalog records are preserved until a separately approved
release operation is run.

## Source discovery

Each cycle builds `data/official_source_registry.json` from all URL provenance
already attached to the catalog. Retailers and aggregate databases are removed
from first-party scoring. `tools/discover_official_manufacturer_sites.py` then
probes plausible domains for unresolved brands and verifies both brand identity
and loudspeaker vocabulary before caching a result in
`data/official_source_discovery_cache.json`.

Reviewed first-party entry points live in
`services/crawler_agent/official_source_seeds.json`. This file lets the agent
retain manufacturer category/archive URLs and explicit legacy-brand aliases
that cannot be inferred safely from spelling alone. It supplements automatic
discovery; it is not a list of catalog records and never writes the catalog.

The registry reports four distinct states:

- `ready`: one canonical official domain and one crawler target;
- `alias`: a catalog label or product line covered by a canonical target;
- `needs_discovery`: a real-looking brand with no verified official site yet;
- `needs_brand_cleanup`: a label that looks like a model, category, or retailer.

The generated `services/crawler_agent/manifest.loadforge.json` contains only
canonical, verified manufacturer domains. Duplicate domains are collapsed.
Run registry generation without network access with:

```bash
.venv/bin/python tools/build_official_source_registry.py
```

## Retailer boundary

`services/crawler_agent/retailer_sources.json` configures Finizio Power Team,
Masori and RG Sound separately. Those sources may reveal missing model
identities, current prices, availability, and purchase links. Their technical
values are observations only: a new driver requires confirmation from the
manufacturer site and retailers never establish the catalog brand.

## Running and progress

Run one complete staging cycle:

```bash
.venv/bin/python tools/autonomous_crawler_daemon.py --once
```

Build only the registry/report, without crawling manufacturer pages:

```bash
.venv/bin/python tools/autonomous_crawler_daemon.py --once --registry-only
```

Continuous mode defaults to one cycle per hour. During active work a heartbeat
is printed every 60 seconds with phase, coverage, unresolved count, selected
targets and publication state. Change the cadence with
`--progress-interval SECONDS`.

Candidate catalogs, checkpoints and per-target logs are written below
`io/crawler_agent_runs/`. The latest user-facing summary is written atomically
to `data/autonomous_crawler_latest_report.json` and always declares
`publication_state=staging_only`, `catalog_write=false`, and whether the catalog
remained byte-for-byte unchanged.

## Tests

Catalog and crawler policy changes have a small dedicated gate:

```bash
make test-catalog
```

It validates catalog version/data coherence, official-domain selection,
retailer isolation, reviewed-source injection, alias collapsing, manifest
policy, and the absence of the old inferred-value/automatic-git path.
