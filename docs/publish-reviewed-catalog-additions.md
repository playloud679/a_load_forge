# Reviewed append-only catalog additions

`tools/publish_reviewed_catalog_additions.py` promotes only crawler records
whose product URLs were explicitly reviewed. It is intended for small,
high-confidence catalog batches after a staging crawl.

The command validates the required T/S fields, official-manufacturer source
label and minimum extraction confidence. It rejects duplicate names, URLs and
brand/model identities. Existing rows are hashed before publication and the
same hashes must remain at the start of the resulting catalog; the operation
therefore appends records without enriching, replacing or deleting the
pre-existing catalog.

Use `--dry-run` first, repeat `--accept-url` for every approved product, then
run without `--dry-run` and execute `make test-catalog`.

The latest approved batch is summarized in
`data/catalog_additions_latest_report.json`; the application shows it in the
sidebar crawl-report expander, separately from staging and retailer discovery.
The report can aggregate a review cycle while `latest_batch_added` identifies
the most recent publication inside that cycle. Large batches use
`latest_batch_by_brand`, `added_names_count` and `added_names_sample` so the UI
shows exact totals and provenance without rendering hundreds of product names.
