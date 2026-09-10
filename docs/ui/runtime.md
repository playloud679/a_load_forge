# src/ui/runtime.py — shared runtime globals

Owns the mutable globals every UI module reads at call time:

| Name | Meaning |
|---|---|
| `_VERSION` | Repo `VERSION` string, `"dev"` when unreadable |
| `_SAAS_SOURCE_TOKEN` | `src/saas.py` mtime, used as a cache key |
| `_SAAS_SETTINGS` | `SaaSSettings` loaded once per run |
| `_CURRENT_SAAS_USER` | Resolved `SaaSUser` for this rerun (may be `None`) |
| `_ACCOUNT_STORE` | Account store for this rerun |
| `logger` | `logging.getLogger("load_forge.ui")` |

## Contract

- `initialize_saas_settings()` must run **after** `st.set_page_config` and
  before `_resolve_saas_user()`/`_get_account_store()`; it calls
  `st.error` + `st.stop()` on `SaaSConfigurationError`, so it cannot execute
  at import time.
- `_CURRENT_SAAS_USER` and `_ACCOUNT_STORE` are assigned by `ui_app.py` on
  every Streamlit rerun. Modules must read them as `_runtime.X`; copying the
  value at import time would freeze the first rerun's user.
- Reloading this module resets the mutable globals to `None`; `ui_app.py`
  reassigns them immediately after the reload loop.

## Tests

`tests/test_all.py` exercises the auth gate, admin gating and cloud
persistence paths through `ui_app`; no test imports `runtime` directly.
