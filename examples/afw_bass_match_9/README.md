# Bass Match — nine native AFW v2 projects

These projects are derived from the real **AUDIO per Windows pro v2** templates
in `Desktop/XP/Audio for windows-2`. Each file embeds a different driver from
the Load Forge database, a coherent 201-point ideal free-air CRW generated from
its T/S data, and a Load Forge starter alignment.

| File | Load Forge database driver | AFW load | Alignment |
|---|---|---|---|
| `01_kef_b110_sealed.afw` | KEF B110B article example | Sealed | Vb 4.09 L, Fc 92.1 Hz, Qtc 0.707 |
| `02_sb34swpl_sealed.afw` | SB Acoustics SB34SWPL76-4 | Sealed | Vb 20.38 L, Fc 41.6 Hz, Qtc 0.707 |
| `03_dayton_rss315ho_sealed.afw` | Dayton Audio RSS315HO-4 | Sealed | Vb 12.78 L, Fc 59.1 Hz, Qtc 0.707 |
| `04_beyma_12lex1300_bp4.afw` | Beyma 12LEX1300Nd | BP4 | 5.60 L / 129.2 Hz + 42.99 L / 129.2 Hz |
| `05_lavoce_wsf122_bp4.afw` | LaVoce WSF122.02 | BP4 | 41.43 L / 82.8 Hz + 87.97 L / 82.8 Hz |
| `06_beyma_12cmv2_bp6.afw` | Beyma 12CMV2 | BP6 | 75.98 L / 46.4 Hz + 37.99 L / 92.8 Hz |
| `07_scanspeak_30w_bp6.afw` | Scan-Speak 30W/4558T00 | BP6 | 196.94 L / 16.7 Hz + 98.47 L / 33.4 Hz |
| `08_dayton_um12_dcaav.afw` | Dayton Audio UM12-22 | DCAAV | 49.08 L / 49.7 Hz + 98.88 L / 19.0 Hz |
| `09_fostex_fe126_dcaav.afw` | Fostex FE126NV2 | DCAAV | 1.98 L / 270.2 Hz + 3.99 L / 103.2 Hz |

The embedded acoustic curves are ideal T/S projections, not manufacturer FRD
measurements. This is intentional: it keeps the AFW and Load Forge comparisons
on the same low-frequency model inputs. All files retain AFW's original CRLF,
Latin-1 layout and 4,847-line project structure.
