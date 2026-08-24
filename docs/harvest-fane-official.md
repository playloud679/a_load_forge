# Fane official harvester

`tools/harvest_fane_official.py` enumerates Fane's current product catalog and
the official low-frequency/full-range archive. The site uses ASP.NET WebForms
postbacks for pages after the first; the harvester preserves the server's
hidden state and follows every published page before fetching product cards.

Only simulation-ready cone drivers with complete, physically valid T/S data
are accepted. Compression drivers and incomplete archive pages are retained as
rejections, never filled with third-party library values. Output is staging
only and must pass the reviewed append-only publication gate.

```bash
make crawl-fane ARGS='--output /tmp/fane-official.json --workers 8'
```
