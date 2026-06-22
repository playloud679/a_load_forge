"""
Save / load flare_forge parameters to ``.flr`` files (JSON).

``.flr`` files are plain JSON with a branded extension so the OS associates
them with flare_forge and they don't get mistaken for generic data.
"""

import json
from pathlib import Path
from typing import Any


FLR_EXTENSION = ".flr"
META_KEY = "_flare_forge_meta"


def _build_meta() -> dict[str, Any]:
    """Return a small metadata block written into every ``.flr`` file."""
    try:
        from pathlib import Path as _P
        _ver = (_P(__file__).parent.parent / "VERSION").read_text().strip()
    except Exception:
        _ver = "unknown"
    return {"version": _ver, "format": 1}


def save(params: dict[str, Any], path: str | Path) -> Path:
    """Write *params* to a ``.flr`` file.

    Parameters
    ----------
    params : dict
        Flat dictionary of parameter names → JSON-serialisable values.
    path : str or Path
        Destination file path.  ``.flr`` is appended if missing.
    """
    path = Path(path)
    if path.suffix.lower() != FLR_EXTENSION:
        path = path.with_suffix(FLR_EXTENSION)
    payload: dict[str, Any] = {META_KEY: _build_meta()}
    payload.update(params)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load(path: str | Path) -> dict[str, Any]:
    """Read parameters from a ``.flr`` file.

    Returns the parameter dictionary (without the internal meta key).
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop(META_KEY, None)
    return raw
