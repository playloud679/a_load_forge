# Manufacturer database status report

`tools/generate_manufacturer_database_report.py` produces the current,
human-readable audit in
[`manufacturer-database-status.md`](manufacturer-database-status.md).

The generator reads `data/manufacturer_drivers.json`, the separate price index
and the latest applied deduplication report. It recalculates:

- driver, manufacturer and per-field coverage counts;
- verified price coverage, currencies, URL/provenance completeness and misses;
- invalid required values, `Qms <= Qts` conflicts and invalidated unitless power;
- explicit refresh and derived-field provenance;
- a non-mutating conservative duplicate preview;
- leading sources and the manufacturers with the largest Xmax, Pe and Le gaps.

Regenerate the report without running the application test suite:

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py
```

To run the complete active suite and include its fresh result:

```bash
.venv/bin/python tools/generate_manufacturer_database_report.py --run-tests
```

The command never edits either JSON database. It writes the Markdown report
through a temporary sibling and an atomic replacement, so an interrupted run
does not leave a partial report.
