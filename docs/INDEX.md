# Load Forge — Module Index

## Manuale funzionale

- [`software-function-reference.md`](software-function-reference.md) — guida
  completa in italiano a Bass Match, parametri, topologie, Box Design,
  analisi, progetti, export e catalogo.

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
| `tools/publish_reviewed_catalog_additions.py` | [publish-reviewed-catalog-additions.md](publish-reviewed-catalog-additions.md) | Explicitly reviewed, validation-gated append-only promotion of crawler records |
| `tools/harvest_peerless_official.py` | [harvest-peerless-official.md](harvest-peerless-official.md) | Complete first-party Peerless/Tymphany API crawl into staging |
| `tools/harvest_monacor_official.py` | [harvest-monacor-official.md](harvest-monacor-official.md) | First-party Monacor component crawl with per-product manufacturer verification |
| `tools/harvest_sica_official.py` | [harvest-sica-official.md](harvest-sica-official.md) | Structured first-party SICA/Jensen Store API crawl with brand separation and T/S unit normalization |
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
| — | [acoustic-sampling-optimization.md](acoustic-sampling-optimization.md) | Criterio di Campionamento Acustico Spettrale (Q-constrained), adaptive sampling e ottimizzazione a due stadi per Bass Match / Finder |
| — | [optimizer-manual.md](optimizer-manual.md) | Manuale tecnico dell'ottimizzatore: Compass search, funzione di costo, barriere fisiche, ripple ceiling e griglia segmentata |
| — | [engine-manual.md](engine-manual.md) | Manuale utente del motore acustico: parametri T/S, carichi, condotti, perdite, pilotaggio e interpretazione grafici |
| — | [load-forge-innovations-manual.md](load-forge-innovations-manual.md) | Manuale operativo delle innovazioni e parametri esclusivi: DCCAV, Ripple Cutout, Panel Loading, Forge Score, MOL/MIL, Saddle Coherence |
| — | [social-api-hosting-strategy.md](social-api-hosting-strategy.md) | Strategia Social Share ibrida, Architettura Headless API (FastAPI) per client mobile e Hosting Low-Cost / Zero-Cost (Hetzner, Streamlit Cloud, Oracle Free) |

## SaaS Product Strategy

[saas-strategy.md](saas-strategy.md) records the Open Beta, privacy,
monetization and Free/Pro transition strategy. It separates approved operating
principles from pricing and quota decisions that still require evidence.
[social-api-hosting-strategy.md](social-api-hosting-strategy.md) outlines the
hybrid social sharing, mobile headless API and low-cost hosting architecture.

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
Projects are managed cleanly and safely via standalone `.lfp` file export and import.
The dashboard supports instant download of the complete design state (including T/S
parameters, box alignments, and Bass Match candidate results) and file upload (.lfp, .json,
or .crw) to restore projects or drivers. No project data is retained on servers or in
browser IndexedDB databases, ensuring 100% data privacy and safety.
A dedicated "New / Reset design" action clears all parameters and restores factory defaults.
Share links encode design parameters directly into URL query parameters (?d=...).
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
