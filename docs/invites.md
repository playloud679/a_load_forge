# src/invites.py — legacy alpha invite store

This standalone helper creates, lists, revokes and redeems invite codes. It is
not imported by the current Streamlit UI. `create_invite` records recipient,
role, creation time, maximum uses, redemption count and active state.
`verify_and_redeem_token` returns `(valid, message_or_recipient)` and increments
the count only on a successful redemption. `is_token_authorized` checks active
status without consuming another use; exhausted codes remain valid for existing
sessions until revoked.

Records live in `data/invites.json`; JSON or base64 environment records supplement
local records, with local values winning for the same code. Saving uses a
temporary file and replacement. The lock is process-local, not a distributed
transaction or an IP rate limiter. Invalid optional JSON/base64 inputs are
currently ignored. The master token comes from `LOAD_FORGE_ALPHA_TOKEN` with a
legacy development fallback and bypasses use limits; this is not the current
SaaS authorization boundary.

There are no dedicated invite tests in the active suite. Do not treat its
passing result as verification of multi-process invite persistence.
