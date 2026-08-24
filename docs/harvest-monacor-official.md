# Monacor official catalog harvester

`tools/harvest_monacor_official.py` reads the public product catalog at
`monacor.com` and enumerates the seven low-frequency, midrange, coaxial and
full-range component categories. Pagination is resolved from each category's
published result count and product links are normalized against the site's
document-level base URL.

The site also distributes third-party Celestion products. A product is
therefore accepted only when its own `Manufacturer information` block starts
with `MONACOR INTERNATIONAL`; the site header, importer address and category
branding are not treated as proof of manufacturer. Every accepted record must
also pass the generic crawler's complete T/S validation for `Fs`, `Vas`,
`Qts`, `Qms`, `Re` and `Sd`. Tweeter categories are not crawled.

The harvester uses a small bounded worker pool, retries transient product-page
failures and prints progress every ten details. It writes a staging artifact
and never edits the proprietary catalog directly:

```bash
.venv/bin/python tools/harvest_monacor_official.py
```

The default output is `data/monacor_official_checkpoint.json`. Publication is
a separate reviewed append-only operation followed by `make test-catalog`.
