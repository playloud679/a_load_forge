# Official-source hunt radar

`tools/build_official_hunt_radar.py` uses the optional LSDB, VituixCAD,
Speaker Box Lite, ZTZ Audio and legacy manufacturer-crawl libraries only as a
discovery index. It does not import their technical fields into the proprietary
catalog.

The tool reads every record, reduces it to the same normalized
manufacturer/model/impedance identity used by the application, and compares
that identity with `data/catalog_proprietario.json`. Its committed report
contains aggregate per-library and per-brand counts plus a small model sample;
it contains no copied T/S parameters. Use `--brand NAME` to print the complete
in-memory candidate list for one manufacturer while researching its official
site or datasheets.

```bash
make catalog-radar
make catalog-radar ARGS='--brand "DD Audio"'
```

A radar match is never publication evidence. A driver may be appended only
after the manufacturer page or first-party datasheet independently supplies a
complete, physically valid simulation record and passes the reviewed
append-only publication gate. Retailers and third-party libraries may reveal a
model name, but they cannot establish its T/S values or provenance.
