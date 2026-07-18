# PDF-first driver datasheet library

`tools/crawl_driver_datasheets.py` builds the durable document layer behind the
Load Forge driver catalog. Product pages are discovery sources; linked PDF
datasheets are downloaded, hashed, archived, indexed and parsed.

## Storage model

- `data/datasheets/<sha-prefix>/<sha256>.pdf` stores one copy of each distinct
  PDF. Identical documents exposed by several URLs use the same file.
- `data/driver_datasheets.sqlite3` records document URLs, discovery pages,
  timestamps, parsing status, extracted observations and model aliases.
- `data/loudspeaker_database_drivers.json` remains the application-facing
  catalog. PDF observations fill missing parameters and attach provenance.

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
