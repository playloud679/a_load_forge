# src/ui/alternatives.py — Bass Match preview in Box Design

Everyone, guests included, sees under the Box Design analysis the five best of
the ~25 catalog drivers most similar to the current one, simulated with the
**same load type and total volume**, each with an **Open** action. It is the
free taste of Bass Match; the full search (whole catalog, filters, optimizer,
credits) stays behind sign-in.

- `similar_driver_names(current, features, limit=25, needs_xmax=True)` — pure.
  Distance `2·|ln size ratio| + |ln Fs ratio| + |ln Qts ratio| + 0.5·|ln Vas ratio|`
  (missing size/value: 0.5). One unit listed by several sources (`WEB:`,
  `LSDB:`, `VCD:` …) counts once; the current driver is excluded; vented and
  bandpass loads require a published Xmax.
- `box_total_volume_l(load_type, box)` — same rule as the summary strip
  (Infinite baffle: none, so no preview).
- Ranking: `ranking.rank_preset_row` without optimizer goals (suggested
  alignment at that volume, 10–500 Hz, 160 points), sorted by
  `sort_ranked_rows`; ~1 ms per driver; `st.cache_data` per
  (pool, load, volume, voltage), 24 h. Only drivers visible to users
  (`catalog._available_driver_preset_names`) are considered.
- **Open** reuses Bass Match's path (`batch_pending_result`), adding the driver
  as a design tab. The footer offers the full Bass Match: guests get
  "Search all N drivers — sign in free" (`account.request_sign_in("bass_match")`).
- Events: `alternatives_shown` (once per driver × load per session),
  `alternative_opened`. Failures are logged and never break Box Design.
