"""Backward-compatible alias for the neutral :mod:`acoustics` facade.

New code should import ``acoustics`` or ``src.acoustics``.  The historical
``dccav`` module remains available because external callers may still rely on
it, but it no longer defines the primary API or the active application path.
"""

from __future__ import annotations

try:
    from .acoustics import *  # noqa: F401,F403
    from .acoustics import (
        _load_driver_price_records,  # noqa: F401
        _load_loudspeaker_database_presets,  # noqa: F401
        _load_manufacturer_presets,  # noqa: F401
        _load_speakerboxlite_presets,  # noqa: F401
        _load_vituixcad_presets,  # noqa: F401
        _load_ztzaudio_presets,  # noqa: F401
    )
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    from acoustics import *  # noqa: F401,F403
    from acoustics import (  # type: ignore[no-redef]
        _load_driver_price_records,  # noqa: F401
        _load_loudspeaker_database_presets,  # noqa: F401
        _load_manufacturer_presets,  # noqa: F401
        _load_speakerboxlite_presets,  # noqa: F401
        _load_vituixcad_presets,  # noqa: F401
        _load_ztzaudio_presets,  # noqa: F401
    )
