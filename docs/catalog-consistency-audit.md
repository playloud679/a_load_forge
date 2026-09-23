# Catalog consistency audit

`make test-catalog` is a strict local data gate: source names must be unique and
all six required T/S fields must be positive finite values. It does not share
the runtime loader's deduplication or incomplete-row filtering. A passing
simulation suite therefore does not imply that this raw catalog gate passes.
Crawler policy tests belong to the separate crawler workspace; the obsolete
local `test_crawler_registry.py` entry point has been removed.

## Contract alignment check, 2026-09-23

The strict gate currently fails on duplicate names: 11 Eminence names each
occur twice in the 10,761-row proprietary catalog. Their six core T/S values
and official URLs match, but metadata and optional values differ. A separate
read-only inspection also finds 101 invalid/missing required fields across
52 rows. The records are retained for source review in the crawler workspace;
the gate has not been relaxed and missing physical values have not been invented.

Run `.venv/bin/python tools/audit_catalog_consistency.py` to inspect every row
in the six local simulation catalog files. Output:
`data/catalog_consistency_audit.json`, with catalog, row index, name, URL,
issue codes and numerical evidence. The tool never changes catalog records.

This audits input data, unlike `mass_driver_validator.py`, which samples
drivers and compares simulation curves using the same input parameters.

Checks cover required positive finite values, Q ordering, Q/Fs/Vas/motor
identities (15% multiplicative tolerance), effective diameter versus nominal
size (70–115%), historical size corrections, missing source units and explicit
imperial/SI conversion discrepancies. Derived inputs are identified: identities
satisfied by construction are not independent validation of source values.
Size corrections must be reviewed even when the resulting size agrees with Sd.
Raw-unit discrepancies may be errors in provenance rather than in solver data.

The audit also compares every explicit inch diameter in a name or published
specification with Sd. It does not interpret bare model numbers as diameters;
voice-coil and compression-driver dimensions are excluded from that inference.

## Repairing what the audit finds

The audit only reports. `Sd` values that are provably wrong are repaired in the
crawler repository, which owns the source-of-truth catalog:

```bash
cd ../load_forge_crawler
.venv/bin/python tools/repair_sd_integrity.py            # dry run + report
.venv/bin/python tools/repair_sd_integrity.py --apply    # writes the catalog
.venv/bin/python tools/sync_to_official_db.py            # propagate to load_forge + deploy
```

`tools/repair_sd_integrity.py` repairs a row only when the replacement comes
from independent evidence: the `Vas`+`Cms` identity, a corroborated decade/unit
rescale, or a **published** nominal frame diameter (at 80 % of the frame) when
the stored value is identifiable as the crawler's voice-coil-area fallback or
falls below the physical floor for any radiator. Every repair records
`website_fields.field_corrections.sd_cm2` and `derivations.sd_cm2`, refreshes
dependent derived fields and is idempotent. Rows it cannot resolve stay
untouched and are listed in `data/sd_integrity_repair_report.json`; at runtime
they surface as the ⚠ `Size/Sd` coverage flag instead of a silently rewritten
frame size.

## Local scan, 2026-09-20

| File | Rows inspected | Rows requiring review |
|---|---:|---:|
| catalog_proprietario.json | 10,761 | 2,787 |
| manufacturer_drivers.json | 10,761 | 2,787 |
| catalog_lsdb.json | 6,215 | 721 |
| catalog_vituixcad.json | 1,038 | 62 |
| catalog_speakerboxlite.json | 1,952 | 231 |
| catalog_ztzaudio_lf_ferrite_presets.json | 25 | 3 |

The manufacturer copy must not be counted as another 10,761 unique drivers.
External catalogs also overlap; totals are row counts, not unique drivers.
No sampling or acoustic eligibility filtering is used.

This run follows the Sd-integrity repair below: in the proprietary catalog
`size_sd_mismatch` fell from 284 to 210 and `declared_size_sd_mismatch` from 177
to 116 (80 rows repaired for a voice-coil-derived, decade-scaled or
unit-mismatched `Sd`). The remaining findings are review candidates: a
70–115 % diameter window flags drivers with unusually wide surrounds as well as
genuine conflicts, and only the crawler-side repair tool may change them, on
independent evidence.
Categories overlap; a record can have multiple findings.
The first scan found 60 Rockville records requiring review. Source-verified
repairs now cover MS12LB, MS12LW and MS10LB in both local manufacturer files.
In addition, 730 records with an explicit published nominal diameter now use
that value instead of a size inferred from Sd. Sd is not silently changed when
nominal diameter and Sd disagree; those records remain flagged for review.
REDCATT Twiggy12 has Qms=0.16 and Qts=1.08, violating the positive-Q identity.
RCF MB12N251 has a source-unit discrepancy requiring review of raw metadata.

This is an offline consistency audit, not full manufacturer-source verification.
Missing units cannot be reconstructed reliably from plausibility alone.
It excludes live Firestore/deployed snapshots, built-in Python presets and
passive-radiator presets. No cloud catalog has been changed or published.
Warnings are review candidates, not automatic grounds for rewriting values.

After the explicit unit repairs, decimal-scale recovery, nominal/Sd unit
recovery, Vas–Cms cross-check and verified Rockville repairs, the latest scan
reports 2,316 proprietary rows
requiring review. The Vas–Cms cross-check corrected only decimal-scale errors
where the independent identity agreed within 15%; it corrected, for example,
the 3FR30 Sd from 30,000 to 30 cm². The remaining flags are review candidates:
they include source identity conflicts, missing provenance units and effective
Sd values that cannot be corrected from nominal diameter alone.
The remaining rows require source-by-source verification before further edits.

Tests: `.venv/bin/python tests/test_catalog_consistency_audit.py`.
The primary-source Beyma corrections include 12CMV2 (0.053 m² = 530 cm²),
15CMV2 (0.088 m² = 880 cm²) and 12WRS400 (0.053 m² = 530 cm²).
