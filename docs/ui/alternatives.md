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
- **Compare entry (`?compare=1`)**: the portal's "Compare with Bass Match"
  button adds `compare=1`; `wants_on_top()` consumes it and the preview is
  rendered in a slot above the chart (`render_alternatives(..., on_top=True)`)
  with a "Hide" action that moves it back under the analysis.
- **Unreliable data**: records flagged by
  [driver_plausibility](../driver_plausibility.md) are excluded from the pool;
  if the current driver is flagged, a warning replaces the comparison.
  Duplicate listings that differ only by an "Ohm" word ("FRS 7 - 8" /
  "FRS 7 - 8 Ohm") collapse to one.

- **Representative driver** (`representative_driver`, pure; `context_driver`
  over the visible library): candidates of the requested size (±0.3") and/or
  brand with published Xmax; without a brand, reference brands (the portal's
  featured set: Dayton Audio, SB Acoustics, Scan-Speak, SEAS, Peerless,
  FaitalPRO, B&C, Beyma, Eminence, SICA, Ciare, Morel) are preferred; then
  first-party names; the one closest to the group's median Fs/Qts/Vas wins
  (e.g. 6.5" → Peerless 165 WF, 12" → FaitalPRO 12FH530).
