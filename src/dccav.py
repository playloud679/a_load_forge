"""
Compatibility facade for the split acoustic-load modules.

The implementation lives in ``engine`` (physics, simulation, optimizer and
analysis), ``presets`` (driver catalog and metadata) and ``pricing``
(retailer price records and value scoring).  Importing ``dccav`` exposes the
whole public API in both supported contexts: as a top-level module
(``import dccav`` with ``src/`` on ``sys.path``, used by ``ui_app.py``) and
as part of the package (``from src import dccav``, used by the tests).
"""

from __future__ import annotations

try:
    from .engine import *  # noqa: F401,F403
    from .presets import *  # noqa: F401,F403
    from .presets import _load_loudspeaker_database_presets  # noqa: F401
    from .pricing import *  # noqa: F401,F403
    from .pricing import _load_driver_price_records  # noqa: F401
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    from engine import *  # noqa: F401,F403
    from presets import *  # noqa: F401,F403
    from presets import _load_loudspeaker_database_presets  # noqa: F401
    from pricing import *  # noqa: F401,F403
    from pricing import _load_driver_price_records  # noqa: F401
