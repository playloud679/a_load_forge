# Restartable published-spec batches

`tools/run_published_spec_batches.py` completes one known source domain through
small, atomic calls to `refresh_manufacturer_optionals.py`. Each child batch
writes the catalog, URL checkpoint and report before the next batch starts, so
an interruption loses at most the currently running batch and a later run
continues from the first URL not attempted with the current parser revision.

```bash
.venv/bin/python tools/run_published_spec_batches.py \
  --domain bcspeakers.com --batch-size 10
```

The runner stops when the domain is exhausted, a child command fails, the
failure fraction of one batch exceeds `--max-failure-rate`, or the optional
`--max-batches` limit is reached. It never uses `--force`: successful,
no-change and failed URL attempts already recorded by the current parser are
not fetched again.
