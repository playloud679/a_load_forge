# PDF-first driver datasheet library

`tools/crawl_driver_datasheets.py` builds the durable document layer behind the
Load Forge driver catalog. Product pages are discovery sources; linked PDF
datasheets are downloaded, hashed, archived, indexed and parsed.

## Storage model

- `data/datasheets/<sha-prefix>/<sha256>.pdf` stores one copy of each distinct
  PDF. Identical documents exposed by several URLs use the same file.
- `data/driver_datasheets.sqlite3` records document URLs, discovery pages,
  timestamps, parsing status, extracted observations and model aliases.
- `data/manufacturer_drivers.json` is the application-facing catalog for this
  crawler's output — LSDB-free and safe to redistribute (see `docs/presets.md`).
  PDF observations fill missing parameters and attach provenance. Never merge
  observations into `data/loudspeaker_database_drivers.json`; that file is a
  separate, non-redistributable import from loudspeakerdatabase.com.

The PDF archive and SQLite index are reproducible local data and are excluded
from Git because a broad library can become very large.

## Canonical identity and aliases

The manufacturer part number from the product page is retained even when the
PDF uses a marketing name. A PDF observation can be linked to an existing
catalog row only when brand plus all four stable identity fields match within
tight tolerances: `Fs`, `Qts`, `Re` and `Sd`.

Fuzzy matching is never run blindly across the complete catalog. It is limited
to a new PDF-backed observation, prefers an existing curated record, stores the
new model code as an alias and removes only an equivalent provisional
`Web crawler` row. This prevents unrelated OEM drivers from being collapsed.

## Running a crawl

One or more product pages:

```bash
make crawl-datasheets ARGS="\
  --seed https://manufacturer.example/product/woofer-12 \
  --sleep 2"
```

A product sitemap:

```bash
make crawl-datasheets ARGS="\
  --sitemap https://manufacturer.example/sitemap.xml \
  --include '/(woofer|subwoofer|midbass)/' \
  --max-pages 500 --max-pdfs 500 --sleep 2"
```

Known official product URLs already stored in the manufacturer catalog can be
used directly. This is useful when a sitemap is absent, slow or incomplete:

```bash
make crawl-datasheets ARGS="\
  --catalog-domain beyma.com --brand Beyma \
  --max-pages 500 --max-pdfs 500 --sleep 2"
```

`--catalog-domain` is repeatable, accepts the base host or a subdomain, keeps
catalog order and removes duplicate URLs before any request. Only URLs already
associated with matching manufacturer-domain records are selected. The exact
catalog URL also supplies the established brand/model identity; if legacy
duplicates share a URL, real model-like identities outrank generic page-title
boilerplate such as “Products - Manufacturer”.

Catalog URLs may point directly to PDFs (as in the SB Acoustics catalog). In
that case the first response is reused as the document body instead of being
downloaded twice, while its exact catalog record supplies product identity.
On later runs, a direct PDF already present in the content-addressed archive is
resolved through the SQLite URL index before any HTTP request, so retries touch
only missing or failed documents.

Page and PDF requests run through a bounded worker pool (`--workers`, default
6). Request starts for the same host remain spaced by `--per-host-delay`, or by
the legacy `--sleep` value when no explicit host delay is supplied. Downloads
may overlap while SQLite indexing, content-addressed archiving, parsing and
catalog merges remain single-threaded and deterministic.

When a manufacturer omits structured brand metadata, scope the run with an
authoritative brand hint. This also removes a matching `| Brand` suffix from
page-title-derived model names:

```bash
make crawl-datasheets ARGS="\
  --sitemap https://manufacturer.example/sitemap.xml \
  --include '/products/.+/' --brand 'Example Audio'"
```

Already archived PDFs are reloaded from the SQLite observation index and
re-canonicalized with the current product page and brand hint. Incremental
runs therefore still update the catalog instead of silently skipping known
documents.

Use `--reparse-known` after improving extraction rules. It reads the
content-addressed local PDF archive again, refreshes parsed and formerly
rejected index entries, and merges newly recognized fields without downloading
the documents a second time.

Use `--reparse-archive` to process every document already present in the local
content-addressed archive without any network request or seed. Archive reparse
is enrichment-only: unmatched partial observations remain indexed and cannot
create a new catalog driver. This is the preferred first step after adding a
dimension or published-spec parser.

The crawler respects `robots.txt` independently for product pages and external
PDF hosts. Scanned documents without an embedded text layer are archived and
marked rejected until an OCR stage is available; they are not converted into
partial driver records.

When a public product page exposes a broken directory link but the direct file
is known, attach it explicitly without losing product context:

```bash
make crawl-datasheets ARGS="\
  --document 'https://shop.example/driver::https://docs.example/driver.pdf'"
```

## Scope and completeness

No crawler can prove it has found every file on the public web. Coverage is
therefore measured through source domains, product pages visited, PDF URLs,
distinct SHA-256 documents, parsed observations, rejected documents and
failures. Repeated incremental crawls expand the library without duplicating
previously archived files.

Parallel page/PDF fetches isolate recoverable transport failures per URL.
Timeouts, HTTP/URL errors and truncated `IncompleteRead` responses are recorded
in the run report without aborting the remaining batch; a later run resumes
from the content-addressed archive and retries only missing documents.

Some manufacturer applications expose technical drawings only inside their
embedded JSON state. The discovery pass recognizes official
`uploads/products/drawing/*.pdf` assets as well as ordinary PDF anchors; this
is used for B&C SolidWorks drawings whose printed repeated-hole callouts are
otherwise absent from the product-page specification table.

The requested catalog product URL remains the identity anchor even when a
manufacturer redirects an impedance-specific page to a generic product URL.
This prevents a shared chassis drawing from enriching only one impedance
variant; each exact catalog URL encountered in the crawl receives the same
published dimensional evidence independently.
