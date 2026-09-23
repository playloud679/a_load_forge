# src/ui/__init__.py — UI package bootstrap

Adds the `src/` directory to `sys.path` when absent so UI modules can import the
same top-level backend modules as `ui_app.py`. It does not render the UI or
initialize account stores. See [../ui.md](../ui.md) for the module map, reload
ordering and module-qualified cross-reference contract.

The Streamlit AppTest and the active UI regression suite exercise this bootstrap.
