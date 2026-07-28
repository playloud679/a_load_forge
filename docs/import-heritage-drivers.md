# Heritage driver import: Altec Lansing and TAD

`tools/import_heritage_drivers.py` adds historically important low-frequency
drivers from two traceable tables:

- Altec Lansing Technical Letter No. 267B, hosted and corrected by Great
  Plains Acoustic. The live HTML table contains model, Xmax, Re, displacement,
  Fs, Vas, Qts, Qms and Qes.
- Pioneer/TAD's © 2005 official “Thiele-Small Parameters” table, supplemented
  by the current and archived TAD product pages. It covers TL-1601 variants,
  TL-1602, TL-1603, TL-1801, TL-1101h, TL-1102 and TM-1201 variants.

The Altec table does not publish `Sd` directly. It is derived exactly from
volume displacement and one-way excursion:

```text
Sd [cm²] = Vd [in³] / Xmax [in] × 6.4516
```

Altec `Vas` is converted from cubic feet to litres and Xmax from inches to
millimetres. TAD square metres and `10⁻⁴ m/N` compliance values are converted
to `cm²` and `mm/N`. Every conversion, original table value, archive URL and
document identity is retained in `website_fields`.

Online import into the manufacturer catalog:

```bash
.venv/bin/python tools/import_heritage_drivers.py
```

Qualification with a previously downloaded Altec page:

```bash
.venv/bin/python tools/import_heritage_drivers.py \
  --altec-input /tmp/altec_ts.html --dry-run
```

The standard manufacturer merge is used: existing populated records are not
overwritten, brand/model identities are stable and output writes are atomic.
