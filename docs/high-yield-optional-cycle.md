# High-yield optional-field cycle

`tools/run_high_yield_optional_cycle.py` replaces blind full-catalog retries
with a measured source-level gate for published-only `Xmax`, `Pe` and `Le`.

Records are grouped by domain and ranked by weighted missing-field opportunity.
A domain first receives a three-record probe. The remaining records are fetched
only when at least 50% of the probe records produce a field and at least 50% of
requests succeed. Results and attempt timestamps are stored in
`data/optional_source_yield_checkpoint.json`; failed or low-yield domains remain
in cooldown for 30 days unless `--force` is explicit.

Domains where many records share one archive/table URL are excluded: those
need a dedicated multi-record adapter rather than applying one parsed product
page to several drivers. Retailer/API-derived technical rows are also excluded
from this manufacturer-source gate and remain in their dedicated importers.

```bash
.venv/bin/python tools/run_high_yield_optional_cycle.py
```

The completion coordinator runs this gate once per network-enabled run. Generic
PDF discovery is opt-in through a positive `--datasheet-limit` because its own
bounded pilot must demonstrate useful yield before expansion.
