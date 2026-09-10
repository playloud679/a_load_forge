# Catalog consistency audit

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

## Local scan, 2026-09-10

| File | Rows inspected | Rows requiring review |
|---|---:|---:|
| catalog_proprietario.json | 9,906 | 2,316 |
| manufacturer_drivers.json | 9,906 | 2,316 |
| catalog_lsdb.json | 6,215 | 721 |
| catalog_vituixcad.json | 1,038 | 61 |
| catalog_speakerboxlite.json | 1,952 | 229 |
| catalog_ztzaudio_lf_ferrite_presets.json | 25 | 3 |

The manufacturer copy must not be counted as another 9,906 unique drivers.
External catalogs also overlap; totals are row counts, not unique drivers.
No sampling or acoustic eligibility filtering is used.

In the proprietary catalog: 782 Vas identity discrepancies, 603 motor
discrepancies, 411 Fs discrepancies, 159 Q discrepancies, 244 size/Sd
discrepancies, 716 size-correction histories and 1,228 missing-unit observations.
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
