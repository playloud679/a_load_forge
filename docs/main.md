# `main.py` - Compatibility CLI Entrypoint

**Path:** `src/main.py`

---

## Purpose

`main.py` is intentionally a thin compatibility wrapper around
`profile_generator.main()`.

It exists so both entrypoints keep working:

```bash
python -m src.main ...
horn ...
```

The actual CLI argument parsing, profile dispatch and STL generation live in
`profile_generator.py`. Do not add profile-specific logic here; otherwise the
project gets two divergent command-line interfaces.

---

## Public API

```python
def main(argv: list[str] | None = None) -> None
```

Delegates directly to `profile_generator.main(argv)`.

---

## Import Behavior

The module first tries the package import:

```python
from .profile_generator import main as _profile_main
```

If run directly as `python src/main.py`, it falls back to:

```python
from profile_generator import main as _profile_main
```

This fallback is only for developer convenience. The preferred execution mode is
`python -m src.main` or the installed `horn` console script.
