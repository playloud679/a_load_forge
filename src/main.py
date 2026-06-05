"""
Compatibility CLI entrypoint.

The maintained command-line implementation lives in `profile_generator.py`.
Keeping this thin wrapper preserves `python -m src.main` and the `horn`
console script without duplicating profile dispatch logic.
"""

from __future__ import annotations

try:
    from .profile_generator import main as _profile_main
except ImportError:  # pragma: no cover - supports direct `python src/main.py`
    from profile_generator import main as _profile_main


def main(argv: list[str] | None = None) -> None:
    """Run the profile generator CLI."""
    _profile_main(argv)


if __name__ == "__main__":
    main()
