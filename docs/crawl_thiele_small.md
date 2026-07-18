# Generic Thiele/Small crawler

`tools/crawl_thiele_small.py` discovers loudspeaker product pages, extracts
validated Thiele/Small parameters and merges compatible presets into
`data/loudspeaker_database_drivers.json`.

## Discovery

The crawler accepts repeatable inputs:

- `--seed URL`: product or catalog page; internal links are followed breadth
  first up to `--max-depth`
- `--sitemap URL`: XML `urlset` or nested `sitemapindex`
- `--allow-domain DOMAIN`: explicit domain allow-list; otherwise domains are
  derived from seeds and sitemaps
- `--include REGEX` / `--exclude REGEX`: limit large catalogs to likely driver
  paths

It removes fragments, rejects non-HTTP URLs, remains on allowed domains,
respects `robots.txt`, uses a descriptive user agent, sleeps between requests
and stops at `--max-pages`. Progress is written atomically to
`data/thiele_small_crawler_checkpoint.json`; omit `--fresh` to resume it.

## Extraction and validation

HTML pages are read from visible text and schema.org JSON-LD, including
`Product.additionalProperty`. PDF datasheets are supported when `pypdf` is
installed. Recognized fields are `Fs`, `Vas`, `Qts`, `Qms`, `Qes`, `Re`, `Sd`,
`Le`, `Xmax`, `Pe/Pmax`, `Mms/Mmd`, `Cms`, `BL` and mechanical `Rms`.

Units are converted to the Load Forge schema:

- frequency: kHz → Hz
- volume: m³/ft³ → litres
- area: m²/mm²/in² → cm²
- inductance: H/µH → mH
- excursion: m/cm/in → mm
- power: kW → W
- mass: kg/mg → g
- compliance: m/N or µm/N → mm/N

Both ASCII and typographic area/volume notation are accepted (`cm2`/`cm²`,
`ft3`/`ft³`), including the `Surface Area of Cone` label used by storefront
specification tables.

The crawler can derive `Qts` from `Qms+Qes`, `Qms` from `Qts+Qes` or
`Fs+Mms+Rms`, and `Vas` from `Cms+Sd`. A record is accepted only when the six
simulation inputs `Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd` are present after
derivation, values are physically bounded, `Qms > Qts`, and extraction
confidence reaches `--min-confidence` (default `0.75`).

Every preset stores the original URL, timestamp, extraction method,
confidence and raw measurement labels/units in `website_fields`. Its catalog
source is `Web crawler`, while the exact origin remains attached to the row.

## Safe database merge

Brand and model form the deduplication key. By default an existing row keeps
all non-empty values; the crawler only fills missing optional parameters and
records the additional source URL. `--overwrite` explicitly replaces a
matching row. Output and checkpoints use a temporary file plus atomic rename,
so an interrupted write cannot truncate the database.

Always inspect a new source first:

```bash
.venv/bin/python tools/crawl_thiele_small.py \
  --seed https://manufacturer.example/woofers/driver-12 \
  --fresh --dry-run --max-pages 5
```

Crawl a product sitemap and populate the normal database:

```bash
.venv/bin/python tools/crawl_thiele_small.py \
  --sitemap https://manufacturer.example/sitemap.xml \
  --include '/(woofer|subwoofer|midbass|speaker)/' \
  --max-pages 500 --sleep 2
```

Resume after an interruption by repeating the command without `--fresh`.
Use a separate `--output` and `--checkpoint` while qualifying a new source.
