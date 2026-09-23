# src/billing.py — hosted payment integration

`get_stripe_setting` resolves environment variables before Streamlit's `[stripe]`
secrets. Checkout and customer-portal helpers initialize Stripe lazily and
return hosted URLs; they require a configured secret key. The optional account
store persists customer IDs, subscription state and purchased credits.

`create_checkout_session` handles subscriptions; `create_credit_pack_checkout_session`
uses `CREDIT_PACKS`. `sync_checkout_session` reconciles a returned Checkout
session. `process_webhook_event` verifies the signature with the webhook secret,
then handles Checkout, subscription and invoice events. Event deduplication
depends on the supplied store's event persistence; do not assume exactly-once
credit application without that backend support.

The UI accesses this module as `_billing`; the entry point reloads it after
`saas` when its source changes. Hosted URL creation is an external operation,
so tests use mocked Stripe objects, not live purchases.

See [payments-stripe.md](payments-stripe.md) for settings and deployment,
and `tests/test_billing.py` for payment-flow regression coverage.
