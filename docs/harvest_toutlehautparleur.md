# ToutLeHautParleur catalog harvester

`tools/harvest_toutlehautparleur.py` downloads the public English cone-speaker
catalog from `en.toutlehautparleur.com`. Direct HTTP clients receive a
Cloudflare challenge, so the harvester uses an already-open Safari session that
has passed the interactive check. It opens one temporary catalog tab per page,
reads only that tab's public HTML, closes it, and checkpoints immediately.

The checkpoint is `data/toutlehautparleur_harvest_checkpoint.json`. It contains
brand, MPN/SKU, EUR price, availability and direct product URL. After the list
pages, the same run visits products not already represented in any of the four
catalogs, extracts and physically validates their T/S parameters with
`tools/crawl_thiele_small.py`, and merges accepted new drivers into
`data/catalog_proprietario.json`. Products without a complete valid LF T/S set
are retained as price offers but not inserted as simulatable drivers.
Re-running resumes missing pages and product details; `--fresh` starts over.

```bash
.venv/bin/python tools/harvest_toutlehautparleur.py
```

Use `--max-pages N --max-products N` for a bounded validation run, or
`--prices-only` to skip product-detail T/S extraction. After harvesting, merge the
offers through the same guarded preset matcher used by all other retailers:

```bash
.venv/bin/python tools/merge_extra_retailers.py
```

The harvester never reads unrelated Safari tabs and rejects every URL outside
the exact TLHP cone-speaker pagination pattern.
