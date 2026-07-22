# Refresh missing manufacturer specifications

`tools/refresh_manufacturer_optionals.py` revisits the exact source URL of
catalog records missing `Xmax`, AES/RMS/rated power (`Pe`) or voice-coil
inductance (`Le`). It reuses the generic T/S parser, fills only empty fields
and never creates records or overwrites published non-zero values.

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

Power handling is deliberately semantic: AES, RMS, rated power, power rating
and power capacity are accepted; program, continuous-program, maximum and
peak figures are not used as the thermal `Pe` value. A manufacturer-declared
linear coil travel marked `(p-p)` is converted to one-way Xmax by division by
two and retains that derivation in provenance.
