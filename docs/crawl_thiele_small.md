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
The same observation parser retains source-published physical dimensions
(overall/cutout diameter, depth/mounting depth, bolt circle, mounting holes and
weight) plus future-facing numeric specifications (nominal impedance,
sensitivity, voice-coil diameter, Xmech, reference efficiency, magnet mass and
gap flux). These fields require explicit labels and physical units where
applicable; they are never inferred. Ambiguous responsive/PDF column pairing is
disabled for these fields.
One-way values written as `X Max +/- N mm` are normalized to the positive
excursion magnitude `N`. An inline production tolerance after `Fs`, such as
MISCO's `Fs (Hz) +/- 15% 23`, is skipped so the following value (`23 Hz`) is
stored as resonance frequency; this rule is deliberately limited to `Fs` so
signed excursion notation keeps its existing meaning.
Manufacturer wording that explicitly reports `Linear coil travel (p-p)` is
stored as one-way `Xmax = travel / 2`, with the formula and source field kept
in `website_fields.derivations`. Program, continuous-program, maximum and peak
power are not substituted for the AES/RMS/rated thermal power stored as `Pe`.
When a responsive product page also repeats program or continuous power inside
a prose description or layout-derived row, an explicit AES, RMS, nominal or
rated-power observation outranks it regardless of extraction method. This
preserves Eighteen Sound's nominal thermal rating instead of its 2x continuous
figure.
Footnote markers after labels (`Xmax*`, `Power Capacity AES¹`) are ignored.
18Sound-style coaxial rows are component-aware: `LF Nominal Power Handling`
is accepted as the simulated cone driver's `Pe`, an intervening numeric HTML
footnote is skipped, and adjacent HF or continuous/program ratings are not
substituted.
Eighteen Sound reuses one public model name for genuine 2/4/8/16-ohm variants.
The crawler appends the page's published nominal impedance to that model
identity (for example `18LW2400 8Ω`) so variants remain independently visible
and can still deduplicate against older rows through the runtime identity.
Localized/brand-specific power rows are recognized where their meaning is
unambiguous: Bomber `Potência (RMS) ... W_RMS`, Eminence `Watts N W`, and
Accuton `Power handling P N W`. MISCO's explicitly rated
`Rated Power IEC268-5 (W)` row is treated as thermal `Pe`.

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
normalized as well. Written-out area units such as `square inches`, `square
centimeters` and `square meters` are converted too. For physical quantities,
an explicit recognized unit outranks a unitless candidate from a higher-level
layout parser; extraction-method priority is used after unit quality.

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

Wavecor's official HTML uses one matrix for several related part numbers, with
separate before/after-burn-in columns and shared cells for equal values. The
crawler preserves table colspans, selects the published after-burn-in design
values and expands shorthand groups such as `MR120BD01/03` or
`WF182BD09 and WF182BD11` into distinct model records. Every expanded record keeps the official page URL and source group;
retailer titles or measurements are not used for this expansion.

Nominal diameter is stored as `published_specs.nominal_diameter_in`, distinct
from mechanical `overall_diameter_mm`. A label such as “nominal overall
diameter: 12 in” is a published size class and is never converted into a
304.8 mm frame measurement. The mechanical field requires an unqualified,
explicit overall/frame diameter.

Celestion-style `Cut-out diameter` and `Mounting hole dimensions` labels are
recognized. The latter is accepted as a hole diameter only when the source
also supplies an explicit length unit; the raw label, unit and value remain in
field provenance.

A bare `Depth` remains rejected in general. It is accepted as driver depth only
inside an explicit `MOUNTING INFORMATION` section, stopping before construction,
packaging or frequency-response sections. Weight-unit parsing prefers `lb/lbs`
over the single-letter litre token, so `Net Weight 5.3 lbs` cannot be mistaken
for an unsupported `l` unit; shipping weight remains excluded.

Beyma datasheets split `Baffle cutout diameter` and its `Front mount` value
across consecutive lines. That pair is recognized only inside the same
explicit mounting-information section; the generic `Front mount` phrase is not
accepted elsewhere. The section terminates at Beyma's company footer or the
following Thiele-Small notes, so unrelated PDF pages remain out of scope.

SB Acoustics CorelDRAW datasheets expose their dimension callouts as positioned
PDF text rather than labelled table rows. For recognized SB model signatures,
the parser retains text coordinates and rotation and maps only stable drawing
roles: rotated side-view overall/cutout callouts, explicit diameter-and-count
hole callouts, the upper bolt-circle callout and the paired horizontal overall/
rear-of-baffle depths. These measurements are tagged `pdf.drawing`; circular
overall diameter is left blank when the frame drawing does not print the
diameter glyph, and no nominal-size estimate is used.

PHL Audio's `Speaker net mass` and `Max overall dimension (on ears)` labels map
to net driver weight and maximum frame diameter. Its `Bolt number & Metric
diameter: 4x M5` row supplies a four-hole count only: `M5` is the specified
fastener, not an asserted drilled-hole diameter.

Oberton's responsive pages place the six mounting labels in one HTML column
and all six values in the adjacent column. The parser pairs that exact ordered
`MOUNTING INFORMATION` block, including hole count and overall depth. When a
slotted frame publishes two orthogonal pitch diameters such as `438/441 mm`,
the scalar bolt-circle field stores the larger envelope and provenance retains
the complete two-value source string; slot width is not recast as hole diameter.

P.Audio datasheets have a documented caption swap in their mounting table: the
row labelled `Mounting Hole Diameter` contains the bolt-circle value, while the
`Bolt Circle Diameter` row contains hole count and size. The parser therefore
uses the independent `PCD ... mm` drawing callout for pitch circle, takes
diameter/cutout/depth/net weight from their direct rows, and takes hole count
from the `N × Ø...` tuple. A circular hole size is retained only for one-number
tuples; an oval such as `6.5×10 mm` has no fabricated scalar diameter.

Bomber's official PDF drawings publish a keyed `A`--`F` dimension table. The
parser records `C` as overall diameter and `D` as baffle cutout. `A` and `B`
are the axial extents to opposite flange faces; because the letter carrying
the larger extent changes with the frame drawing, their larger published value
is overall depth and the smaller is rear-of-baffle mounting depth. Both raw
`A/B` values and the `pdf.drawing` provenance are retained. Magnet dimensions
`E/F` are deliberately ignored.

B&C product pages embed official SolidWorks drawing PDFs outside ordinary HTML
anchors. For PDFs whose metadata identifies `BCSPEAKERS`, the drawing parser
accepts only explicit repeated-hole callouts such as `Ø5 (4x)` and `B.C.
Ø142`: these yield hole diameter, hole count and bolt circle with
`pdf.drawing` provenance. Historical drawing variants such as `6.20(x8)`,
`8x 6.5 min`, `N.8 x 7` and `(x8) 7 min` are normalized only when the PDF
metadata identifies B&C or the archive URL is the official B&C drawing path.
The callout may follow another printed dimension on the extracted line (for
example `2,5  6,6(x8)`); numeric boundaries keep that preceding dimension out
of the match. The same glyph pattern in an unrelated PDF is ignored.
Implausible dimension-like tokens are skipped instead of masking a later valid
callout in the same official drawing.

The crawler can derive any missing electrical/mechanical Q relation:
`Qts` from `Qms+Qes`, `Qms` from `Qts+Qes`, or `Qes` from `Qts+Qms`;
`Qms` can also come from `Fs+Mms+Rms`, and `Vas` from `Cms+Sd`.
Published or derived `Qes` is retained in the operational driver record, not
only in raw provenance. A record is accepted only when the six
simulation inputs `Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd` are present after
derivation, values are physically bounded, `Qms > Qts`, and extraction
confidence reaches `--min-confidence` (default `0.75`).

It can also derive `Sd` from a published effective diaphragm radius/diameter,
from `Vd+Xmax`, or by inverting the `Vas+Cms` relationship. `Re` can be derived
from `Qes+BL+Fs+Mms`. Nominal frame diameter is never substituted for effective
piston diameter. HTTPS requests use certifi and securely fall back to the
system `curl` trust store for legacy certificate chains; certificate checking
is never disabled.

Nominal inch sizes are parsed as complete values, including mixed fractions:
`6-1/2"` becomes 6.5 rather than 2, and `1-1/8"` becomes 1.125. A bare numeric
model prefix is used only when its proposed frame size is compatible with the
record's `Sd`-equivalent effective diameter. This prevents metric family codes
such as Scan-Speak `15W` from becoming 15-inch drivers while preserving
compatible pro-driver codes such as `18FT`.

Every preset stores the original URL, timestamp, extraction method,
confidence and raw measurement labels/units in `website_fields`. Its catalog
source is `Web crawler`, while the exact origin remains attached to the row.
When structured product metadata omits model/MPN/SKU, a visible `Model #`,
`Model No.` or `Model Number` specification row supplies the stable model
identity before falling back to the descriptive page title.
When metadata falls back to the HTML title, a trailing `| Brand`, `– Brand` or
`— Brand` site-name suffix is removed from the model identity before merge.
Stereo Integrity's numeric WooCommerce SKU ids are replaced with the official
product H1, which is the public model name shown on the page.
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
and tweeters are pruned by inspecting both stable model code and descriptive
product title: their pages can contain valid-looking T/S values from related
products but they are not standalone low-frequency load candidates.

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
