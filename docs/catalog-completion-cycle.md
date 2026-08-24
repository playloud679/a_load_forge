# Automatic catalog completion cycle

`tools/run_catalog_completion_cycle.py` coordinates the existing metadata,
retailer and reporting tools. It targets the fields that cannot be inferred
safely (`Xmax`, AES/RMS/rated `Pe`, `Le`) plus verified current prices. It does
not invent values, use brand averages or accept accessory/low-confidence price
matches.

## Plan first

The default mode is offline and read-only with respect to the source catalogs:

```bash
.venv/bin/python tools/run_catalog_completion_cycle.py plan
```

It writes `data/catalog_completion_report.json` with:

- a complete field/price coverage snapshot;
- a weighted brand queue (`Xmax` first, then `Pe`, `Le` and price);
- record-level tasks and their next safe action;
- the ordered execution stages.

Records with an exact HTTP source URL are queued for a bounded refresh. Records
without one are marked `approved_source_discovery`; they require an allow-listed
manufacturer/archive/authorized-retailer target in the crawler-agent manifest.
Price gaps are always sent through the retailer matcher rather than guessed.

## Run restartable cycles

```bash
.venv/bin/python tools/run_catalog_completion_cycle.py run \
  --max-cycles 3 --stop-after-stalled 1
```

Each cycle:

1. reparses stored measurements, applies physical derivations and rematches the
   existing price index before making any request;
2. probes the highest-opportunity manufacturer domains on three records and
   expands only sources with at least 50% measured record yield;
3. optionally sends official product URLs to the PDF-first archive when
   `--datasheet-limit` is positive; blind full HTML refreshes are suppressed;
4. refreshes retailer checkpoints only in the first cycle of a run;
5. applies only high-confidence price matches, rebuilds the four source-specific
   catalogs and regenerates the coverage report.

The primary retailer workers use independent shards and atomic merging. All
underlying crawlers retain their checkpoints, so restarting this coordinator
continues useful work. The coordinator updates its report after every stage,
stores only bounded stdout/stderr tails and stops when a complete cycle adds no
new tracked field or matched price. A stage failure is recorded; by default the
remaining independent stages still run so successful checkpoints can be
merged. Regional source workers are capped at five minutes by default
(`--extra-source-runtime`) so one slow catalog cannot block every other source.
Source probes and datasheet seeds have separate attempt checkpoints and are not
revisited during the cooldown. PDF discovery is disabled by default after a
20-page pilot produced no catalog improvements. Network work is never repeated
in later cycles unless `--repeat-network` is explicit. Add `--force-optionals`
after a parser change or `--fail-fast` for operational debugging.

This ordering is yield-driven: cheap deterministic work and rematching happen
first; repeated low-yield page crawls are suppressed; unresolved records remain
queued for a dedicated source adapter or an explicitly enabled evidence channel
instead of requesting the same HTML again.

Useful bounds:

```bash
# Metadata only, at most 200 exact source pages per cycle
.venv/bin/python tools/run_catalog_completion_cycle.py run \
  --skip-prices --max-records 200

# Prices only, without the regional retailer group
.venv/bin/python tools/run_catalog_completion_cycle.py run \
  --skip-optionals --skip-extra-retailers --max-cycles 1
```

The completion report ends with explicit unresolved counts. Reaching 100% is
not forced: if a manufacturer does not publish a value, leaving it missing is
more accurate than manufacturing a plausible number.

## Driver-growth watchdog

The application release and proprietary catalog release are independent. The
current app release is tracked in `VERSION`; the published proprietary catalog
has its own `catalog_version` (`1.0.0` currently). Catalog-only changes use the
fast gate:

```bash
make test-catalog
```

The full application suite remains required for changes to `src/`, `ui_app.py`
or the app-facing catalog loader.

After a batch, check whether the manufacturer catalog itself grew:

```bash
.venv/bin/python tools/driver_count_watchdog.py
```

The watchdog counts the deduplicated manufacturer tier loaded by the
application from `catalog_proprietario.json`. It resets an old baseline if it was created with the
application's cross-catalog deduplicated count, emits `WARNING` on the first
stalled cycle and `ALARM` from the second consecutive stalled cycle onward.
