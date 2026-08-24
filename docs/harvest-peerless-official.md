# Peerless official API harvester

`tools/harvest_peerless_official.py` reads the public product API used by the
official Peerless/Tymphany driver application at `products-peerless.com`. It
walks every listing page and then requests each `/api/driver/{id}` detail
object, because list rows may omit the complete T/S set. Detail requests use a
small bounded worker pool, retry transient HTTP/network failures independently
and print progress every ten products; one broken detail endpoint is recorded
in the staging report instead of aborting the complete crawl.

Only official API types `Woofer`, `Subwoofer` and `Fullrange` with positive
published `Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd` and `Qms > Qts` enter the
staging artifact. Tweeters and compression drivers share the same API but are
outside the low-frequency acoustic-load catalog. API units are preserved explicitly:
`Cms` is converted from the official UI's µm/N to Load Forge mm/N; `Sd`, `Vas`,
`Le`, `Xmax`, power and mass already use cm², litres, mH, mm, watts and grams.
Every record retains the official transducer page, API id, PDF link and raw
required measurements with confidence 1.0.

The command never edits the proprietary catalog:

```bash
.venv/bin/python tools/harvest_peerless_official.py
```

It writes `data/peerless_official_checkpoint.json` as staging. Publication is
a separate reviewed append-only operation followed by `make test-catalog`.
