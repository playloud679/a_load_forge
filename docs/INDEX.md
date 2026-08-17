# Load Forge — Module Index

Each active source module has a matching document in this directory.  Future
agents should read the doc before source when possible, then keep docs and code
in sync in the same change.

> Required contract: modifying any `src/*.py` requires updating
> `docs/<module>.md` in the same change.  Create the doc if it is missing.

## Active App Path

| Module/File | Doc | Role |
|---|---|---|
| `ui_app.py` | [catalog-maintenance.md](catalog-maintenance.md) for the administrator surface | Streamlit dashboard with a killer-feature-first Bass Match brief and single run action, a selection-aware gray/emerald Box Design CTA directly below the brief, all usable ranked results without a display cap, a lazy collapsible candidate pool, compact 3+3 illustrated load cards, a Bass-reflex Ports submenu for vent/passive-radiator resonators, compact multiselect library filters, progressively disclosed T/S controls, stateful lazy analysis/sidebar tabs, compact plot markers including labelled enclosure tuning frequencies, IndexedDB browser-project autosave, complete `.lfp` v2 Box Design/Bass Match backups and grouped exports. Response-chart overlay layers must filter their data to the zoom window (or clip their marks): unclipped marks past the x-domain make Vega shrink the plot area inside the container |
| `src/__init__.py` | [__init__.md](__init__.md) | Public package exports for acoustic-load helpers |
| `src/acoustics.py` | [acoustics.md](acoustics.md) | Neutral public facade for every lumped and distributed acoustic load |
| `src/dccav.py` | [dccav.md](dccav.md) | Legacy import compatibility and DCCAV-specific theory |
| `src/engine.py` | [engine.md](engine.md) | Physics, alignment, simulation and optimization for every supported load |
| `src/saas.py` | [saas.md](saas.md) | Optional OIDC identity normalization, tenant-safe plan entitlements and Firestore/in-memory project persistence |
| `tests/test_all.py` | source only | Active regression runner for the acoustic-load models and Streamlit workflows |
| `tools/crawl_thiele_small.py` | [crawl_thiele_small.md](crawl_thiele_small.md) | Robots-aware sitemap/seed crawler, T/S parser, unit normalizer, validator and safe database merger |
| `tools/crawl_driver_datasheets.py` | [crawl_driver_datasheets.md](crawl_driver_datasheets.md) | PDF discovery, SHA-256 archive, SQLite provenance index and alias-aware catalog merge |
| `tools/harvest_toutlehautparleur.py` | [harvest_toutlehautparleur.md](harvest_toutlehautparleur.md) | Restartable Safari-assisted harvest of TLHP cone-speaker prices and availability |
| `tools/run_catalog_completion_cycle.py` | [catalog-completion-cycle.md](catalog-completion-cycle.md) | Offline gap planning and restartable Xmax/Pe/Le/price completion cycles |
| `tools/run_high_yield_optional_cycle.py` | [high-yield-optional-cycle.md](high-yield-optional-cycle.md) | Probe-gated source ranking that expands only domains with measured optional-field yield |
| `tools/run_published_spec_batches.py` | [published-spec-batches.md](published-spec-batches.md) | Restartable atomic batches for completing one proven source domain |
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

When changing `src/engine.py` or `src/acoustics.py`:

- update `ui_app.py` controls, metrics and plots for any new/changed parameter
- update `tests/test_all.py`
- update [engine.md](engine.md), [acoustics.md](acoustics.md) and any
  topology-specific document affected by the change
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
UI-only design actions reuse cached solver output and saved alignment state;
they must not trigger a second rerun or restart the enclosure optimizer.
Workspace switching must remain view-only: Bass Match workers are created only
by `Run Bass Match`; closed Project/Candidate sections and inactive sidebar or
analysis tabs must not build their hidden controls, tables or charts. Catalog
matching uses the reusable process pool locally. Streamlit Community Cloud
(`/mount/src`) caps that pool at four workers to bound duplicated catalog
memory and verifies startup within ten seconds before falling back to shared
threads. The parent resolves preset names and sends compact candidate payloads,
so process workers never load a second copy of the external catalogs; Cloud Run
uses threads directly. Catalog
metadata/price summaries and embedded visual CSS use bounded caches, while
large filtered-name lists must not accumulate in the Streamlit cache.
Finder ranking revision 8 invalidates pre-two-stage persisted rows, and every
new result carries hidden T/S and complete box-parameter snapshots that Box
Design reuses verbatim so a catalog refresh or previous loss-factor state
cannot change F3 while opening the selected enclosure.
Legacy sessions with an empty Finder load selection use the active Box Design
load consistently for both ranking and result validation, so a completed
fallback run remains visible instead of being mistaken for changed inputs.
Routine IndexedDB autosaves are fire-and-forget once the active project is in
the sidebar index, so their acknowledgement and `updated_at` value cannot
trigger another full-page rerun. Streamlit stale elements remain fully opaque
during the one required calculation rerun, while autosave errors stay visible.
Creating a new browser project clears every project-owned design, Finder,
comparison, plot and pending-load value before normal defaults are seeded; no
state from the formerly active project may cross that boundary.
A browser project can be duplicated or permanently deleted directly from the
saved-project chooser as well as while it is active. Duplication keeps its
complete design and Bass Match state under a new identity; confirmed deletion
removes both its IndexedDB payload and index entry in one committed browser
transaction. The UI confirms deletion only after that commit. Deleting the
active project also seeds a clean replacement project for autosave.
When saved projects exist, startup always presents the chooser instead of
opening one implicitly. Missing or invalid IndexedDB payloads finish with a
recoverable warning, leaving the chooser available to delete the damaged entry
or create a clean project without entering a Streamlit rerun loop.
Library search, provenance, brand, size, class and price filters retain both
their aggregate values and compact widget selections while Box Design is open,
so returning to Bass Match restores the same candidate pool.
Compact titles preserve driver identity through tab selection/deletion and use
the same deterministic colors as their chart curves. The Finder follows
acoustic brief → `Run Bass Match` → ranked driver/load/box designs. Its raw
driver library is a secondary collapsible candidate pool used to narrow the
search or open one known driver directly. In the default collapsed state, the
brief exposes every enclosure, performance, driver, library and evaluation
constraint in a dense responsive grid, including explicit Off/Any/N/A states;
four metrics share one row, the full-width run action occupies the next compact
row, completion is a transient toast, and ranked
rows scroll within a fixed-height table. During matching, a prominent full-width
slim progress bar temporarily occupies the row immediately below the action,
with its small status caption beneath;
optional/advanced sections are the only persistent controls allowed to extend
the page. Constraint labels and values use readable dashboard sizing. The
Finder replaces the retired soft `Desired F3` preference with an optional hard
`Maximum F3` post-simulation constraint: only designs at or below the limit
remain ranked. Before running the enclosure solver,
the Finder builds a separate eligible pool for each load from reference SPL at
the chosen voltage, driver configuration, T/S validity and required Xmax;
F3, MOL, ripple, excursion and group delay remain post-simulation checks.
Catalog rows sharing a normalized brand/model/impedance identity collapse
before simulation, preferring Load Forge provenance and then price. Successful
load variants collapse again after ranking, so the table exposes one best
design per physical driver. Empty result columns stay hidden.
