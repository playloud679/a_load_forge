# Load Forge — Module Index

Each active source module has a matching document in this directory.  Future
agents should read the doc before source when possible, then keep docs and code
in sync in the same change.

> Required contract: modifying any `src/*.py` requires updating
> `docs/<module>.md` in the same change.  Create the doc if it is missing.

## Active App Path

| Module/File | Doc | Role |
|---|---|---|
| `ui_app.py` | source only | Streamlit dashboard with compact 3+3 illustrated load cards, a Bass-reflex Ports submenu for vent/passive-radiator resonators, target/performance/library Finder flow, contextual design tabs, T/S controls, plots, project state and CSV export.  Response-chart overlay layers must filter their data to the zoom window (or clip their marks): unclipped marks past the x-domain make Vega shrink the plot area inside the container |
| `src/__init__.py` | [__init__.md](__init__.md) | Public package exports for acoustic-load helpers |
| `src/dccav.py` | [dccav.md](dccav.md) | DCCAV/reflex/sealed/infinite-baffle formulas, T/S derivation and lumped acoustic-circuit simulation |
| `tests/test_all.py` | source only | Active regression runner for the acoustic-load models and Streamlit workflows |
| `tools/crawl_thiele_small.py` | [crawl_thiele_small.md](crawl_thiele_small.md) | Robots-aware sitemap/seed crawler, T/S parser, unit normalizer, validator and safe database merger |
| `tools/crawl_driver_datasheets.py` | [crawl_driver_datasheets.md](crawl_driver_datasheets.md) | PDF discovery, SHA-256 archive, SQLite provenance index and alias-aware catalog merge |
| `tools/compare_afw_sealed.py` | [afw_validation.md](afw_validation.md) | Read-only AFW v2 sealed/BP4/BP6 parser, response diagnostics and identical-driver projection bridge |
| `tools/generate_afw_dccav.py` | [afw_validation.md](afw_validation.md) | Write-side counterpart: clones a verified DCAAV `.afw` template and injects a Load Forge DCCAV `.lfp` design's driver/chamber values |

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
and active-load summary above the fold on desktop viewports. The Finder follows
target enclosure → performance goal → candidate library, keeps its primary
action pinned to the sidebar bottom, and hides empty result columns.
