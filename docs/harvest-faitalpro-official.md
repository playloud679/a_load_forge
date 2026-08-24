# FaitalPRO official catalog harvester

`tools/harvest_faitalpro_official.py` enumerates the first-party FaitalPRO LF,
coaxial and archived-LF catalogs. Current product listings expose every
published 4/8/16-ohm product ID, so impedance variants are harvested as
separate engineering records instead of being collapsed into one model.

Each detail page must pass the common complete T/S validation for `Fs`, `Vas`,
`Qts`, `Qms`, `Re` and `Sd`. The shared parser also captures official AES
power, Xmax, Mms, Bl and Le when published. HF-only drivers and horns are not
enumerated; coaxial records use their low-frequency moving system.

The bounded worker pool retries transient requests and prints progress every
ten product pages. Output is staging-only and never changes the proprietary
catalog directly:

```bash
.venv/bin/python tools/harvest_faitalpro_official.py
```

The default output is `data/faitalpro_official_checkpoint.json`. Publication
requires exact runtime deduplication, explicit reviewed URLs and the append-only
catalog gate.
