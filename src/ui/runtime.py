"""Runtime globals shared across the Load Forge UI modules.

``_VERSION``/``_SAAS_SOURCE_TOKEN`` are read once; ``_SAAS_SETTINGS`` is loaded
by :func:`initialize_saas_settings` after ``st.set_page_config`` (it renders
``st.error``/``st.stop`` on misconfiguration). ``_CURRENT_SAAS_USER`` and
``_ACCOUNT_STORE`` are assigned by ``ui_app.py`` on every Streamlit rerun, so
modules must read them through this module instead of copying the value.
"""
from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

import saas as _saas

logger = logging.getLogger("load_forge.ui")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    _VERSION = (_PROJECT_ROOT / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"
_SAAS_SOURCE_TOKEN = Path(_saas.__file__).stat().st_mtime_ns
_SAAS_SETTINGS = None
_CURRENT_SAAS_USER = None
_ACCOUNT_STORE = None


def initialize_saas_settings() -> None:
    """Load SaaS settings for this run; fail closed on unsafe configuration."""
    global _SAAS_SETTINGS
    try:
        _SAAS_SETTINGS = _saas.SaaSSettings.from_env()
    except _saas.SaaSConfigurationError as _saas_config_error:
        st.error(f"Unsafe SaaS configuration: {_saas_config_error}")
        st.stop()
