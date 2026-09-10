"""Load Forge UI package.

Modules under ``src/ui`` implement the Streamlit dashboard. ``ui_app.py`` is the
entry point: it sets up the import path, hot-reloads changed modules and calls
``ui.app.main``. See ``docs/ui.md`` for the module map and
``docs/ui/<module>.md`` for per-module contracts.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
