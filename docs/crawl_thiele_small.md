# Generic Thiele/Small crawler

`tools/crawl_thiele_small.py` discovers manufacturer loudspeaker product
pages, extracts validated Thiele/Small parameters and merges compatible
presets into `data/manufacturer_drivers.json` by default — the LSDB-free
catalog safe to redistribute publicly (see `docs/presets.md`). Point
`--output` elsewhere for a one-off crawl; never point it at
`data/loudspeaker_database_drivers.json`, which is a separate, non-redistributable
import from loudspeakerdatabase.com.

## Discovery

The crawler accepts repeatable inputs:

- `--seed URL`: product or catalog page; internal links are followed breadth
  first up to `--max-depth`
- `--sitemap URL`: XML `urlset` or nested `sitemapindex`
- `--allow-domain DOMAIN`: explicit domain allow-list; otherwise domains are
  derived from seeds and sitemaps
- `--include REGEX` / `--exclude REGEX`: limit large catalogs to likely driver
  paths

It removes fragments, percent-encodes characters that `http.client` rejects
(such as spaces in datasheet filenames), rejects non-HTTP URLs, remains on
allowed domains,
respects `robots.txt`, uses a descriptive user agent, sleeps between requests
and stops at `--max-pages`. Progress is written atomically to
`data/thiele_small_crawler_checkpoint.json`; omit `--fresh` to resume it.

## Extraction and validation

HTML pages are read from visible text and schema.org JSON-LD, including
`Product.additionalProperty`. PDF datasheets are supported when `pypdf` is
installed. Recognized fields are `Fs/Fo/F0`, `Vas`, `Qts`, `Qms`, `Qes`,
`Re/ReVc`, `Sd`,
`Le/L1kHz/Le1k` (including “inductance of the voice coil”),
`Le10k/L10kHz` (the optional 10 kHz inductance some pro-audio datasheets
publish alongside the usual 1 kHz value, stored separately as `le10k_mh` —
display-only, not used by the simulator),
`Xmax/X Max/excursion limit`, `Pe/Pmax/Pwr` plus AES/RMS/rated-power labels,
`Mms/Mmd`, `Cms`, `BL` and
mechanical `Rms`. Storefront synonyms are folded in: `Qt` counts as `Qts`,
`Equivalent Air Volume` as `Vas` and `Diaphragm Area` as `Sd`, and a stray
closing parenthesis directly after a label (`... (Qms) 8.82` rendered as
`Qms)\n8.82`) is tolerated. Markaudio's `L1kHz` value is treated as the voice-coil
inductance used by the simulator, while its nominal `Pwr` is stored as `Pe`.
One-way values written as `X Max +/- N mm` are normalized to the positive
excursion magnitude `N`.
Manufacturer wording that explicitly reports `Linear coil travel (p-p)` is
stored as one-way `Xmax = travel / 2`, with the formula and source field kept
in `website_fields.derivations`. Program, continuous-program, maximum and peak
power are not substituted for the AES/RMS/rated thermal power stored as `Pe`.
Footnote markers after labels (`Xmax*`, `Power Capacity AES¹`) are ignored.
Localized/brand-specific power rows are recognized where their meaning is
unambiguous: Bomber `Potência (RMS) ... W_RMS`, Eminence `Watts N W`, and
Accuton `Power handling P N W`.

Units are converted to the Load Forge schema:

- frequency: kHz → Hz
- volume: m³/ft³ → litres
- area: m²/mm²/in² → cm²
- inductance: H/µH → mH
- excursion: m/cm/in → mm
- power: kW → W
- mass: kg/mg → g
- compliance: m/N or µm/N → mm/N

Comma-separated thousands in English-language values (`2,000 W`) are kept as
thousands, while ordinary decimal-comma values remain decimals. Free-text
power extraction requires an explicit `W` or `kW` unit in text, tables and
structured measurement pairs; this prevents nearby voice-coil diameters,
sensitivity or impedance values from becoming false power ratings. For power,
an explicit-unit text measurement outranks an unqualified table candidate.
The value and its unit may be split across adjacent HTML table lines.

Both ASCII and typographic area/volume notation are accepted (`cm2`/`cm²`,
`ft3`/`ft³`), including the `Surface Area of Cone` label used by storefront
specification tables. Spaced manufacturer notation (`m ²`), `K mm/2`
(including `K/mm/2`, thousands of square millimetres) and `K Hz` are
normalized as well.

Literal control characters inside otherwise valid JSON-LD strings are parsed
in tolerant mode so that one dirty product description does not discard the
brand and MPN for the entire block. HTML superscripts remain visible to the
text extractor (`ft.<sup>3</sup>`, `cm<sup>2</sup>`), preventing cubic-foot
values from silently falling back to litres. SPA hydration objects shaped as
`{label, value, units}` are extracted directly.

Table extraction supports both layout-preserved PDF rows (`description`,
symbol, unit, value) and responsive HTML that renders all labels in one column
and all values in an adjacent column, both for T/S and general specification
blocks. A known PHL embedded-font substitution
that exposes the ohm glyph as `W` is accepted only for a DC-resistance row.

The crawler can derive `Qts` from `Qms+Qes`, `Qms` from `Qts+Qes` or
`Fs+Mms+Rms`, and `Vas` from `Cms+Sd`. A record is accepted only when the six
simulation inputs `Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd` are present after
derivation, values are physically bounded, `Qms > Qts`, and extraction
confidence reaches `--min-confidence` (default `0.75`).

It can also derive `Sd` from a published effective diaphragm radius/diameter,
from `Vd+Xmax`, or by inverting the `Vas+Cms` relationship. `Re` can be derived
from `Qes+BL+Fs+Mms`. Nominal frame diameter is never substituted for effective
piston diameter. HTTPS requests use certifi and securely fall back to the
system `curl` trust store for legacy certificate chains; certificate checking
is never disabled.

Every preset stores the original URL, timestamp, extraction method,
confidence and raw measurement labels/units in `website_fields`. Its catalog
source is `Web crawler`, while the exact origin remains attached to the row.
When metadata falls back to the HTML title, a trailing `| Brand`, `– Brand` or
`— Brand` site-name suffix is removed from the model identity before merge.
Generic archive headings such as `Discontinued product` are replaced by the
model encoded in the product URL slug (with a leading numeric content ID
removed), so archived products do not collapse onto one false deduplication
key. During a source refresh, a record whose identity changed is replaced by
matching source URL as well as by brand/model key.
For PDFs with no embedded title, filename fallbacks also remove trailing
`SpecSheet`/`Datasheet` markers and accidental spreadsheet extensions.

## Safe database merge

Brand and model form the deduplication key. By default an existing row keeps
all non-empty values; the crawler only fills missing optional parameters and
records the additional source URL. `--overwrite` explicitly replaces a
matching row. Output and checkpoints use a temporary file plus atomic rename,
so an interrupted write cannot truncate the database.

`--refresh-source "Manufacturer website"` is narrower than `--overwrite`: it
replaces a matching row only when that row already has the named source. This
lets an HTML recrawl correct earlier HTML extraction without replacing a more
authoritative PDF or curated record. During this scoped refresh, obvious kits
and tweeters are pruned: their pages can contain valid-looking T/S values from
related products but they are not standalone low-frequency load candidates.

When duplicate measurements have the same extraction priority, fields that
require units prefer the occurrence with an explicit recognized unit. This is
important for pages that present a malformed legacy table before a corrected
specification table.

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

For SoundImports, use the catalog-aware wrapper rather than crawling all
retailer pages. It reads the already cached brand/MPN manifest, limits the
crawl to driver-like products and writes explicit quality rejections:

```bash
.venv/bin/python tools/harvest_soundimports_drivers.py --fresh --sleep 0.2
```
