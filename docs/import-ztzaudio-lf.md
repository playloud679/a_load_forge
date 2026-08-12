# ZTZ Audio LF ferrite import

`tools/crawl_ztzaudio_lf.py` downloads the 10-page ZTZ Audio **LF
Loudspeakers - Ferrite** category into:

- `data/catalog_ztzaudio_lf_ferrite.json` — 118 product pages, source URLs,
  raw table labels, normalized T/S fields and datasheet URLs;
- `data/ztzaudio_lf_ferrite_assets/` — downloaded datasheets and available
  product images.

The crawler uses checkpoints and can resume by rerunning the same command:

```bash
.venv/bin/python tools/crawl_ztzaudio_lf.py \
  --output data/catalog_ztzaudio_lf_ferrite.json \
  --assets-dir data/ztzaudio_lf_ferrite_assets
```

The category currently provides 118 pages and 35 datasheet links. A product is
eligible for automatic Load Forge import only when the required LF T/S fields
are present (`Fs`, `Vas`, `Qms`, `Qes`, `Qts`, `Re`, `Sd`, `Mms`, `BL` and
`Xmax`); the importer also preserves the nominal chassis size separately as
`size_in`. `Sd` remains the effective piston area and must not be used as the
nominal frame diameter. The remaining records are retained as source material
and must be completed or manually reviewed first.
