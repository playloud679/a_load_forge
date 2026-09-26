# driver_plausibility

Source: `src/driver_plausibility.py` (an identical copy lives in the portal's
vendored `load_forge_deploy/src/`).

`plausibility_issues(name, *, qts, le_mh, sd_cm2)` returns short reasons why a
catalog record cannot describe the product; an empty list means "no known
problem", not "verified". It is the guard until bad records are quarantined in
the crawler catalog.

| Rule | Example caught |
|---|---|
| Multi-driver product: `kit`, `component system/set`, `N vie`, `2-way kit/system` | "Focal 165 SF3Kit a 3 vie da 165 mm", Focal car "Kit 2 vie" series, "2-way Component System" |
| Placeholder T/S: Qts exactly 1.000 **and** Le = 0 | Focal SUB 5 KM, Soundmax SX-AH12, several SBL records |
| Name size vs Sd: nominal diameter from "165 mm", '6.5"', '6-1/2"', "12 in"; Sd outside 0.35–2.5 × π·(0.4·D)² | 6.5" coaxial pairs with Sd 530 cm², "8in" records with Sd 2 cm² |

A single "2-way coaxial" driver is *not* flagged (only kit/system/set wording).
Oval sizes ("2" x 7") skip the size rule. On the 2026-09-26 catalog it flags 57
of ~19,200 records.

Used by [ui/alternatives](ui/alternatives.md): an implausible current driver
shows a warning instead of a comparison, and implausible records are never
suggested.
