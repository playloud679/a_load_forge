# Manufacturer/retailer scraping strategies — ranked playbook

Distilled from the 2026-07-21/22 sessions that grew `data/manufacturer_drivers.json`
from ~1200 to ~3200+ drivers across 40+ brands, plus a full Parts Express
catalog + price harvest. Ranked by yield-per-effort, from what to try first
down to what rarely works. Companion to `docs/crawl_thiele_small.md`
(the tool contract) — this file is about *which route* to reach for on a
new site, not the tool's API.

## Tier S — try these first, huge yield for the effort

### 1. Reverse-engineer a hidden JSON/REST API from the site's own JS bundle
The single highest-leverage move this session. Modern storefronts (NetSuite
SuiteCommerce, custom Node/Laravel backends) often expose a public REST
endpoint that the page's own JavaScript calls to render content — even when
the page itself is an empty SPA shell to `curl`.

**How to find it:** fetch the site's main JS bundle(s) and `grep` for
`fetch(`, `axios`, `/api/`, or parameter names hinted at by the UI (search
boxes, filters). Confirm with a plain `curl` against candidate query strings
before committing.

**Worked examples:**
- **Parts Express**: `curl`'d an empty `<div id="main">` shell even with a
  Googlebot UA. The ~1.1MB `shopping.js` bundle referenced `/api/items`.
  Reverse-engineering `fieldset=details` (trial-and-error against
  `search`/`extended`/`full`/`item`/`product` — NetSuite silently drops
  unrecognized param *values*, not just names, so a wrong guess looks
  identical to "unsupported") unlocked ~85 fields per item including
  pre-typed T/S parameters *and* price, brand, and canonical URL — for
  **every brand the retailer carries**, not just one.
- **REDCATT**: a stale sitemap's very last `<loc>` entry (everything else
  404'd) was `.../api/v1/products` — a fully paginated, structured JSON API
  nobody meant to leave world-readable in a sitemap.

**Why it's S-tier:** one API call replaces dozens of HTML-parsing edge
cases, gives clean typed values (no regex/unit-guessing), and often exposes
the *entire* multi-brand catalog behind one retailer, not just the brand
you went looking for.

### 2. Full-catalog sitemap + bulk request, not category browsing
When the listing/search UI is JS-only but a sitemap exists, don't bother
crawling categories — grab the sitemap, regex-filter to product-URL shapes,
and hit every one directly (via the API from #1, or the page itself if it's
server-rendered per-product even though the *list* isn't).
- Parts Express: `sitemap_pages.xml` (13k+ URLs) filtered to a
  `-\d{3}-\d{2,5}/?$` SKU-suffix pattern → 8632 product URLs, harvested
  directly against the API. (First pass under-filtered by ~1200 URLs whose
  slugs didn't match that exact pattern — always sanity-check the regex
  catches everything by diffing matched vs. unmatched sitemap entries,
  don't assume one SKU-suffix shape covers 100% of a catalog.)
- Rockford Fosgate, RCF, DS18: same move — sitemap or `products.json`
  (Shopify) gives the full URL list up front instead of discovering it via
  BFS link-following, which wastes budget wandering through
  amps/cables/accessories before ever reaching a driver.

## Tier A — reliable, worth the setup cost

### 3. Test one direct product URL by hand before writing a brand off
The JS-only *listing/search* page is not proof the *product detail* page is
also JS-only — they're frequently built on different rendering paths.
- **RCF**: category browser is 100% client-side AJAX (Liferay portlet, zero
  product links in raw HTML) — but `products/product-detail/<slug>` pages
  are fully server-rendered with a complete T/S table. Found only because
  the user pasted one such URL by hand.
- **Ciare**: same shape — category page is JS/AJAX, but
  `products/<cat>/<inches>/<impedance>/<name>` product pages are
  server-rendered (Remix), see #4.
Moral: a "dead end" verdict from probing only the homepage/category page is
unreliable. Always try a real product URL (from a search engine, a user
link, or a guessed slug) before concluding a brand is unreachable.

### 4. Extract JSON embedded in `<script>` hydration blobs (SPA state, not JSON-LD)
Frameworks like Remix/Nuxt/Next sometimes server-render the page but stash
the *complete* underlying data model as a JSON blob assigned to a
`window.*` global (`window.__remixContext = {...}`), separate from
`application/ld+json`. The visible HTML only shows a curated subset; the
blob has everything, including fields the rendered page never displays.
- **Ciare, B&C Speakers** (same backend platform, confirmed via a shared
  `"sites":[...]` tag inside the blob): full T/S data for every parameter,
  keyed as `{"label": "Fs", "value": 122, "units": {"default": "Hz"}}`.
  Implemented generically in `tools/crawl_thiele_small.py` as
  `embedded_js_objects()` (regex-extract the `{...}` span after
  `window.SOMETHING =`, `json.loads` it) plus a shape-matcher added to
  `jsonld_measurements()` for the `{label, value, units}` pattern — reusable
  for any other site on a similar platform, not a one-off hack.
- Category/listing pages on the *same* platform carry the **entire product
  list** in their own hydration blob too, sidestepping a broken client-side
  search UI entirely (used this to enumerate every Ciare/B&C product
  without ever running their JS search).
- **Caveat**: this is not a universal "JS site" unlock — checked several
  other JS-heavy sites (Monacor, Focal, Solen, RCF's listing page,
  HiFiCollective) for the same `window.__NUXT__`/`__NEXT_DATA__`/
  `__remixContext`/`__INITIAL_STATE__` pattern; none of them use it. It only
  helps sites built on a framework that does this specific style of SSR
  hydration.

### 5. Standard HTML crawl with PDF-datasheet fallback (the default path)
Still the bread-and-butter route for most manufacturer sites:
product-listing page → product page → (if T/S isn't in the visible HTML)
follow the linked PDF datasheet, parse with `pypdf`. Handles the largest
number of brands this session (SB Acoustics, Eminence, Visaton, Accuton,
AudioTechnology, Supravox, Atohm, DS18, Rockford Fosgate, Madisound...).
Success depends entirely on the site being genuinely server-rendered —
verify with one `curl` before writing a multi-seed crawl.

## Tier B — useful multipliers, not discovery methods on their own

### 6. Parallelize a large, known-finite harvest
Once you know exactly which N URLs/API calls you need, running them
sequentially with a polite sleep is needlessly slow for large N. Splitting
into k independent workers (own URL slice, own checkpoint file, same sleep
per-worker) cuts wall-clock time ~k× without hammering the target harder
per-connection than a single fast browsing session would.
- Parts Express: single-threaded estimate ~50 min for 8632 items → 4
  workers at 0.4s each finished in ~13 min. Merge checkpoints afterward
  (`tools/merge_partsexpress_harvest.py` reads all of them).
- **Precompute per-candidate match data before an O(N×M) matching loop.**
  Found a real perf bug this way: `enrich_driver_prices.py`'s
  `match_score()` recomputes `tokenize`/`model_compacts`/`brand_compacts`
  for *every* candidate on *every* product — all three depend only on the
  candidate. Precomputing once turned a 9-minute matching pass (8400
  candidates × several thousand price records) into 34 seconds.

### 7. Spoof a browser User-Agent for sites that soft-block scrapers
Some sites don't outright block a scraper UA — they serve a *fake* 200/404
with real page chrome but no real content, or genuinely 404 even the
homepage. A plain Chrome UA string (no cookies/JS needed) is often enough.
- **Madisound**: default crawler UA got a real HTTP 404 status with a
  real-looking (but decoy) page body on *every* URL including the homepage.
  `--user-agent "Mozilla/5.0 ... Chrome/120..."` fixed it immediately, no
  other headers needed.
- This is *not* the same as a real bot-defense block (Cloudflare-style
  403s from Falcon Acoustics, PRV Audio, Skar Audio, Wagner Online, The
  Loudspeaker Kit did not budge for any UA/header combination tried — don't
  waste time iterating headers against a real WAF).

### 8. A retailer's brand-name search (`?q=<brand>`) as a discovery shortcut
If a retailer's API/search supports free-text queries, searching for a
specific manufacturer name surfaces that brand's catalog slice without
needing to enumerate the whole site. Cheap way to check "does this
retailer carry brand X" before deciding whether to do a full harvest.
- Used to confirm Parts Express carries Tang Band, Wavecor, Morel, Aurum
  Cantus, GRS — several of which were **dead ends on their own official
  sites** (Tang Band's domain is gone; Wavecor's sitemap is stale; Morel's
  product grid is JS-only). One retailer search substituted for four
  separate manufacturer-site investigations.
- **Caveat**: it's fuzzy keyword search, not a brand filter — always
  post-filter results by the exact brand field in the returned record
  (`q=Fountek` returned a GRS product that merely mentioned "Fountek" in
  its description; 0 of the 4 hits were real Fountek items).

### 9. Web search for the *correct* domain before guessing
Blind `https://www.<brand>.com` guessing wastes round-trips on wrong
domains, redirects, and parked pages. A single web search resolved several
brands (STX → `stx.pl`, not the domains being guessed; Redcatt →
`redcatt.net`) in one shot after multiple failed manual guesses.

## Tier C/F — rarely worked, low priority to retry

- **JS-rendered category/search UI with no exposed API and no hydration
  blob**: Monacor, Focal, Solen, HiFiCollective's product grids, Ciare's
  own listing page, RCF's listing portlet. Genuinely needs a headless
  browser; not worth repeated probing with plain HTTP tools.
- **Real bot-defense (Cloudflare etc.) returning hard 403s**: Falcon
  Acoustics, PRV Audio, Skar Audio, Wagner Online, The Loudspeaker Kit,
  HiFonics, Acoustic Elegance. No UA/header combination helped; don't keep
  retrying these without a different approach (proxy/headless browser),
  it's not a UA-sniffing problem.
- **Image-scanned or cipher-font PDFs**: diyaudiocart.com (photographed/
  scanned datasheet, 0 extractable chars via `pypdf`), Scan-Speak (custom
  font encoding with no ToUnicode map). Needs OCR; not attempted.
- **Dead/parked/nonexistent domains**: Tang Band's own `.com.tw` (NXDOMAIN),
  PowerBass (parked on HugeDomains), several guessed regional distributor
  domains. A quick `nslookup`/`curl -o /dev/null -w '%{http_code}'` check
  rules these out in seconds — do that before any deeper investigation.
- **Brands that simply don't publish T/S data**: most consumer car-audio
  brands (Kicker, Fi Car Audio, JL Audio, Hertz — publishes everything
  *except* Sd on every product checked, so it can never validate, MTX,
  SoundStream, Diamond Audio, Audiopipe, Memphis, Crescendo, Sundown).
  Confirmed by checking their Shopify `products.json`/`body_html` or an
  actual product page — not a scraping failure, the data doesn't exist on
  the source at all. Compression-driver specialists (Radian, BMS's
  compression-driver lines) are a related case: the product category
  structurally lacks classical cone T/S parameters.

## Data-quality lessons that came out of scale

Once a harvest touches thousands of items across many sources, these
recur and are worth checking after *every* merge, not just once:

- **`str(None)` bug**: a brand/field extractor with no final `or ""`
  fallback can literally stringify Python's `None` into the text `"None"`
  and silently pollute the brand column. Grep for a literal `"None"` brand
  after any crawl that allows an empty `--brand` hint.
- **One-off "brand equals model" entries** are the signature of a
  page-declared brand field being wrong at the source (e.g. a Shopify
  theme's JSON-LD `brand.name` set to the product's own SKU). Sanity-check
  `Counter(p['brand'] for p in presets)` for singletons where
  `brand == model`.
- **Brand-name variants across sources for the same manufacturer**
  (`Peerless` vs `Peerless by Tymphany`, `LaVoce` vs `Lavoce`, `Eminence`
  vs `Eminence Speaker`) need canonicalizing after every new source merge —
  and canonicalizing the *live* dataset doesn't stick if you later re-run
  a merge from raw checkpoints that still have the old spelling; either
  patch the checkpoint or re-run the canonicalization pass after every
  merge.
- **Not every generic-sounding "brand" is wrong**: Parts Express's own
  `Coast Buyouts`/`Factory Buyouts` labels are genuine — accurate
  attribution for unbranded closeout stock, not a bug to "fix" by
  deleting or renaming.

## 2026-07-22 next-wave audit

Before the next bulk merge, four silent-correctness defects were reproduced
and covered by regression tests: nested hydration measurements were behind an
unreachable branch; HTML `<sup>` text was discarded (turning `0.07 ft³` into
`0.07 L`); a dirty JSON-LD description discarded its entire Product block;
and frame size could be taken from navigation text rather than the product.
Never start a multi-thousand-page retailer crawl until these probes pass.

Ranked new pools after those fixes:

1. **SoundImports manifest harvest**: reuse URLs, brands and MPNs already
   cached in `data/driver_prices.json` instead of crawling all 7,846 sitemap
   entries. A conservative name filter found 1,219 branded driver candidates;
   eight representative brands all produced complete T/S records in a probe.
2. **Direct WordPress product sitemaps**: SICA exposes 178 product URLs,
   P.Audio Thailand exposes 207 products including 94 LF-driver paths, and
   Bomber exposes 228 products with roughly 118 woofer/subwoofer/midbass URLs.
   One live LF probe from each manufacturer parsed successfully.
3. **Parallel-column/table sources**: Oberton's responsive HTML and PHL's
   four-column PDF rows are complete but defeat adjacency regexes. The generic
   table extractor now handles both layouts. Hinor's multi-model PDF matrices
   are the next variation to qualify.
4. **Regional/document fallbacks**: SEAS requires the secure system-trust
   fallback; Fostex publishes effective diaphragm radius instead of `Sd` and
   is unlocked by the radius derivation; JBL publishes a central T/S table
   suitable for a one-shot structured import.

Quality gate for retailer data: require authoritative brand+MPN metadata,
explicit units for dimensional required fields, and a physical consistency
audit before merge. A parser reporting "accepted" is not sufficient evidence
when a unit may have fallen back to its schema default.

### 2026-07-22 execution results

The qualified pools were downloaded and atomically merged into the
manufacturer catalog:

- SICA: 177 pages visited, 147 accepted, 22 incomplete/non-driver pages.
- P.Audio: 86 LF pages visited and accepted, with no failures.
- Bomber: 119 pages accepted; 114 new records and five already present.
- SoundImports: 1,219 catalog candidates visited, 1,067 T/S-complete pages
  extracted, 12 unit-quality rejections, 1,055 accepted; the merge added 941,
  updated 55 and left 59 unchanged.
- Oberton: 78 product pages accepted. Three archived pages used the generic
  heading `Discontinued product`; URL identity recovery and source-URL refresh
  restored `15XB700`, `15XB1200` and `15XL700` instead of collapsing them.
- Fostex: 72 likely speaker-unit pages visited and 19 complete records
  accepted. Most rejected historical pages expose specifications only as
  images, so they were not guessed.
- PHL Audio: the official products page exposed 93 reference PDFs; all 93
  parsed at confidence 1.00 and were accepted. Filename artifacts such as
  `_SpecSheet` and `.xlsx` were removed during identity normalization.

This run grew `data/manufacturer_drivers.json` from 3,219 to 4,697 usable
records and from 44 to 63 brands. Checkpoints and the SoundImports rejection
report remain under `data/` so interrupted or rejected work is auditable.
