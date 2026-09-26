"""Catalog plausibility: flag records whose T/S data cannot describe the product.

Purpose: stop the Studio and the portal from designing boxes, and suggesting
alternatives, for catalog records that are clearly wrong — e.g. a Focal 3-way
car kit that inherited a 65 mm midrange's parameters (Sd 22 cm², Qts 1.000,
Le 0). Crawled catalogs contain such records; this is the guard until they
are quarantined at the source.

Public API: ``plausibility_issues(name, *, qts, le_mh, sd_cm2) -> list[str]``,
pure and dependency-free (the portal keeps an identical copy in its vendored
``src/``). An empty list means "no known problem", not "verified".

Rules (each returns one short English reason):
- multi-driver product named as a kit / component system / "N vie";
- placeholder parameters: Qts exactly 1.0 together with Le = 0;
- nominal size in the name ("165 mm", '6.5"', "12 in") far from the Sd
  (Sd below 0.35× or above 2.5× the area expected for that size).

See docs/driver_plausibility.md.
"""
from __future__ import annotations

import math
import re

_MULTI_DRIVER = re.compile(
    r"\b(kit|component\s+(system|set)|components\s+set|\d\s*vie|[23]-?way\s+(kit|set|system|component))\b",
    re.IGNORECASE,
)
_SIZE_MM = re.compile(r"\b(\d{2,3})\s*mm\b", re.IGNORECASE)
# 6.5", 12 in, and mixed fractions such as 6-1/2" or 8-3/4".
_SIZE_IN = re.compile(
    r'\b(\d{1,2}(?:\.\d{1,2})?)(?:[- ](\d)/(\d{1,2}))?\s*(?:"|”|in\b|inch(?:es)?\b)', re.IGNORECASE)
# Oval / rectangular sizes ("2" x 7", 1-1/8" x 3-1/2") have no single diameter.
_OVAL = re.compile(r'(?:"|”|in\b|mm\b)\s*[x×]\s*\d', re.IGNORECASE)


def _nominal_mm(name: str) -> float | None:
    if _OVAL.search(name):
        return None
    match = _SIZE_MM.search(name)
    if match and 40 <= int(match.group(1)) <= 460:
        return float(match.group(1))
    match = _SIZE_IN.search(name)
    if match:
        inches = float(match.group(1))
        if match.group(2) and match.group(3) and int(match.group(3)):
            inches += int(match.group(2)) / int(match.group(3))
        if 1.5 <= inches <= 21:
            return inches * 25.4
    return None


def plausibility_issues(name: str, *, qts: float, le_mh: float, sd_cm2: float) -> list[str]:
    """Reasons this record's parameters are not trustworthy (empty: none found)."""
    issues = []
    if _MULTI_DRIVER.search(name or ""):
        issues.append("multi-driver product (kit or component system), not a single driver")
    if qts is not None and abs(float(qts) - 1.0) < 1e-9 and not le_mh:
        issues.append("placeholder Thiele/Small parameters (Qts 1.000, Le 0)")
    nominal = _nominal_mm(name or "")
    if nominal and sd_cm2 and sd_cm2 > 0:
        # Effective piston ≈ 80 % of the nominal frame diameter.
        expected = math.pi * (0.4 * nominal / 10.0) ** 2
        ratio = float(sd_cm2) / expected
        if ratio < 0.35 or ratio > 2.5:
            issues.append(f"Sd {float(sd_cm2):.0f} cm² does not match the {nominal:.0f} mm size in the name")
    return issues
