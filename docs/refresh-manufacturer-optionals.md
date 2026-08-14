# Refresh missing manufacturer specifications

`tools/refresh_manufacturer_optionals.py` revisits the exact source URL of
catalog records missing published driver, mechanical or product fields. The
targets include `Xmax`, AES/RMS/rated power (`Pe`), voice-coil inductance
(`Le`), frame/cutout/depth/mounting dimensions, weight, nominal impedance,
sensitivity, voice-coil diameter, `Xmech`, efficiency, magnet weight and flux
density. It reuses the generic T/S parser, fills only empty fields and never
creates records or overwrites published non-zero values.

The default is a dry run. Apply atomically with:

```bash
.venv/bin/python tools/refresh_manufacturer_optionals.py --apply
```

Requests are scheduled round-robin across domains, run concurrently across
hosts, and are serialized and delayed per hostname. `--domain`,
`--max-records`, `--workers`, `--timeout` and
`--per-host-delay` allow a narrow or conservative refresh. Every inserted
field records its source URL, fetch time, raw measurement and any explicit
derivation in `website_fields.field_provenance`. The run report is written to
`data/manufacturer_optional_refresh_report.json` only with `--apply`.
`--local-only` applies only safe reparsing of stored raw measurements and
performs no network requests.
PDF parsing runs in a separate process per document and is bounded by
`--parse-timeout` (30 seconds by default), so a malformed or pathological PDF
is reported and terminated without freezing the rest of the batch.

Completed, empty and failed URL attempts are persisted in
`data/manufacturer_optional_refresh_checkpoint.json`. A URL is attempted once
per parser revision after an `updated` or `no_change` result, so bounded
`--max-records` runs continue with the next unvisited product rather than
retrying a page merely because it does not publish every target. Transient
failures are retried up to three times for that parser revision. `--force`
deliberately ignores this checkpoint. A parser revision bump makes all URLs
eligible again. Results are accepted only when
the page model matches the requested catalog model, or at least three stable
T/S identity values independently agree; redirects and generic pages are
reported as identity failures.

Parser revision 4 enables the source-specific, explicitly labelled Oberton
mounting-table pairing and makes prior `no_change` page attempts eligible for
one new pass.

Per-host throttling spaces request *starts* by `--per-host-delay`. A slow
response does not serialize every other worker, but concurrent workers cannot
start a burst at the same instant.

Known source URLs are trimmed before hostname matching, checkpoint lookup and
fetching. Legacy catalog rows with trailing whitespace therefore resolve to
the intended product URL instead of producing a false `%20`/404 failure.

## Latest catalog audit (2026-07-22)

After the manufacturer refresh and invalidation/refetch of legacy unitless
power matches, the 4,424-record catalog contains `Xmax` for 4,206 records
(95.07%), `Pe` for 4,260 (96.29%) and `Le` for 4,252 (96.11%). No non-zero
`Pe` remains whose stored source measurement lacks an explicit power unit.

Before fetching, explicit-unit raw power measurements are reparsed locally to
repair legacy thousands-separator errors such as `2,000 W → 2 W`. Existing
power values whose stored raw measurement has no unit are treated as suspect
and may be replaced only by a newly extracted value with an explicit `W/kW`.
Legacy `Pe` values backed only by unitless free text are invalidated before
refresh and their previous value/reason is retained in `invalidated_fields`.
Malformed legacy `raw_measurements.pe_w` values that are not structured
measurement objects are ignored safely instead of stopping the bulk cycle.

Power handling is deliberately semantic: AES, RMS, rated power, power rating
and power capacity are accepted; program, continuous-program, maximum and
peak figures are not used as the thermal `Pe` value. A manufacturer-declared
linear coil travel marked `(p-p)` is converted to one-way Xmax by division by
two and retains that derivation in provenance.
