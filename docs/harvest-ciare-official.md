# Ciare official catalog harvester

`tools/harvest_ciare_official.py` enumerates all first-party current and
archived Ciare LF and coaxial product pages. The four server-rendered listings
provide stable product URLs whose path contains family, impedance and model.

Every detail must pass the common complete T/S validation. Product identities
retain their published impedance suffix so current 1/2/4/8-ohm and dual-coil
variants are not collapsed. Coaxial records represent the low-frequency moving
system; tweeters and HF-only drivers are outside the enumerated families.

The bounded worker pool retries transient requests and reports progress every
ten pages. Output is staging-only and never edits the proprietary catalog:

```bash
.venv/bin/python tools/harvest_ciare_official.py
```

The default output is `data/ciare_official_checkpoint.json`. Exact runtime
deduplication and the reviewed append-only publication gate are required before
any catalog write.
