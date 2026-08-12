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
`size_in`. When the source omits it, the runtime catalog assigns the nearest
conventional nominal frame-size class from `Sd`; it does not equate nominal
diameter with the smaller effective piston diameter. Where published,
mechanical fields are imported separately for layout drawing: overall
diameter, baffle cutout, depth, bolt circle and net weight. The remaining
records are retained as source material and must be completed or manually
reviewed first.
