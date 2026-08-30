"""Neutral public facade for all Load Forge acoustic-load modules.

The implementation is split across ``engine`` (physics, simulation,
optimization and analysis), ``presets`` (driver data), ``pricing`` and
``ranking``.  This facade exposes the complete public API in both supported
contexts: as a top-level module used by ``ui_app.py`` and as ``src.acoustics``.
"""

from __future__ import annotations

try:
    from .engine import *  # noqa: F401,F403
    from .port_cad import *  # noqa: F401,F403
    from .presets import *  # noqa: F401,F403
    from .presets import (
        _load_loudspeaker_database_presets,  # noqa: F401
        _load_manufacturer_presets,  # noqa: F401
        _load_speakerboxlite_presets,  # noqa: F401
        _load_vituixcad_presets,  # noqa: F401
        _load_ztzaudio_presets,  # noqa: F401
    )
    from .pricing import *  # noqa: F401,F403
    from .pricing import _load_driver_price_records  # noqa: F401
    from .ranking import *  # noqa: F401,F403
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    from engine import *  # noqa: F401,F403
    from port_cad import *  # noqa: F401,F403
    from presets import *  # noqa: F401,F403
    from presets import (  # type: ignore[no-redef]
        _load_loudspeaker_database_presets,  # noqa: F401
        _load_manufacturer_presets,  # noqa: F401
        _load_speakerboxlite_presets,  # noqa: F401
        _load_vituixcad_presets,  # noqa: F401
        _load_ztzaudio_presets,  # noqa: F401
    )
    from pricing import *  # noqa: F401,F403
    from pricing import _load_driver_price_records  # type: ignore[no-redef]  # noqa: F401
    from ranking import *  # noqa: F401,F403


def plausible_passive_radiators(
    ts: DriverTS,
    vb_l: float,
    target_fb_hz: float,
    pr_catalog: dict[str, Any] | None = None,
    max_pr_count: int = 2,
    max_added_mass_g: float = 400.0,
) -> list[PlausiblePRCombo]:
    """Return plausible passive radiator catalog combinations matching driver and box."""
    if pr_catalog is None:
        pr_catalog = PASSIVE_RADIATOR_PRESETS
    try:
        from . import engine as _eng
    except ImportError:
        import engine as _eng
    return _eng.plausible_passive_radiators(
        ts,
        vb_l,
        target_fb_hz,
        pr_catalog=pr_catalog,
        max_pr_count=max_pr_count,
        max_added_mass_g=max_added_mass_g,
    )


def suggest_best_pr_combo(
    ts: DriverTS,
    vb_l: float,
    target_fb_hz: float,
    pr_catalog: dict[str, Any] | None = None,
) -> PlausiblePRCombo | None:
    """Return the single best plausible passive radiator combination."""
    if pr_catalog is None:
        pr_catalog = PASSIVE_RADIATOR_PRESETS
    try:
        from . import engine as _eng
    except ImportError:
        import engine as _eng
    return _eng.suggest_best_pr_combo(
        ts, vb_l, target_fb_hz, pr_catalog=pr_catalog
    )
