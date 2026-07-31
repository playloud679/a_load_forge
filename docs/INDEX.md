# Load Forge — Module Index

Each active source module has a matching document in this directory.  Future
agents should read the doc before source when possible, then keep docs and code
in sync in the same change.

> Required contract: modifying any `src/*.py` requires updating
> `docs/<module>.md` in the same change.  Create the doc if it is missing.

## Active App Path

| Module/File | Doc | Role |
|---|---|---|
| `ui_app.py` | source only | Streamlit dashboard with a killer-feature-first Bass Match brief and single run action, a collapsible candidate pool, compact 3+3 illustrated load cards, a Bass-reflex Ports submenu for vent/passive-radiator resonators, recoverable target/performance/library filters, progressively disclosed T/S controls, contextual design tabs, compact plot markers, IndexedDB browser-project autosave, complete `.lfp` v2 Box Design/Bass Match backups and grouped exports. Response-chart overlay layers must filter their data to the zoom window (or clip their marks): unclipped marks past the x-domain make Vega shrink the plot area inside the container |
| `src/__init__.py` | [__init__.md](__init__.md) | Public package exports for acoustic-load helpers |
| `src/dccav.py` | [dccav.md](dccav.md) | DCCAV/reflex/sealed/infinite-baffle formulas, T/S derivation and lumped acoustic-circuit simulation |
| `src/saas.py` | [saas.md](saas.md) | Optional OIDC identity normalization, tenant-safe plan entitlements and Firestore/in-memory project persistence |
| `tests/test_all.py` | source only | Active regression runner for the acoustic-load models and Streamlit workflows |
| `tools/crawl_thiele_small.py` | [crawl_thiele_small.md](crawl_thiele_small.md) | Robots-aware sitemap/seed crawler, T/S parser, unit normalizer, validator and safe database merger |
| `tools/crawl_driver_datasheets.py` | [crawl_driver_datasheets.md](crawl_driver_datasheets.md) | PDF discovery, SHA-256 archive, SQLite provenance index and alias-aware catalog merge |
| `services/crawler_agent` | [crawler-agent-service.md](crawler-agent-service.md) | Separate policy-bounded Cloud Run Job that autonomously plans direct-site crawls, writes staging artifacts and requires explicit approval for immutable catalog releases |
| `tools/import_vituixcad_database.py` | [import-vituixcad-database.md](import-vituixcad-database.md) | Validated, deduplicated import of the public VituixCAD online driver database into a separate optional tier |
| `tools/import_heritage_drivers.py` | [import-heritage-drivers.md](import-heritage-drivers.md) | Traceable import of Altec Technical Letter 267B and official Pioneer/TAD heritage T/S tables |
| `tools/import_speakerboxlite_database.py` | [import-speakerboxlite-database.md](import-speakerboxlite-database.md) | Physically validated import of the public Speaker Box Lite community database into a separate optional tier |
| `tools/compare_afw_sealed.py` | [afw_validation.md](afw_validation.md) | Read-only AFW v2 sealed/BP4/BP6 parser, response diagnostics and identical-driver projection bridge |
| `tools/generate_afw_dccav.py` | [afw_validation.md](afw_validation.md) | Write-side counterpart: clones a verified DCAAV `.afw` template and injects a Load Forge DCCAV `.lfp` design's driver/chamber values |

## SaaS Product Strategy

[saas-strategy.md](saas-strategy.md) records the Open Beta, privacy,
monetization and Free/Pro transition strategy. It separates approved operating
principles from pricing and quota decisions that still require evidence.

## Scraping Playbook

[scraping-strategies.md](scraping-strategies.md) ranks the manufacturer/
retailer scraping approaches used to build `data/manufacturer_drivers.json`
by yield-per-effort — read it before starting a new site instead of
re-deriving the same routes from scratch.

## Manufacturer Database Audit

[manufacturer-database-status.md](manufacturer-database-status.md) is the
generated current status report for catalog coverage, prices, provenance,
quality, deduplication and remaining manufacturer gaps. Regenerate it with
`tools/generate_manufacturer_database_report.py`; implementation and usage are
documented in
[manufacturer-database-report.md](manufacturer-database-report.md).

## Data Flow

```text
T/S parameters -> derived driver components -> selected acoustic-load alignment
        -> acoustic impedance network -> response arrays -> plots / CSV
```

## Acoustic-load UI Contract

When changing `src/dccav.py`:

- update `ui_app.py` controls, metrics and plots for any new/changed parameter
- update `tests/test_all.py`
- update [dccav.md](dccav.md)
- run a Streamlit `AppTest` for the touched UI path

The UI keeps selection, primary-action and main-response semantics emerald,
with neutral-gray secondary guidance and a fully black sidebar. Information
bands must never fall back to Streamlit blue: actionable selection instructions
use emerald, while secondary instructions use gray. Load cards are fully
clickable with overlaid labels, a checked active state and keyboard focus; the
full-width 1200×100 app header preserves its native ratio and the active design
uses a 44 px topology chip. The 420 px main response chart keeps its controls
above the fold on desktop viewports; Box Design does not repeat the active-load
heading already conveyed by its editable tab and sidebar. Visibility, duplicate
and close are fixed-position compact icons inside every tab, never a separate action row.
Compact titles preserve driver identity through tab selection/deletion and use
the same deterministic colors as their chart curves. The Finder follows
acoustic brief → `Run Bass Match` → ranked driver/load/box designs. Its raw
driver library is a secondary collapsible candidate pool used to narrow the
search or open one known driver directly. In the default collapsed state, the
brief exposes every enclosure, performance, driver, library and evaluation
constraint in a dense responsive grid, including explicit Off/Any/N/A states;
metrics and action share one row, completion is a transient toast, and ranked
rows scroll within a fixed-height table. During matching, a prominent full-width
progress bar temporarily occupies the row below the brief;
optional/advanced sections are the only persistent controls allowed to extend
the page. Constraint labels and values use readable dashboard sizing. The
Finder has no `Desired F3` input: that former soft optimizer preference did not
provide a dependable ranking constraint. Before running the enclosure solver,
the Finder builds a separate eligible pool for each load from reference SPL at
the chosen voltage, driver configuration, T/S validity and required Xmax;
F3, MOL, ripple, excursion and group delay remain post-simulation checks.
Catalog rows sharing a normalized brand/model/impedance identity collapse
before simulation, preferring Load Forge provenance and then price. Successful
load variants collapse again after ranking, so the table exposes one best
design per physical driver. Empty result columns stay hidden.
