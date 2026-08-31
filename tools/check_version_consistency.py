"""Fail when release version metadata is out of sync."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text().strip()
pyproject = (ROOT / "pyproject.toml").read_text()
readme = (ROOT / "README.md").read_text()
changelog = (ROOT / "CHANGELOG.md").read_text()

if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit(f"Invalid VERSION: {version!r}")
if f'version = "{version}"' not in pyproject:
    raise SystemExit("pyproject.toml version does not match VERSION")
if f"Version **{version}**" not in readme or f"version-{version}-blue" not in readme:
    raise SystemExit("README version badges/text do not match VERSION")
if not re.search(rf"^## {re.escape(version)} \(", changelog, re.MULTILINE):
    raise SystemExit("CHANGELOG top release does not match VERSION")
print(f"Version metadata consistent: {version}")
