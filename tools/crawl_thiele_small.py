#!/usr/bin/env python3
"""Crawl manufacturer/catalog pages and merge Thiele/Small data into Load Forge.

The crawler is intentionally source-agnostic.  Give it one or more product
URLs with ``--seed`` and/or XML sitemaps with ``--sitemap``.  It respects
robots.txt, stays on the seeded domains, checkpoints progress, extracts HTML,
JSON-LD and (when pypdf is installed) PDF datasheets, normalizes units, and
merges only validated records into the existing preset dataset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import io
import json
import math
import re
import ssl
import subprocess
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover - system CA fallback
    certifi = None

ROOT = Path(__file__).resolve().parents[1]
# Manufacturer-site crawls are LSDB-free and safe to redistribute; they merge
# into their own catalog, never into the loudspeakerdatabase.com import.
DEFAULT_OUTPUT = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_CHECKPOINT = ROOT / "data" / "thiele_small_crawler_checkpoint.json"
DEFAULT_USER_AGENT = "LoadForge-TS-Crawler/1.0 (+https://github.com/playloud679/a_load_forge)"
RHO_AIR = 1.18
SPEED_OF_SOUND = 344.0
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where() if certifi else None)


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    aliases: tuple[str, ...]
    default_unit: str = ""


PARAMETERS = (
    ParameterSpec(
        "fs_hz",
        ("fs", "fo", "f0", "resonant frequency", "resonance frequency", "free air resonance",
         "fréquence de résonance", "frequence de resonance"),
        "hz",
    ),
    ParameterSpec(
        "vas_l",
        ("vas", "equivalent compliance volume", "equivalent volume", "equivalent air volume"),
        "l",
    ),
    ParameterSpec("qts", ("qts", "qt", "total q", "total factor")),
    ParameterSpec("qms", ("qms", "mechanical q", "mechanical factor")),
    ParameterSpec("qes", ("qes", "electrical q", "electrical factor")),
    ParameterSpec(
        "re_ohm",
        ("re", "revc", "dc resistance", "voice coil resistance", "dcr", "rdc",
         "dcr impedance", "résistance au cc", "resistance au cc"),
        "ohm",
    ),
    ParameterSpec(
        "sd_cm2",
        ("sd", "effective cone area", "effective piston area", "surface area of cone", "diaphragm area",
         "surface émissive", "surface emissive"),
        "cm2",
    ),
    ParameterSpec(
        "le_mh",
        (
            "le", "le1k", "l1khz", "l1k", "voice coil inductance",
            "voice coil inductance @ 1khz", "voice coil inductance @ 1 khz",
            "inductance of the voice coil l", "inductance of the voice coil",
            "inductance", "le at 1khz",
            "le at 1 khz", "le @1 khz", "le @ 1 khz",
        ),
        "mh",
    ),
    ParameterSpec(
        "le10k_mh",
        (
            "le10k", "l10khz", "l10k", "le at 10khz", "le at 10 khz",
            "le @10 khz", "le @ 10 khz", "voice coil inductance @ 10khz",
            "voice coil inductance @ 10 khz",
        ),
        "mh",
    ),
    ParameterSpec(
        "xmax_mm",
        (
            "xmax", "x max", "x-max", "linear excursion", "maximum linear excursion",
            "max linear excursion", "max. linear excursion", "excursion limit",
        ),
        "mm",
    ),
    ParameterSpec(
        "pe_w",
        (
            "pe", "pmax", "pwr", "aes power rating", "rated power aes",
            "lf nominal power handling", "nominal power handling",
            "rated power handling", "rms power handling", "rms power",
            "power handling capacity", "power capacity aes", "power capacity",
            "power handling p", "power rating", "power handling", "rated power",
            "rated power iec268-5",
            "potência", "potencia", "watts",
        ),
        "w",
    ),
    ParameterSpec("linear_travel_pp_mm", ("linear coil travel",), "mm"),
    ParameterSpec("mms_g", ("mms", "mmd", "moving mass", "diaphragm mass"), "g"),
    ParameterSpec("cms_mm_per_n", ("cms", "mechanical compliance", "suspension compliance"), "mm/n"),
    ParameterSpec("bl_tm", ("bl", "bxl", "force factor", "motor strength", "bl factor"), "tm"),
    ParameterSpec("rms_kg_s", ("rms", "mechanical resistance"), "kg/s"),
    ParameterSpec(
        "effective_radius_mm",
        ("equivalent diaphragm radius", "effective diaphragm radius", "effective piston radius"),
        "mm",
    ),
    ParameterSpec(
        "effective_diameter_mm",
        ("effective diaphragm diameter", "effective piston diameter"),
        "mm",
    ),
    ParameterSpec(
        "vd_l",
        ("vd", "linear displacement volume", "volume displacement", "displacement volume"),
        "l",
    ),
    # Published physical/layout data.  These values are never derived from Sd
    # or nominal frame size: they are accepted only when the source labels the
    # measurement explicitly.
    ParameterSpec(
        "mounting_depth_mm",
        ("mounting depth", "mount depth", "required depth", "installation depth"),
        "mm",
    ),
    ParameterSpec(
        "overall_diameter_mm",
        (
            "overall diameter", "maximum outside diameter",
            "maximum overall diameter", "max overall diameter", "frame diameter",
            "max overall dimension (on ears)", "maximum overall dimension (on ears)",
            "max overall dimension on ears", "maximum overall dimension on ears",
        ),
        "mm",
    ),
    ParameterSpec(
        "cutout_diameter_mm",
        (
            "baffle cutout diameter", "bafﬂe cutout diameter", "baffle hole diameter",
            "mounting cutout diameter", "cutout diameter", "cut-out diameter",
            "baffle opening diameter",
        ),
        "mm",
    ),
    ParameterSpec(
        "depth_mm",
        ("overall depth", "driver depth", "total depth", "maximum depth", "max depth"),
        "mm",
    ),
    ParameterSpec(
        "bolt_circle_mm",
        (
            "bolt circle diameter", "mounting bolt circle", "mounting holes b.c.d.",
            "mounting holes bcd", "pcd", "pitch circle diameter",
        ),
        "mm",
    ),
    ParameterSpec(
        "mounting_hole_count",
        ("number of mounting holes", "mounting hole count", "mounting holes quantity"),
    ),
    ParameterSpec(
        "mounting_hole_diameter_mm",
        (
            "mounting hole diameter", "mounting holes diameter",
            "mounting hole dimensions", "fixing hole diameter",
        ),
        "mm",
    ),
    ParameterSpec(
        "weight_kg",
        ("speaker net mass", "net weight", "driver weight", "unit weight", "weight"),
        "kg",
    ),
    # Additional published numeric specifications retained for future product
    # work even though the acoustic solver does not consume them today.
    ParameterSpec(
        "nominal_diameter_in",
        ("nominal overall diameter", "nominal diameter", "nominal frame diameter"),
        "in",
    ),
    ParameterSpec(
        "nominal_impedance_ohm",
        ("nominal impedance", "rated impedance", "z nominal", "znom"),
        "ohm",
    ),
    ParameterSpec(
        "sensitivity_db",
        (
            "sensitivity 1w/1m", "sensitivity 1w 1m", "sensitivity 1 w 1 m",
            "sensitivity 2.83v/1m", "sensitivity 2.83v 1m",
            "sensitivity 2.83 v 1 m", "sensitivity", "spl 1w/1m", "spl 1w 1m",
        ),
        "db",
    ),
    ParameterSpec(
        "voice_coil_diameter_mm",
        ("voice coil diameter", "voice-coil diameter", "voice coil size"),
        "mm",
    ),
    ParameterSpec(
        "xmech_mm",
        ("xmech", "x mech", "maximum mechanical excursion", "mechanical excursion limit"),
        "mm",
    ),
    ParameterSpec(
        "efficiency_pct",
        ("reference efficiency", "efficiency", "eta zero", "n0"),
        "%",
    ),
    ParameterSpec(
        "magnet_weight_kg",
        ("magnet weight", "magnet mass"),
        "kg",
    ),
    ParameterSpec(
        "flux_density_t",
        ("flux density", "magnetic flux density", "gap flux density"),
        "t",
    ),
)
PARAMETER_BY_KEY = {item.key: item for item in PARAMETERS}
REQUIRED_DRIVER_FIELDS = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")
OPTIONAL_DRIVER_FIELDS = (
    "qes", "le_mh", "le10k_mh", "xmax_mm", "pe_w", "mms_g",
    "cms_mm_per_n", "bl_tm",
)
MECHANICAL_FIELDS = (
    "overall_diameter_mm", "cutout_diameter_mm", "depth_mm", "mounting_depth_mm",
    "bolt_circle_mm", "mounting_hole_count", "mounting_hole_diameter_mm", "weight_kg",
)
PUBLISHED_SPEC_FIELDS = (
    "nominal_impedance_ohm", "sensitivity_db", "voice_coil_diameter_mm",
    "xmech_mm", "efficiency_pct", "magnet_weight_kg", "flux_density_t",
    "nominal_diameter_in",
)
EXPLICIT_UNIT_FIELDS = {
    "pe_w", "sensitivity_db", "efficiency_pct", "overall_diameter_mm",
    "cutout_diameter_mm", "depth_mm", "mounting_depth_mm", "bolt_circle_mm",
    "mounting_hole_diameter_mm", "weight_kg", "nominal_impedance_ohm",
    "voice_coil_diameter_mm", "xmech_mm", "magnet_weight_kg", "flux_density_t",
    "nominal_diameter_in", "cms_mm_per_n",
}
NUMBER_RE = r"[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][-+]?\d+)?"
INCH_SIZE_RE = re.compile(
    r"(?<![\d./])"
    r"(?P<whole>\d+(?:[.,]\d+)?)"
    r"(?:\s*[- ]\s*(?P<numerator>\d+)\s*/\s*(?P<denominator>\d+))?"
    r"\s*(?:inch(?:es)?|in\.?|[\"″])(?=\s|$|[),/x×])",
    re.I,
)
UNIT_RE = r"(?:k\s*hz|hz|square\s+(?:inches?|centimeters?|meters?)|sq\s*\.?\s*in(?:ches)?|sq\s*\.?\s*m(?:eters?)?|m(?:\s*\^?\s*3|³)|dm(?:\s*\^?\s*3|³)|ml|cm\s*(?:\^?\s*2|²)|k\s*/?\s*mm\s*(?:\^?\s*2|²|/2)|mm\s*(?:\^?\s*2|²)|m\s*(?:\^?\s*2|²)|in(?:\s*\^?\s*2|²)|ft\s*\.?\s*(?:\^?\s*3|³)|lit(?:er|re)s?|lbs?|pounds?|oz|ounces?|kg|kilograms?|kgs?|grams?|mg|[gG]|[lL]|k?ohms?|Ω|mΩ|mh|µh|μh|uh|henry|h|mm|cm|inch(?:es)?|in|[\"”″]|kw|w\s*_?\s*rms|watts?|w|m/n|mm/n|µm/n|μm/n|um/n|t\s*[·*]?\s*m|tm|n/a|n\s*s/m|kg/s|dba|db|t|gauss|%)?"
# Same alternation as UNIT_RE but mandatory (no trailing "?"), for datasheets
# that print "Label Unit Value" instead of "Label Value Unit" (e.g. BMS PDFs:
# "Fs Hz 29.8").
UNIT_RE_REQUIRED = UNIT_RE[:-1]

RANGES = {
    "fs_hz": (1.0, 2000.0),
    "vas_l": (0.0001, 100_000.0),
    "qts": (0.005, 10.0),
    "qms": (0.01, 1000.0),
    "qes": (0.005, 100.0),
    "re_ohm": (0.01, 1000.0),
    "sd_cm2": (0.01, 100_000.0),
    "le_mh": (0.0, 1000.0),
    "le10k_mh": (0.0, 1000.0),
    "xmax_mm": (0.0, 500.0),
    "pe_w": (0.0, 100_000.0),
    "mms_g": (0.001, 100_000.0),
    "cms_mm_per_n": (0.000001, 1000.0),
    "bl_tm": (0.0, 1000.0),
    "rms_kg_s": (0.000001, 100_000.0),
    "effective_radius_mm": (0.01, 5000.0),
    "effective_diameter_mm": (0.01, 10_000.0),
    "vd_l": (0.000001, 100_000.0),
    "linear_travel_pp_mm": (0.0, 1000.0),
    "overall_diameter_mm": (1.0, 5000.0),
    "cutout_diameter_mm": (1.0, 5000.0),
    "depth_mm": (1.0, 5000.0),
    "mounting_depth_mm": (1.0, 5000.0),
    "bolt_circle_mm": (1.0, 5000.0),
    "mounting_hole_count": (1.0, 100.0),
    "mounting_hole_diameter_mm": (0.1, 100.0),
    "weight_kg": (0.05, 500.0),
    "nominal_impedance_ohm": (0.1, 256.0),
    "sensitivity_db": (20.0, 150.0),
    "voice_coil_diameter_mm": (1.0, 500.0),
    "xmech_mm": (0.0, 500.0),
    "efficiency_pct": (0.0, 100.0),
    "magnet_weight_kg": (0.01, 500.0),
    "flux_density_t": (0.001, 10.0),
    "nominal_diameter_in": (0.5, 32.0),
}


@dataclass(frozen=True)
class Measurement:
    key: str
    value: float
    raw_value: str
    unit: str
    label: str
    method: str


@dataclass
class PageData:
    title: str = ""
    h1: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    jsonld: list[object] = field(default_factory=list)
    embedded_measurements: list[Measurement] = field(default_factory=list)


@dataclass(frozen=True)
class FetchResult:
    url: str
    content_type: str
    content: bytes


@dataclass
class CrawlConfig:
    seeds: list[str]
    sitemaps: list[str]
    output: Path = DEFAULT_OUTPUT
    checkpoint: Path = DEFAULT_CHECKPOINT
    source_name: str = "Web crawler"
    brand_hint: str = ""
    allowed_domains: set[str] = field(default_factory=set)
    include_patterns: tuple[re.Pattern, ...] = ()
    exclude_patterns: tuple[re.Pattern, ...] = ()
    max_pages: int = 200
    max_depth: int = 2
    timeout_s: float = 20.0
    sleep_s: float = 1.0
    min_confidence: float = 0.75
    follow_links: bool = True
    overwrite: bool = False
    refresh_source: str = ""
    fresh: bool = False
    dry_run: bool = False
    user_agent: str = DEFAULT_USER_AGENT


class DocumentParser(HTMLParser):
    """Collect visible text, links, metadata and JSON-LD without dependencies."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.meta: dict[str, str] = {}
        self.jsonld_texts: list[str] = []
        self.raw_script_texts: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._ignored_depth = 0
        self._jsonld_depth = 0
        self._jsonld_parts: list[str] = []
        self._script_depth = 0
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag in {"style", "noscript"}:
            self._ignored_depth += 1
        elif tag == "script":
            if "ld+json" in values.get("type", "").casefold():
                self._jsonld_depth += 1
                self._jsonld_parts = []
            else:
                self._ignored_depth += 1
                # SPA hydration blobs (window.__remixContext/__NUXT__/etc.)
                # sometimes carry T/S data as JS that isn't application/ld+json;
                # capture raw script bodies too so page() can try to parse them.
                self._script_depth += 1
                self._script_parts = []
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self.h1_parts: # only first h1
            self._in_h1 = True
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])
        elif tag == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop")
            if key and values.get("content"):
                self.meta[key.casefold()] = values["content"].strip()
        if tag in {"br", "p", "div", "li", "tr", "td", "th", "dt", "dd", "section", "article"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "script":
            if self._jsonld_depth:
                self._jsonld_depth -= 1
                raw = "".join(self._jsonld_parts).strip()
                if raw:
                    self.jsonld_texts.append(raw)
                self._jsonld_parts = []
            elif self._ignored_depth:
                self._ignored_depth -= 1
            if self._script_depth:
                self._script_depth -= 1
                raw_script = "".join(self._script_parts).strip()
                if raw_script:
                    self.raw_script_texts.append(raw_script)
                self._script_parts = []
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        if tag in {"p", "div", "li", "tr", "td", "th", "dt", "dd", "section", "article"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str):
        if self._script_depth:
            self._script_parts.append(data)
        if self._jsonld_depth:
            self._jsonld_parts.append(data)
            return
        if self._ignored_depth:
            return
        value = data.strip()
        if not value:
            return
        self.text_parts.append(value)
        self.text_parts.append(" ")
        if self._in_title:
            self.title_parts.append(value)
        if self._in_h1:
            self.h1_parts.append(value)

    def page(self) -> PageData:
        nodes: list[object] = []
        for raw in self.jsonld_texts:
            try:
                try:
                    nodes.append(json.loads(raw))
                except json.JSONDecodeError:
                    # Some otherwise valid storefront JSON-LD contains literal
                    # newlines/tabs inside description strings.  Python's
                    # non-strict mode preserves the structured Product data.
                    nodes.append(json.loads(raw, strict=False))
            except json.JSONDecodeError:
                continue
        nodes.extend(embedded_js_objects(self.raw_script_texts))
        text = "\n".join(
            line.strip() for line in "".join(self.text_parts).splitlines() if line.strip()
        )
        return PageData(
            title=" ".join(self.title_parts).strip(),
            h1=" ".join(self.h1_parts).strip(),
            text=text,
            links=self.links,
            meta=self.meta,
            jsonld=nodes,
        )


def log(message: str):
    print(message, flush=True)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def normalized_label(value: str) -> str:
    value = value.casefold().replace("thiele/small", " ").replace("thiele-small", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def canonical_parameter(label: str) -> str | None:
    normalized = normalized_label(label)
    compact = normalized.replace(" ", "")
    # Exact aliases across the whole schema must win before any broad
    # substring match (e.g. ``mounting holes diameter`` over ``diameter`` or
    # ``magnet weight`` over a generic ``weight`` field).
    for spec in PARAMETERS:
        for alias in spec.aliases:
            alias_norm = normalized_label(alias)
            if normalized == alias_norm or compact == alias_norm.replace(" ", ""):
                return spec.key
    for spec in PARAMETERS:
        for alias in spec.aliases:
            alias_norm = normalized_label(alias)
            if alias_norm in {"depth", "weight", "sensitivity", "efficiency"}:
                continue
            if len(alias_norm) > 3 and alias_norm in normalized:
                return spec.key
    return None


def parse_number(raw: object) -> float | None:
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if math.isfinite(value) else None
    match = re.search(NUMBER_RE, str(raw).replace("\u00a0", " "))
    if not match:
        return None
    token = match.group(0)
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token and re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})+", token):
        # A leading zero unambiguously denotes a decimal in manufacturer
        # datasheets (for example ``0,019 kg`` = 19 g), not a thousands
        # separator. Treating it as 19 would inflate converted masses and
        # compliances by three orders of magnitude.
        if re.match(r"[-+]?0,", token):
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
    else:
        token = token.replace(",", ".")
    try:
        value = float(token)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def normalize_unit(raw: str) -> str:
    unit = raw.casefold().strip().replace("μ", "µ").replace("ω", "ohm").replace("Ω", "ohm")
    unit = unit.replace("²", "2").replace("³", "3").replace("^", "")
    unit = unit.replace("·", "").replace("*", "").replace("_", "").replace(" ", "").replace(".", "")
    unit = unit.replace("/2", "2")
    unit = unit.replace("k/mm", "kmm")
    aliases = {
        "liter": "l", "liters": "l", "litre": "l", "litres": "l", "lit": "l", "dm3": "l",
        "ohms": "ohm", "ohm": "ohm", "milliohm": "mohm", "mω": "mohm",
        "henry": "h", "watts": "w", "watt": "w", "wrms": "w", "grams": "g", "gram": "g",
        "inch": "in", "inches": "in", "µh": "uh", "µm/n": "um/n",
        '"': "in", "”": "in", "″": "in",
        "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
        "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
        "ounce": "oz", "ounces": "oz",
        "tsm": "tm", "n/a": "tm", "ns/m": "kg/s",
        "sqin": "in2", "sqinches": "in2", "squareinch": "in2", "squareinches": "in2",
        "sqcm": "cm2", "squarecentimeter": "cm2", "squarecentimeters": "cm2",
        "sqm": "m2", "sqmeters": "m2", "sqmeter": "m2",
        "squaremeter": "m2", "squaremeters": "m2",
        "dba": "db", "gauss": "gauss", "%": "%",
    }
    return aliases.get(unit, unit)


def convert_measurement(key: str, raw_value: object, raw_unit: str = "") -> float | None:
    raw_text = str(raw_value).strip()
    # Moving mass is conventionally reported in grams, where a three-digit
    # comma suffix is overwhelmingly a decimal (``13,525 g``). Keep the
    # generic parser's thousands-separator behavior for unrelated fields.
    if key == "mms_g" and re.fullmatch(r"[-+]?\d{1,3},\d{3}", raw_text):
        value = float(raw_text.replace(",", "."))
    else:
        value = parse_number(raw_value)
    if value is None:
        return None
    unit = normalize_unit(raw_unit) or PARAMETER_BY_KEY[key].default_unit
    factors = {
        "fs_hz": {"hz": 1.0, "khz": 1000.0},
        "vas_l": {"l": 1.0, "m3": 1000.0, "ft3": 28.316846592, "ml": 0.001},
        "re_ohm": {"ohm": 1.0, "mohm": 0.001},
        "sd_cm2": {
            "cm2": 1.0, "m2": 10_000.0, "kmm2": 10.0,
            "mm2": 0.01, "in2": 6.4516,
            "cm": 1.0, "in": 6.4516, "m": 10_000.0, "mm": 0.01,
        },
        "le_mh": {"mh": 1.0, "h": 1000.0, "uh": 0.001},
        "le10k_mh": {"mh": 1.0, "h": 1000.0, "uh": 0.001},
        "xmax_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "pe_w": {"w": 1.0, "kw": 1000.0},
        "mms_g": {"g": 1.0, "kg": 1000.0, "mg": 0.001},
        "cms_mm_per_n": {"mm/n": 1.0, "m/n": 1000.0, "um/n": 0.001},
        "bl_tm": {"tm": 1.0},
        "rms_kg_s": {"kg/s": 1.0},
        "effective_radius_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "effective_diameter_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "vd_l": {"l": 1.0, "m3": 1000.0, "ft3": 28.316846592, "ml": 0.001},
        "linear_travel_pp_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "nominal_diameter_in": {"in": 1.0, "mm": 1.0 / 25.4, "cm": 10.0 / 25.4},
        "overall_diameter_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "cutout_diameter_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "depth_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "mounting_depth_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "bolt_circle_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "mounting_hole_count": {"": 1.0},
        "mounting_hole_diameter_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "weight_kg": {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": 0.45359237, "oz": 0.028349523125},
        "nominal_impedance_ohm": {"ohm": 1.0, "mohm": 0.001},
        "sensitivity_db": {"db": 1.0},
        "voice_coil_diameter_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "xmech_mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
        "efficiency_pct": {"%": 1.0},
        "magnet_weight_kg": {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": 0.45359237, "oz": 0.028349523125},
        "flux_density_t": {"t": 1.0, "gauss": 0.0001},
        "qts": {"": 1.0}, "qms": {"": 1.0}, "qes": {"": 1.0},
    }
    allowed = factors.get(key, {"": 1.0})
    if unit not in allowed:
        if key in {"qts", "qms", "qes"}:
            unit = ""
        else:
            return None
    converted = value * allowed[unit]
    low, high = RANGES[key]
    return converted if low <= converted <= high else None


def split_value_and_unit(raw: object, unit_hint: str = "") -> tuple[object, str]:
    if isinstance(raw, dict):
        unit_hint = str(raw.get("unitText") or raw.get("unitCode") or unit_hint)
        raw = raw.get("value", raw.get("maxValue", raw.get("minValue", "")))
    text = str(raw)
    match = re.search(rf"({NUMBER_RE})\s*({UNIT_RE})", text, re.I)
    if match:
        return match.group(1), match.group(2) or unit_hint
    return raw, unit_hint


def measurement_from_pair(label: str, raw: object, unit: str, method: str) -> Measurement | None:
    key = canonical_parameter(label)
    if not key:
        return None
    label_normalized = normalized_label(label)
    if key == "weight_kg" and any(
        word in label_normalized for word in ("shipping", "packaged", "gross")
    ):
        return None
    if key == "depth_mm" and any(
        word in label_normalized for word in ("cabinet", "enclosure", "box", "port", "vent")
    ):
        return None
    if key == "overall_diameter_mm" and "nominal" in label_normalized:
        return None
    raw_value, parsed_unit = split_value_and_unit(raw, unit)
    if key in EXPLICIT_UNIT_FIELDS and not normalize_unit(parsed_unit):
        return None
    value = convert_measurement(key, raw_value, parsed_unit)
    if value is None:
        return None
    return Measurement(key, value, str(raw_value), parsed_unit, label.strip(), method)


def walk_json(value: object) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def embedded_js_objects(raw_script_texts: list[str]) -> list[object]:
    """Parse SPA hydration blobs like ``window.__remixContext = {...};``.

    Many modern storefronts (Remix/Nuxt/Next) render the product page
    server-side but only put the *visible* spec table in a summary form,
    with the full structured data (including T/S params) embedded as a
    JSON-serialized object assigned to a ``window.*`` global. This looks for
    that pattern and parses it the same way as JSON-LD, so it flows through
    the existing ``jsonld_measurements`` extraction.
    """
    found: list[object] = []
    for text in raw_script_texts:
        if not re.search(r"window\.\w+\s*=\s*\{", text):
            continue
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue
        try:
            try:
                found.append(json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                found.append(json.loads(text[start : end + 1], strict=False))
        except (json.JSONDecodeError, ValueError):
            continue
    return found


def jsonld_measurements(nodes: list[object]) -> list[Measurement]:
    found: list[Measurement] = []
    for root in nodes:
        for node in walk_json(root):
            # SPA hydration blobs frequently store one measurement per object.
            if (
                isinstance(node.get("label"), str)
                and "value" in node
                and not isinstance(node["value"], (dict, list))
            ):
                units = node.get("units")
                unit = units.get("default", "") if isinstance(units, dict) else str(units or "")
                if item := measurement_from_pair(node["label"], node["value"], unit, "jsonld.field"):
                    found.append(item)
            for prop_key in ("additionalProperty", "additionalProperties"):
                props = node.get(prop_key, [])
                if isinstance(props, dict):
                    props = [props]
                if isinstance(props, list):
                    for prop in props:
                        if not isinstance(prop, dict):
                            continue
                        label = str(prop.get("name") or prop.get("propertyID") or "")
                        raw = prop.get("value", prop.get("maxValue", ""))
                        unit = str(prop.get("unitText") or prop.get("unitCode") or "")
                        if item := measurement_from_pair(label, raw, unit, "jsonld.additionalProperty"):
                            found.append(item)
            for key, raw in node.items():
                if key.startswith("@") or isinstance(raw, (dict, list)):
                    continue
                if item := measurement_from_pair(str(key), raw, "", "jsonld.field"):
                    found.append(item)
    return found


def table_measurements(text: str, method: str = "html.table") -> list[Measurement]:
    """Extract row tables and paired label/value columns from flattened text."""
    found: list[Measurement] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Layout-preserving PDF extraction commonly yields:
    # ``DC Resistance    Re    W    5.6 (+/-0.6)``.
    for line in lines:
        columns = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
        if len(columns) < 2:
            continue
        key_index = next(
            (index for index, part in enumerate(columns[:3]) if canonical_parameter(part)),
            None,
        )
        if key_index is None:
            continue
        label = columns[key_index]
        key = canonical_parameter(label)
        for value_index in range(key_index + 1, len(columns)):
            token = columns[value_index]
            if (
                token == "1"
                or token.casefold() == "w"
                or re.fullmatch(UNIT_RE_REQUIRED, token, re.I)
            ):
                continue
            if parse_number(token) is None:
                continue
            unit = columns[value_index - 1] if value_index > key_index + 1 else ""
            if key in {"qts", "qms", "qes"} and unit == "1":
                unit = ""
            # Some PHL PDFs map the ohm glyph to W in their embedded font.
            if key == "re_ohm" and unit.casefold() == "w":
                unit = "ohm"
            if item := measurement_from_pair(label, token, unit, method):
                found.append(item)
            break

    # Responsive HTML often renders the labels in one div and all values in
    # the adjacent div (Oberton). Pair both blocks by position.
    for marker_index, marker in enumerate(lines):
        marker_normalized = normalized_label(marker)
        if "thiele" not in marker.casefold() and marker_normalized != "specifications":
            continue
        block = lines[marker_index + 1 : marker_index + 80]
        first_value = next(
            (index for index, line in enumerate(block) if re.match(rf"^[+±]?\s*{NUMBER_RE}", line)),
            None,
        )
        if first_value is None or first_value < 3:
            continue
        labels = block[:first_value]
        values = block[first_value : first_value + len(labels)]
        # Ragged spec blocks pair by position; tolerate trailing truncation.
        for label, raw_value in zip(labels, values):  # noqa: B905
            key = canonical_parameter(label)
            if key in (*MECHANICAL_FIELDS, *PUBLISHED_SPEC_FIELDS):
                continue
            if key and (
                item := measurement_from_pair(label, raw_value, "", method)
            ):
                found.append(item)
    return found


def text_measurements(text: str) -> list[Measurement]:
    found: list[Measurement] = []
    for spec in PARAMETERS:
        aliases = sorted(spec.aliases, key=len, reverse=True)
        alias_pattern = "|".join(re.escape(alias).replace(r"\ ", r"\s+") for alias in aliases)
        signed_value_prefix = r"(?:(?:±|\+\s*/\s*[-−])\s*)?"
        # MISCO prints ``Fs (Hz) +/- 15% 23``: the first number is the
        # production tolerance, not the resonance frequency. Restrict this
        # exception to Fs so one-way excursion such as ``Xmax +/- 9 mm``
        # continues to mean 9 mm.
        tolerance_prefix = (
            rf"(?:(?:±|\+\s*/\s*[-−])\s*{NUMBER_RE}\s*%\s*)?"
            if spec.key == "fs_hz"
            else ""
        )
        footnote_prefix = r"(?:(?:[*¹²³]+|\d{1,2})\s+)?" if spec.key == "pe_w" else ""
        pattern = re.compile(
            rf"(?<![A-Za-z0-9])(?P<label>{alias_pattern})(?![A-Za-z0-9])"
            rf"(?:\)|\.)?\s*(?:\([^)]{{0,30}}\)|\[[^]]{{0,30}}\])?"
            rf"\s*(?:[*¹²³]+)?\s*(?:(?:[:=\-–—：]|is)\s*)?"
            rf"{footnote_prefix}{tolerance_prefix}{signed_value_prefix}"
            rf"(?P<value>{NUMBER_RE})[\t \r\n]{{0,16}}"
            rf"\[?(?P<unit>{UNIT_RE})\]?",
            re.I,
        )
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 32):match.start()].casefold()
            if spec.key == "depth_mm" and re.search(r"mount(?:ing)?\s+$", prefix):
                continue
            if spec.key == "weight_kg" and re.search(r"(?:magnet|shipping)\s+$", prefix):
                continue
            if spec.key == "overall_diameter_mm" and re.search(r"nominal\s+$", prefix):
                continue
            # A generic ``power rating`` substring inside ``continuous power
            # rating`` or ``program power rating`` is not Pe/AES/RMS power.
            # Those values are usually 2x the thermal rating and must not win
            # merely because they occur first on the page.
            if spec.key == "pe_w":
                if re.search(
                    r"(?:continuous|program|maximum|max\.?|hf(?:\s+nominal)?)[ \t]+$",
                    prefix,
                ):
                    continue
            unit = match.group("unit") or ""
            if spec.key in EXPLICIT_UNIT_FIELDS and not normalize_unit(unit):
                continue
            value = convert_measurement(spec.key, match.group("value"), unit)
            if value is not None:
                found.append(Measurement(
                    spec.key, value, match.group("value"), unit,
                    match.group("label"), "html.text",
                ))

        # Fallback for "Label Unit Value" column layouts (unit printed right
        # after the label, before the number) instead of the usual
        # "Label Value Unit". Requires an explicit, unambiguous unit token so
        # it can't misfire on ordinary "Label: Value Unit" text.
        pattern_lu = re.compile(
            rf"(?<![A-Za-z0-9])(?P<label>{alias_pattern})(?![A-Za-z0-9])"
            rf"(?:\)|\.)?\s*(?:\([^)]{{0,30}}\)|\[[^]]{{0,30}}\])?\s*(?:[:=]\s*)?"
            rf"(?P<unit>{UNIT_RE_REQUIRED})\s+"
            rf"{tolerance_prefix}{signed_value_prefix}"
            rf"(?P<value>{NUMBER_RE})(?![A-Za-z0-9])",
            re.I,
        )
        for match in pattern_lu.finditer(text):
            prefix = text[max(0, match.start() - 32):match.start()].casefold()
            if spec.key == "overall_diameter_mm" and re.search(r"nominal\s+$", prefix):
                continue
            unit = match.group("unit") or ""
            if spec.key in EXPLICIT_UNIT_FIELDS and not normalize_unit(unit):
                continue
            value = convert_measurement(spec.key, match.group("value"), unit)
            if value is not None:
                found.append(Measurement(
                    spec.key, value, match.group("value"), unit,
                    match.group("label"), "html.text",
                ))

    # A bare "Depth" is too ambiguous globally (it may describe a cabinet or
    # package), but manufacturers such as Eminence place it inside an explicit
    # MOUNTING INFORMATION block. Limit the match to that section and stop at
    # the next known section heading.
    mounting_block = re.search(
        r"(?is)\bmounting\s+information\b(?P<body>.{0,2500}?)"
        r"(?=\b(?:materials?\s+of\s+construction|packed\s+dimensions|frequency\s+response|"
        r"ac[uú]stica\s+beyma|thiele.small\s+parameters)\b|$)",
        text,
    )
    if mounting_block:
        depth = re.search(
            rf"(?im)^\s*(?P<label>depth)\s*(?P<value>{NUMBER_RE})\s*"
            rf"(?P<unit>mm|cm|inches?|in|[\"”″])",
            mounting_block.group("body"),
        )
        if depth:
            value = convert_measurement("depth_mm", depth.group("value"), depth.group("unit"))
            if value is not None:
                found.append(Measurement(
                    "depth_mm", value, depth.group("value"), depth.group("unit"),
                    depth.group("label"), "html.text",
                ))
        # Beyma's layout keeps the cutout heading on one line and the actual
        # front-mount dimension on the next. Accept that pair only inside the
        # explicit mounting section; a free-standing "front mount" value is
        # otherwise too ambiguous to treat as a baffle cutout.
        cutout = re.search(
            rf"(?im)^\s*(?P<label>baffle\s+cutout\s+diameter)\s*:?\s*$\s*"
            rf"^\s*-?\s*front\s+mount\s+(?P<value>{NUMBER_RE})\s*"
            rf"(?P<unit>mm|cm|inches?|in|[\"”″])",
            mounting_block.group("body"),
        )
        if cutout:
            value = convert_measurement(
                "cutout_diameter_mm", cutout.group("value"), cutout.group("unit")
            )
            if value is not None:
                found.append(Measurement(
                    "cutout_diameter_mm", value, cutout.group("value"), cutout.group("unit"),
                    cutout.group("label"), "html.text",
                ))
    # PHL mounting tables publish a metric fastener prescription as
    # ``Bolt number & Metric diameter  -  4x M5``. The leading number is an
    # explicit hole count, while M5 describes the bolt and must not be stored
    # as the drilled-hole diameter.
    phl_bolts = re.search(
        r"(?i)bolt\s+number\s*(?:&|and)\s*metric\s+diameter"
        r"[^\n]{0,30}?\b(?P<count>\d{1,2})\s*[x×]\s*M\s*\d+(?:[.,]\d+)?",
        text,
    )
    if phl_bolts:
        found.append(Measurement(
            "mounting_hole_count", float(phl_bolts.group("count")),
            phl_bolts.group("count"), "", "Bolt number & Metric diameter",
            "html.text",
        ))
    oberton_mounting = re.search(
        r"(?is)\bmounting\s+information\b\s*"
        r"overall\s+diameter\s+baffle\s+hole\s+diameter\s+mounting\s+holes\s+"
        r"bolt\s+circle\s+diameter\s+overall\s+depth\s+net\s+weight\s+"
        rf"(?P<overall>{NUMBER_RE})\s*mm\s+"
        rf"(?P<cutout>{NUMBER_RE})\s*mm\s+"
        rf"(?P<holes>\d{{1,2}})\s+[^\n]{{0,50}}?\s+"
        rf"(?P<pcd_a>{NUMBER_RE})(?:\s*/\s*(?P<pcd_b>{NUMBER_RE}))?\s*mm\s+"
        rf"(?P<depth>{NUMBER_RE})\s*mm\s+"
        rf"(?P<weight>{NUMBER_RE})\s*kg",
        text,
    )
    if oberton_mounting:
        # A slotted pattern such as 438/441 mm has two orthogonal pitch
        # diameters; store the larger published envelope in the scalar PCD
        # field and retain the complete raw value in provenance.
        pcd_values = [
            parse_number(oberton_mounting.group("pcd_a")),
            parse_number(oberton_mounting.group("pcd_b")),
        ]
        pcd = max(value for value in pcd_values if value is not None)
        values = {
            "overall_diameter_mm": ("overall", "mm", "Overall Diameter"),
            "cutout_diameter_mm": ("cutout", "mm", "Baffle Hole Diameter"),
            "mounting_hole_count": ("holes", "", "Mounting Holes"),
            "depth_mm": ("depth", "mm", "Overall Depth"),
            "weight_kg": ("weight", "kg", "Net Weight"),
        }
        for key, (group, unit, label) in values.items():
            raw = oberton_mounting.group(group)
            value = convert_measurement(key, raw, unit)
            if value is not None:
                found.append(Measurement(key, value, raw, unit, label, "html.table"))
        raw_pcd = oberton_mounting.group("pcd_a")
        if oberton_mounting.group("pcd_b"):
            raw_pcd += "/" + oberton_mounting.group("pcd_b")
        found.append(Measurement(
            "bolt_circle_mm", pcd, raw_pcd, "mm", "Bolt Circle Diameter", "html.table",
        ))
    # P.Audio datasheets contain a known swapped pair of captions: the row
    # named "Mounting Hole Diameter" carries the PCD, while "Bolt Circle
    # Diameter" carries ``8 x Ø6.5``. Prefer the unambiguous drawing callout
    # ``PCD 265.2 mm`` and use the count/diameter tuple only for actual holes.
    paudio_heading = re.search(r"(?i)\bmounting\s+and\s+shipping\s+info\b", text)
    paudio_block = None
    if paudio_heading:
        section = text[paudio_heading.end():paudio_heading.end() + 4000]
        stop = re.search(r"(?i)\b(?:frequency\s+response|recone\s+kit)\b", section)
        paudio_block = section[:stop.start()] if stop else section
    if paudio_block:
        body = paudio_block
        aliases = {
            "overall_diameter_mm": "Diameter",
            "cutout_diameter_mm": "Baffle Cutout Diameter",
            "depth_mm": "Depth",
            "weight_kg": "Net Weight",
        }
        for key, label in aliases.items():
            match = re.search(
                rf"(?im)^\s*{re.escape(label)}\s+(?P<value>{NUMBER_RE})\s*"
                rf"(?P<unit>mm|kg)\b",
                body,
            )
            if match:
                value = convert_measurement(key, match.group("value"), match.group("unit"))
                if value is not None:
                    found.append(Measurement(
                        key, value, match.group("value"), match.group("unit"),
                        label, "pdf.table",
                    ))
        pcd = re.search(rf"(?i)\bPCD\s+(?P<value>{NUMBER_RE})\s*mm\b", text)
        if pcd:
            value = convert_measurement("bolt_circle_mm", pcd.group("value"), "mm")
            if value is not None:
                found.append(Measurement(
                    "bolt_circle_mm", value, pcd.group("value"), "mm",
                    "PCD drawing callout", "pdf.drawing",
                ))
        holes = re.search(
            rf"(?im)^\s*Bolt\s+Circle\s+Diameter\s+"
            rf"(?P<count>\d{{1,2}})\s*[x×]\s*Ø\s*\(?(?P<dims>{NUMBER_RE}(?:\s*[x×]\s*{NUMBER_RE})?)\)?\s*mm",
            body,
        )
        if holes:
            found.append(Measurement(
                "mounting_hole_count", float(holes.group("count")),
                holes.group("count"), "", "Mounting hole count", "pdf.table",
            ))
            dims = holes.group("dims")
            if not re.search(r"[x×]", dims, re.I):
                value = convert_measurement("mounting_hole_diameter_mm", dims, "mm")
                if value is not None:
                    found.append(Measurement(
                        "mounting_hole_diameter_mm", value, dims, "mm",
                        "Mounting hole drawing diameter", "pdf.table",
                    ))
    return found


def choose_measurements(items: Iterable[Measurement]) -> dict[str, Measurement]:
    priority = {
        "html.variant_table": 5,
        "jsonld.additionalProperty": 4,
        "pdf.drawing": 3,
        "jsonld.field": 3,
        "html.table": 2,
        "pdf.table": 2,
        "html.text": 1,
        "pdf.text": 1,
    }
    unitless_keys = {"qts", "qms", "qes", "mounting_hole_count"}

    def quality(item: Measurement) -> tuple[int, ...]:
        explicit_unit = int(bool(normalize_unit(item.unit))) if item.key not in unitless_keys else 0
        if item.key == "pe_w":
            label = normalized_label(item.label)
            if re.search(r"\b(?:continuous|program|maximum|peak)\b", label):
                thermal_rank = 0
            elif (
                label in {
                    "pe", "pwr", "pmax", "power handling", "power rating",
                    "watts", "potencia",
                }
                or item.label.casefold().startswith(("potência", "potencia", "power handling"))
                or re.search(r"\b(?:nominal|aes|rms|rated)\b", label)
            ):
                thermal_rank = 2
            else:
                thermal_rank = 1
            return explicit_unit, thermal_rank, priority.get(item.method, 0)
        if item.key not in unitless_keys:
            return explicit_unit, 0, priority.get(item.method, 0)
        return priority.get(item.method, 0), explicit_unit, 0

    chosen: dict[str, Measurement] = {}
    for item in items:
        current = chosen.get(item.key)
        if current is None or quality(item) > quality(current):
            chosen[item.key] = item
    return chosen


def sb_acoustics_drawing_measurements(
    tokens: list[tuple[float, float, float, float, str]], signature: str,
) -> list[Measurement]:
    """Decode explicit dimension callouts in SB Acoustics drawing templates.

    The tuple is ``(x, y, text_matrix_a, text_matrix_b, text)``. This does not
    infer dimensions from nominal size: it associates printed drawing callouts
    by rotation, position and the manufacturer's repeated drafting layout.
    """
    if not re.search(r"\b(?:SB|SW|MW|MR|WO)\d{2}[A-Z0-9-]*", signature, re.I):
        return []

    def numeric(raw: str) -> float | None:
        match = re.search(NUMBER_RE, raw.replace("Ø", ""))
        return parse_number(match.group(0)) if match else None

    def measurement(key: str, value: float, raw: str, label: str) -> Measurement:
        return Measurement(key, value, raw, "mm", label, "pdf.drawing")

    drawing = [token for token in tokens if token[1] > 560.0]
    rotated = [
        (numeric(raw), raw) for _x, _y, a, b, raw in drawing
        if abs(a) < 0.2 and abs(abs(b) - 1.0) < 0.2 and numeric(raw) is not None
    ]
    rotated_values = sorted(
        [(float(value), raw) for value, raw in rotated if 20.0 <= float(value) <= 1000.0],
        reverse=True,
    )
    found: list[Measurement] = []
    if len(rotated_values) >= 2:
        overall_value, overall_raw = rotated_values[0]
        cutout_value, cutout_raw = rotated_values[1]
        # Circular frames explicitly print the diameter glyph on the largest
        # rotated side-view callout. Rectangular/coax frames do not fit the
        # catalog's overall-diameter field and are deliberately left blank.
        if "Ø" in overall_raw:
            found.append(measurement(
                "overall_diameter_mm", overall_value, overall_raw,
                "SB drawing overall diameter",
            ))
        found.append(measurement(
            "cutout_diameter_mm", cutout_value, cutout_raw,
            "SB drawing baffle cutout diameter",
        ))

    pcd_candidates: list[tuple[float, str]] = []
    hole_candidates: list[tuple[float, int, str]] = []
    for _x, y, a, b, raw in drawing:
        value = numeric(raw)
        if value is None or abs(a - 1.0) >= 0.2 or abs(b) >= 0.2:
            continue
        count_match = re.search(r"\(\s*x\s*(\d+)\s*\)", raw, re.I)
        if count_match and "Ø" in raw:
            hole_candidates.append((float(value), int(count_match.group(1)), raw))
        elif "Ø" in raw and y > 690.0 and value >= 20.0:
            pcd_candidates.append((float(value), raw))
    if pcd_candidates:
        value, raw = max(pcd_candidates)
        found.append(measurement("bolt_circle_mm", value, raw, "SB drawing bolt circle"))
    if hole_candidates:
        value, count, raw = min(hole_candidates)
        found.extend([
            measurement(
                "mounting_hole_diameter_mm", value, raw,
                "SB drawing through mounting hole diameter",
            ),
            Measurement(
                "mounting_hole_count", float(count), str(count), "",
                "SB drawing mounting hole count", "pdf.drawing",
            ),
        ])

    # The paired horizontal callouts at the upper/right side view are overall
    # and rear-of-baffle depth. Require a close pair to exclude flange
    # thickness and other isolated dimensions elsewhere on the drawing.
    depth_tokens: list[tuple[float, float, str]] = []
    for x, y, a, b, raw in drawing:
        value = numeric(raw)
        if (
            value is not None and 450.0 <= x <= 520.0
            and abs(a - 1.0) < 0.2 and abs(b) < 0.2
            and "Ø" not in raw and "x" not in raw.casefold()
            and 20.0 <= value <= 1000.0
        ):
            depth_tokens.append((y, float(value), raw))
    pairs = [
        (left, right) for index, left in enumerate(depth_tokens)
        for right in depth_tokens[index + 1:] if abs(left[0] - right[0]) <= 15.0
    ]
    if pairs:
        pair = max(pairs, key=lambda items: max(items[0][0], items[1][0]))
        values = sorted((pair[0][1], pair[1][1]), reverse=True)
        found.extend([
            measurement("depth_mm", values[0], str(values[0]), "SB drawing overall depth"),
            measurement(
                "mounting_depth_mm", values[1], str(values[1]),
                "SB drawing rear-of-baffle mounting depth",
            ),
        ])
    return found


def bomber_drawing_measurements(text: str) -> list[Measurement]:
    """Decode Bomber's explicitly keyed A--F loudspeaker drawing.

    Bomber publishes A/B as the two axial extents measured to opposite flange
    faces.  Which letter is larger depends on the frame, so the larger printed
    extent is overall depth and the smaller is rear-of-baffle mounting depth.
    C and D are respectively the frame and baffle-cutout diameters.  E/F are
    magnet dimensions and intentionally do not enter the mechanical schema.
    """
    if not re.search(r"(?i)www\.bomber\.com\.br", text):
        return []
    heading = re.search(r"(?i)speaker\s+dimensions\s*\(\s*mm\s*\)", text)
    if not heading:
        return []
    block = text[heading.end():heading.end() + 1400]
    keyed = re.search(
        rf"(?s)\bA\s+(?P<a>{NUMBER_RE})\s+\bB\s+(?P<b>{NUMBER_RE})"
        rf".{{0,350}}?\bC\s+(?P<c>{NUMBER_RE})\s+\bD\s+(?P<d>{NUMBER_RE})"
        rf".{{0,350}}?\bE\s+(?P<e>{NUMBER_RE})\s+\bF\s+(?P<f>{NUMBER_RE})",
        block,
    )
    if not keyed:
        return []
    values = {name: parse_number(keyed.group(name)) for name in "abcdef"}
    if any(value is None for value in values.values()):
        return []
    a, b = float(values["a"]), float(values["b"])
    c, d = float(values["c"]), float(values["d"])
    if not (20.0 <= min(a, b) <= max(a, b) <= 1000.0 and 20.0 <= d < c <= 1000.0):
        return []
    raw_depths = f"A={keyed.group('a')}; B={keyed.group('b')}"
    return [
        Measurement(
            "overall_diameter_mm", c, keyed.group("c"), "mm",
            "Bomber drawing dimension C (overall diameter)", "pdf.drawing",
        ),
        Measurement(
            "cutout_diameter_mm", d, keyed.group("d"), "mm",
            "Bomber drawing dimension D (baffle cutout)", "pdf.drawing",
        ),
        Measurement(
            "depth_mm", max(a, b), raw_depths, "mm",
            "Bomber drawing A/B overall axial extent", "pdf.drawing",
        ),
        Measurement(
            "mounting_depth_mm", min(a, b), raw_depths, "mm",
            "Bomber drawing A/B rear-of-baffle extent", "pdf.drawing",
        ),
    ]


def bc_speakers_drawing_measurements(text: str, metadata_signature: str) -> list[Measurement]:
    """Read explicit mounting-hole callouts from official B&C CAD drawings."""
    if not re.search(r"(?i)BCSPEAKERS|official B&C drawing URL", metadata_signature):
        return []
    hole_patterns = (
        # Ø5 (4x), 6.20(x8), 6.4 (8x)
        rf"(?im)(?<![\d.,])[Ø⌀φ]?\s*(?P<diameter>{NUMBER_RE})\s*"
        r"\(\s*(?:x\s*)?(?P<count>\d{1,2})\s*x?\s*\)",
        # 8x Ø6.5, 8x 7 min, N.8 x 7 min
        rf"(?im)(?<![\d.,])(?:N\.?\s*)?(?P<count>\d{{1,2}})\s*x\s*"
        rf"[Ø⌀φ]?\s*(?P<diameter>{NUMBER_RE})(?:\s*min\.?)?",
        # (x8) 7 min, (8x) 6.50
        rf"(?im)(?<![\d.,])\(\s*(?:x\s*)?(?P<count>\d{{1,2}})\s*x?\s*\)\s*"
        rf"[Ø⌀φ]?\s*(?P<diameter>{NUMBER_RE})(?:\s*min\.?)?",
    )
    holes = None
    diameter = count = None
    for pattern in hole_patterns:
        for candidate in re.finditer(pattern, text):
            candidate_diameter = parse_number(candidate.group("diameter"))
            candidate_count = parse_number(candidate.group("count"))
            if (
                candidate_diameter is not None and candidate_count is not None
                and 1.0 <= candidate_diameter <= 50.0
                and 1 <= candidate_count <= 32
            ):
                holes = candidate
                diameter, count = candidate_diameter, candidate_count
                break
        if holes:
            break
    if holes is None or diameter is None or count is None:
        return []
    found = [
        Measurement(
            "mounting_hole_diameter_mm", diameter, holes.group("diameter"), "mm",
            "B&C drawing through-hole diameter", "pdf.drawing",
        ),
        Measurement(
            "mounting_hole_count", count, holes.group("count"), "",
            "B&C drawing repeated-hole count", "pdf.drawing",
        ),
    ]
    bolt_circle = re.search(
        rf"(?im)^\s*(?:B\.?\s*C\.?|BCD)\s*[Ø⌀φ]?\s*"
        rf"(?P<value>{NUMBER_RE})\s*$",
        text,
    )
    if bolt_circle:
        value = parse_number(bolt_circle.group("value"))
        if value is not None and 20.0 <= value <= 1000.0:
            found.append(Measurement(
                "bolt_circle_mm", value, bolt_circle.group("value"), "mm",
                "B&C drawing bolt circle", "pdf.drawing",
            ))
    return found


def sanitize_published_measurements(
    chosen: dict[str, Measurement],
) -> dict[str, Measurement]:
    """Drop internally contradictory layout observations, never estimate them."""
    result = dict(chosen)
    overall = result.get("overall_diameter_mm")
    for key in ("cutout_diameter_mm", "bolt_circle_mm"):
        item = result.get(key)
        if overall and item and item.value > overall.value * 1.02:
            result.pop(key, None)
    holes = result.get("mounting_hole_count")
    if holes and not float(holes.value).is_integer():
        result.pop("mounting_hole_count", None)
    return result


def derive_driver_values(values: dict[str, float]) -> dict[str, float]:
    out = dict(values)
    if out.get("xmax_mm") is None and out.get("linear_travel_pp_mm"):
        out["xmax_mm"] = out["linear_travel_pp_mm"] / 2.0
    qts, qms, qes = out.get("qts"), out.get("qms"), out.get("qes")
    if qts is None and qms and qes:
        out["qts"] = qms * qes / (qms + qes)
        qts = out["qts"]
    if qms is None and qts and qes and qes > qts:
        out["qms"] = 1.0 / (1.0 / qts - 1.0 / qes)
    if qes is None and qts and qms and qms > qts:
        out["qes"] = 1.0 / (1.0 / qts - 1.0 / qms)
    if out.get("qms") is None and all(out.get(key) for key in ("fs_hz", "mms_g", "rms_kg_s")):
        out["qms"] = (
            2.0 * math.pi * out["fs_hz"] * (out["mms_g"] / 1000.0)
            / out["rms_kg_s"]
        )
    if out.get("vas_l") is None and out.get("cms_mm_per_n") and out.get("sd_cm2"):
        cms_m_per_n = out["cms_mm_per_n"] / 1000.0
        sd_m2 = out["sd_cm2"] / 10_000.0
        out["vas_l"] = cms_m_per_n * RHO_AIR * SPEED_OF_SOUND**2 * sd_m2**2 * 1000.0
    if out.get("sd_cm2") is None and out.get("effective_radius_mm"):
        radius_cm = out["effective_radius_mm"] / 10.0
        out["sd_cm2"] = math.pi * radius_cm**2
    if out.get("sd_cm2") is None and out.get("effective_diameter_mm"):
        radius_cm = out["effective_diameter_mm"] / 20.0
        out["sd_cm2"] = math.pi * radius_cm**2
    if out.get("sd_cm2") is None and out.get("vd_l") and out.get("xmax_mm"):
        out["sd_cm2"] = out["vd_l"] * 10_000.0 / out["xmax_mm"]
    if out.get("sd_cm2") is None and out.get("vas_l") and out.get("cms_mm_per_n"):
        vas_m3 = out["vas_l"] / 1000.0
        cms_m_per_n = out["cms_mm_per_n"] / 1000.0
        sd_m2 = math.sqrt(vas_m3 / (cms_m_per_n * RHO_AIR * SPEED_OF_SOUND**2))
        out["sd_cm2"] = sd_m2 * 10_000.0
    if out.get("re_ohm") is None and all(
        out.get(key) for key in ("qes", "bl_tm", "fs_hz", "mms_g")
    ):
        mms_kg = out["mms_g"] / 1000.0
        out["re_ohm"] = (
            out["qes"] * out["bl_tm"] ** 2
            / (2.0 * math.pi * out["fs_hz"] * mms_kg)
        )
    return out


def validate_driver(values: dict[str, float]) -> list[str]:
    errors = [f"missing {key}" for key in REQUIRED_DRIVER_FIELDS if values.get(key) is None]
    if errors:
        return errors
    if values["qms"] <= values["qts"]:
        errors.append("Qms must be greater than Qts")
    for key in REQUIRED_DRIVER_FIELDS:
        low, high = RANGES[key]
        if not low <= values[key] <= high:
            errors.append(f"{key} outside physical range")
    return errors


def flatten_jsonld(nodes: list[object]) -> list[dict]:
    return [node for root in nodes for node in walk_json(root)]


def product_metadata(page: PageData, url: str, brand_hint: str = "") -> tuple[str, str, str]:
    product: dict = {}
    for node in flatten_jsonld(page.jsonld):
        raw_type = node.get("@type", "")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(str(item).casefold() == "product" for item in types):
            product = node
            break
    
    # 18 Sound sets generic title, use h1 if available
    name_candidates = [
        product.get("name"),
        page.h1,
        page.title,
        page.meta.get("og:title")
    ]
    name = next(
        (html.unescape(str(n)).strip() for n in name_candidates if n and str(n).strip()),
        "",
    )
    
    raw_brand = product.get("brand", "")
    if isinstance(raw_brand, dict):
        raw_brand = raw_brand.get("name", "")
    # A caller-supplied brand hint means "I already know which manufacturer's
    # site this is" (every crawl invocation targets one brand). Trust it over
    # page-declared brand data, which is sometimes wrong at the source (e.g.
    # DS18's Shopify theme puts the product's own SKU in JSON-LD brand.name
    # instead of "DS18").
    brand = html.unescape(
        str(brand_hint or raw_brand or page.meta.get("product:brand") or "")
    ).strip()
    model = str(
        product.get("model") or product.get("mpn") or product.get("sku")
        or page.meta.get("product:retailer_item_id") or ""
    ).strip()
    model = html.unescape(model)
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host == "stereointegrity.com" and re.fullmatch(r"\d{2,}", model):
        model = name
        if brand and model.casefold().startswith(brand.casefold()):
            model = model[len(brand):].strip(" -–—|")
    if not model:
        # Some storefronts expose their stable manufacturer identity only as
        # visible specification rows, e.g. MISCO's ``Model #`` followed by
        # ``305-WF08-01``. Prefer that over a descriptive product title.
        labelled_model = re.search(
            r"(?im)^\s*model(?:\s*(?:number|no\.?))?\s*#?\s*:?\s*"
            r"(?:\n\s*)?(?P<model>[A-Z0-9][A-Z0-9._/+ -]{1,79})\s*$",
            page.text,
        )
        if labelled_model:
            model = labelled_model.group("model").strip()
    if re.search(r"(?:spec(?:ification)?[_ -]?sheet|datasheet)", model, re.I):
        url_model = Path(urlparse(url).path).stem
        model = re.sub(
            r"(?:[_ -]?(?:spec(?:ification)?[_ -]?sheet|datasheet).*)$",
            "",
            url_model,
            flags=re.I,
        ).strip(" _-") or model
    if not model:
        model = name
        if brand and model.casefold().startswith(brand.casefold()):
            model = model[len(brand):].strip(" -–—|")
    if model.casefold() in {"discontinued product", "product", "speaker unit"}:
        url_model = Path(urlparse(url).path).stem
        url_model = re.sub(r"^\d+-", "", url_model).strip(" _-")
        if url_model:
            model = url_model.upper()
    if re.search(r"(?:spec(?:ification)?[_ -]?sheet|datasheet)", model, re.I):
        url_model = Path(urlparse(url).path).stem
        model = re.sub(
            r"(?:[_ -]?(?:spec(?:ification)?[_ -]?sheet|datasheet).*)$",
            "",
            url_model,
            flags=re.I,
        ).strip(" _-") or model
    if brand:
        model = re.sub(
            rf"\s*[-|–—]\s*{re.escape(brand)}\s*$",
            "",
            model,
            flags=re.I,
        ).strip()
        model = re.sub(
            r"\s*[-|–—]\s*(?:LF Drivers|High Frequency Drivers|Coaxials|Subwoofers)\s*$",
            "",
            model,
            flags=re.I,
        ).strip()
        model = re.sub(
            r"^(?:FaitalPRO\s*\|\s*)?(?:LF Loudspeakers|High Frequency Drivers|Coaxial Loudspeakers|Subwoofers)\s*\|\s*",
            "",
            model,
            flags=re.I,
        ).strip()
    if not brand:
        brand = urlparse(url).hostname.removeprefix("www.") if urlparse(url).hostname else "Unknown"
    if not model:
        model = Path(urlparse(url).path).stem or "Unknown"
    model = re.sub(
        r"(?:[_ -]?(?:spec(?:ification)?[_ -]?sheet|datasheet).*)$",
        "",
        model,
        flags=re.I,
    ).strip(" _-") or model
    model = re.sub(r"\.xlsx?$", "", model, flags=re.I).strip() or model
    return name or f"{brand} {model}".strip(), brand, model


def is_standalone_lf_driver_model(model: str, title: str = "") -> bool:
    """Reject obvious assemblies and tweeters from the LF driver catalog."""
    identity = f"{model} {title}".strip()
    return not re.search(r"\b(?:kit|tweeter)\b", identity, re.I)


def first_inch_size(value: object) -> float | None:
    """Return the first complete inch dimension, including mixed fractions."""
    text = (
        str(value or "")
        .replace("¼", " 1/4")
        .replace("½", " 1/2")
        .replace("¾", " 3/4")
    )
    compound = re.search(
        r"(?<![\d.])(?P<first>\d+(?:[.,]\d+)?)\s*[x×]\s*"
        r"\d+(?:[.,]\d+)?\s*(?:inch(?:es)?|in\.?|[\"″])",
        text,
        re.I,
    )
    if compound:
        size = float(compound.group("first").replace(",", "."))
        return round(size, 3) if 0.5 <= size <= 32.0 else None
    match = INCH_SIZE_RE.search(text)
    if not match:
        return None
    size = float(match.group("whole").replace(",", "."))
    if match.group("numerator") and match.group("denominator"):
        denominator = float(match.group("denominator"))
        if denominator:
            size += float(match.group("numerator")) / denominator
    return round(size, 3) if 0.5 <= size <= 32.0 else None


def _size_matches_sd(size_in: float, sd_cm2: float | None) -> bool:
    """Reject model-number guesses that cannot be the frame diameter."""
    if not sd_cm2 or sd_cm2 <= 0.0:
        return True
    effective_diameter_in = math.sqrt(4.0 * sd_cm2 / math.pi) / 2.54
    # The effective piston must remain smaller than, but reasonably close to,
    # the nominal frame. This rejects size-like model numbers and bad catalog
    # labels before they become filter metadata.
    return 0.70 <= effective_diameter_in / size_in <= 1.15


def infer_size_in(
    name: str,
    text: str = "",
    sd_cm2: float | None = None,
) -> float | None:
    labelled = re.search(
        r"\b(?:nominal\s+(?:diameter|size)|effective\s+diameter)\b[^\n]{0,60}",
        text,
        re.I,
    )
    if labelled:
        size = first_inch_size(labelled.group(0))
        if size is not None:
            return size
    # Titles are product-specific; arbitrary body text may start with sizes
    # from navigation menus or related products and must not be trusted.
    title_size = first_inch_size(name)
    if title_size is not None:
        return title_size
    model_prefix = re.match(r"^(?:[A-Za-z][A-Za-z .&+-]*\s*)?(\d{1,2})(?=[A-Za-z])", name)
    if model_prefix and 2 <= int(model_prefix.group(1)) <= 32:
        size = float(model_prefix.group(1))
        if _size_matches_sd(size, sd_cm2):
            return size
    described = re.search(
        r"\b[^\n]{0,16}(?:inch(?:es)?|in\.?|[\"″])\s+"
        r"(?:loudspeaker\s+)?(?:driver|woofer|subwoofer|midbass|full[- ]?range)\b",
        text,
        re.I,
    )
    if described:
        size = first_inch_size(described.group(0))
        if size is not None and _size_matches_sd(size, sd_cm2):
            return size
    return None


def eighteensound_variant_model(
    model: str,
    url: str,
    published_specs: dict[str, float],
) -> str:
    """Keep official Eighteen Sound impedance variants as distinct products."""
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host not in {"eighteensound.com", "eighteensound.it"}:
        return model
    impedance = published_specs.get("nominal_impedance_ohm")
    if not impedance or impedance <= 0.0:
        return model
    undecorated = re.sub(
        r"\s+\d+(?:[.,]\d+)?\s*(?:oh(?:ms?)?|Ω)\s*$",
        "",
        model,
        flags=re.I,
    ).strip()
    return f"{undecorated} {float(impedance):g}Ω"


def build_preset(
    page: PageData,
    url: str,
    source_name: str = "Web crawler",
    brand_hint: str = "",
    extraction_method: str = "html",
) -> tuple[dict | None, list[str]]:
    measurements = jsonld_measurements(page.jsonld)
    text_items = text_measurements(page.text)
    table_items = table_measurements(
        page.text,
        "pdf.table" if extraction_method == "pdf" else "html.table",
    )
    if extraction_method == "pdf":
        text_items = [Measurement(
            item.key, item.value, item.raw_value, item.unit, item.label, "pdf.text"
        ) for item in text_items]
    chosen = sanitize_published_measurements(
        choose_measurements([*measurements, *page.embedded_measurements, *table_items, *text_items])
    )
    values = derive_driver_values({key: item.value for key, item in chosen.items()})
    derived_fields = sorted(
        key for key in (*REQUIRED_DRIVER_FIELDS, *OPTIONAL_DRIVER_FIELDS)
        if key not in chosen and values.get(key) is not None
    )
    errors = validate_driver(values)
    if errors:
        return None, errors

    name, brand, model = product_metadata(page, url, brand_hint)
    if not is_standalone_lf_driver_model(model, name):
        return None, ["not a standalone low-frequency driver"]
    direct_required = sum(1 for key in REQUIRED_DRIVER_FIELDS if key in chosen)
    optional_count = sum(1 for key in OPTIONAL_DRIVER_FIELDS if values.get(key) is not None)
    confidence = min(1.0, 0.55 + 0.05 * direct_required + 0.025 * optional_count)
    driver = {
        key: round(float(values.get(key, 0.0) or 0.0), 8)
        for key in (*REQUIRED_DRIVER_FIELDS, *OPTIONAL_DRIVER_FIELDS)
    }
    fetched_at = utc_now()
    raw_measurements = {
        key: {
            "value": item.value,
            "raw_value": item.raw_value,
            "unit": item.unit,
            "label": item.label,
            "method": item.method,
            "source_url": url,
            "fetched_at": fetched_at,
        }
        for key, item in chosen.items()
    }
    mechanical = {
        key: (int(chosen[key].value) if key == "mounting_hole_count" else chosen[key].value)
        for key in MECHANICAL_FIELDS if key in chosen
    }
    published_specs = {
        key: chosen[key].value for key in PUBLISHED_SPEC_FIELDS if key in chosen
    }
    model = eighteensound_variant_model(model, url, published_specs)
    derivations = {}
    if "xmax_mm" in derived_fields and "linear_travel_pp_mm" in chosen:
        derivations["xmax_mm"] = {
            "formula": "linear_travel_pp_mm / 2",
            "source_fields": ["linear_travel_pp_mm"],
            "confidence": "high",
        }
    preset = {
        "name": f"WEB: {brand} {model}".strip(),
        "brand": brand,
        "model": model,
        "size_in": infer_size_in(name, page.text, driver.get("sd_cm2")),
        "kind": "Loudspeaker driver",
        "url": url,
        "source": source_name,
        "driver": driver,
        "raw": {key: item.value for key, item in chosen.items()},
        "website_fields": {
            "title": name,
            "brand": brand,
            "model": model,
            "url": url,
            "source": source_name,
            "fetched_at": fetched_at,
            "extraction_method": extraction_method,
            "confidence": round(confidence, 3),
            "raw_measurements": raw_measurements,
            "derived_fields": derived_fields,
            "derivations": derivations,
        },
    }
    if mechanical:
        preset["mechanical"] = mechanical
    if published_specs:
        preset["published_specs"] = published_specs
    return preset, []


class _StructuredTableParser(HTMLParser):
    """Retain direct HTML table cells and colspans for variant matrices."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, object]]]] = []
        self._stack: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None})
            return
        if not self._stack:
            return
        table = self._stack[-1]
        if tag == "tr":
            table["row"] = []
        elif tag in {"td", "th"} and table["row"] is not None:
            values = {key.casefold(): value or "" for key, value in attrs}
            try:
                colspan = max(1, int(values.get("colspan", "1")))
            except ValueError:
                colspan = 1
            cell: dict[str, object] = {"parts": [], "colspan": colspan}
            row = table["row"]
            assert isinstance(row, list)
            row.append(cell)
            table["cell"] = cell

    def handle_data(self, data: str):
        if not self._stack:
            return
        cell = self._stack[-1].get("cell")
        if isinstance(cell, dict) and data.strip():
            parts = cell["parts"]
            assert isinstance(parts, list)
            parts.append(data.strip())

    def handle_endtag(self, tag: str):
        if not self._stack:
            return
        table = self._stack[-1]
        if tag in {"td", "th"}:
            table["cell"] = None
        elif tag == "tr":
            row = table.get("row")
            rows = table["rows"]
            assert isinstance(rows, list)
            if isinstance(row, list) and row:
                rows.append(row)
            table["row"] = None
        elif tag == "table":
            finished = self._stack.pop()["rows"]
            assert isinstance(finished, list)
            if finished:
                self.tables.append(finished)


def _expanded_table_row(row: list[dict[str, object]]) -> list[str]:
    expanded: list[str] = []
    for cell in row:
        parts = cell.get("parts") or []
        text = " ".join(str(part) for part in parts if str(part).strip())
        text = " ".join(html.unescape(text).replace("\u00a0", " ").split())
        expanded.extend([text] * int(cell.get("colspan") or 1))
    return expanded


_WAVECOR_MODEL_GROUP = re.compile(
    r"\b(?:FR|MR|SW|WF)[A-Z0-9]+(?:\s*(?:[/&]|and)\s*[A-Z0-9]+)+\b",
    re.I,
)


def _wavecor_models(group: str) -> list[str]:
    """Expand Wavecor shorthand such as ``MR120BD01/03`` into MPNs."""
    compact = re.sub(r"\s+", "", group).upper()
    parts = re.split(r"[/&]|(?i:AND)", compact)
    first = parts[0]
    models = [first]
    for suffix in parts[1:]:
        if re.fullmatch(r"\d{1,3}", suffix) and len(first) > len(suffix):
            models.append(first[:-len(suffix)] + suffix)
        elif suffix:
            models.append(suffix)
    return list(dict.fromkeys(models))


def _variant_parameter(label: str) -> str | None:
    if re.search(r"\b10\s*k\s*hz\b", label, re.I) and re.search(
        r"\b(?:le|inductance)\b", label, re.I
    ):
        return "le10k_mh"
    key = canonical_parameter(label)
    if key:
        return key
    for token in reversed(re.findall(r"[A-Za-z][A-Za-z0-9]*", label)):
        if key := canonical_parameter(token):
            return key
    return None


def wavecor_variant_presets(
    content: bytes,
    page: PageData,
    url: str,
    source_name: str,
    brand_hint: str,
) -> list[dict]:
    """Split official Wavecor before/after-burn-in matrices by model group."""
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host != "wavecor.com":
        return []
    parser = _StructuredTableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    presets: list[dict] = []
    seen_models: set[str] = set()
    for table in parser.tables:
        rows = [_expanded_table_row(row) for row in table]
        header_index = next((
            index for index, row in enumerate(rows)
            if any(_WAVECOR_MODEL_GROUP.search(cell) for cell in row)
            and any(normalized_label(cell) == "parameter" for cell in row)
            and any(normalized_label(cell) == "unit" for cell in row)
        ), None)
        if header_index is None:
            continue
        header = rows[header_index]
        unit_column = next(
            index for index, cell in enumerate(header)
            if normalized_label(cell) == "unit"
        )
        groups: dict[str, list[int]] = {}
        for column, cell in enumerate(header):
            match = _WAVECOR_MODEL_GROUP.search(cell)
            if match:
                group = re.sub(r"\s+", "", match.group(0)).upper()
                groups.setdefault(group, []).append(column)
        for group, columns in groups.items():
            # Wavecor publishes before/after burn-in in adjacent columns. The
            # after-burn-in value is the stable design value; colspan rows
            # naturally repeat the same value in both slots.
            value_column = max(columns)
            measurements: list[Measurement] = []
            for row in rows[header_index + 1:]:
                if len(row) <= max(unit_column, value_column) or len(row) < 2:
                    continue
                label = row[1]
                key = _variant_parameter(label)
                if not key:
                    continue
                label_key = normalized_label(label)
                if key == "pe_w" and any(
                    phrase in label_key for phrase in ("short term", "long term")
                ):
                    continue
                raw = re.sub(r"^\s*\+?\s*/\s*[-−]\s*", "", row[value_column])
                unit = row[unit_column].strip(" []()")
                value = convert_measurement(key, raw, unit)
                if value is not None:
                    measurements.append(Measurement(
                        key, value, raw, unit, label, "html.variant_table"
                    ))
            for model in _wavecor_models(group):
                if model in seen_models:
                    continue
                variant_page = PageData(
                    title=model,
                    h1=model,
                    embedded_measurements=measurements,
                )
                preset, errors = build_preset(
                    variant_page,
                    url,
                    source_name,
                    brand_hint or "Wavecor",
                    extraction_method="html",
                )
                if errors or preset is None:
                    continue
                preset["size_in"] = infer_size_in(
                    page.title or model, page.text, preset["driver"].get("sd_cm2")
                )
                preset["website_fields"]["title"] = page.title or page.h1 or model
                preset["website_fields"]["variant_group"] = group
                presets.append(preset)
                seen_models.add(model)
    return presets


def build_published_observation(
    page: PageData,
    url: str,
    source_name: str = "Web crawler",
    brand_hint: str = "",
    extraction_method: str = "html",
) -> dict | None:
    """Build a source-backed partial observation without inventing fields.

    Unlike ``build_preset``, this does not require a complete simulation-ready
    T/S set and may therefore enrich an already identified catalog record with
    physical or future-facing published specifications. It must not be used to
    create a standalone driver row.
    """
    measurements = jsonld_measurements(page.jsonld)
    text_items = text_measurements(page.text)
    table_items = table_measurements(
        page.text, "pdf.table" if extraction_method == "pdf" else "html.table"
    )
    if extraction_method == "pdf":
        text_items = [Measurement(
            item.key, item.value, item.raw_value, item.unit, item.label, "pdf.text"
        ) for item in text_items]
    chosen = sanitize_published_measurements(
        choose_measurements([*measurements, *page.embedded_measurements, *table_items, *text_items])
    )
    if not chosen:
        return None
    name, brand, model = product_metadata(page, url, brand_hint)
    fetched_at = utc_now()
    driver = {
        key: round(float(chosen[key].value), 8)
        for key in (*REQUIRED_DRIVER_FIELDS, *OPTIONAL_DRIVER_FIELDS) if key in chosen
    }
    mechanical = {
        key: (int(chosen[key].value) if key == "mounting_hole_count" else chosen[key].value)
        for key in MECHANICAL_FIELDS if key in chosen
    }
    published_specs = {
        key: chosen[key].value for key in PUBLISHED_SPEC_FIELDS if key in chosen
    }
    raw_measurements = {
        key: {
            "value": item.value, "raw_value": item.raw_value, "unit": item.unit,
            "label": item.label, "method": item.method, "source_url": url,
            "fetched_at": fetched_at,
        }
        for key, item in chosen.items()
    }
    observation = {
        "name": f"OBS: {brand} {model}".strip(),
        "brand": brand,
        "model": model,
        "kind": "Loudspeaker driver observation",
        "url": url,
        "source": source_name,
        "driver": driver,
        "website_fields": {
            "title": name, "brand": brand, "model": model, "url": url,
            "source": source_name, "fetched_at": fetched_at,
            "extraction_method": extraction_method,
            "raw_measurements": raw_measurements,
            "partial_observation": True,
        },
    }
    if mechanical:
        observation["mechanical"] = mechanical
    if published_specs:
        observation["published_specs"] = published_specs
    return observation


def parse_html(content: bytes) -> PageData:
    parser = DocumentParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    return parser.page()


def parse_pdf(content: bytes) -> PageData:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF found but pypdf is not installed") from exc
    reader = PdfReader(io.BytesIO(content))
    # Layout mode keeps table labels and values on one line, which is required
    # for column-formatted datasheets (e.g. SB Acoustics) whose plain reading
    # order lists every label before every value. It goes first so its correct
    # pairings win; mispaired plain-order matches fail unit conversion anyway.
    tokens: list[tuple[float, float, float, float, str]] = []
    try:
        layout_pages = []
        for page in reader.pages:
            layout_pages.append(page.extract_text(extraction_mode="layout") or "")

            def visitor(text, _cm, tm, _font, _size):
                stripped = str(text or "").strip()
                if stripped:
                    tokens.append((float(tm[4]), float(tm[5]), float(tm[0]), float(tm[1]), stripped))

            page.extract_text(visitor_text=visitor)
        layout = "\n".join(layout_pages)
    except Exception:
        layout = ""
    plain = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = f"{layout}\n{plain}" if layout else plain
    metadata = reader.metadata or {}
    title = str(metadata.get("/Title") or "")
    metadata_signature = "\n".join(str(value) for value in metadata.values())
    return PageData(
        title=title,
        text=text,
        embedded_measurements=[
            *sb_acoustics_drawing_measurements(tokens, f"{title}\n{layout[:500]}"),
            *bomber_drawing_measurements(text),
            *bc_speakers_drawing_measurements(text, metadata_signature),
        ],
    )


def normalize_url(url: str, base: str = "") -> str | None:
    absolute = urljoin(base, url.strip())
    absolute, _fragment = urldefrag(absolute)
    # Percent-encode characters (such as spaces) that http.client rejects;
    # keep existing escapes intact instead of double-encoding them.
    absolute = quote(absolute, safe=":/?#[]@!$&'()*+,;=%")
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return absolute


def parse_sitemap(content: bytes) -> tuple[list[str], list[str]]:
    root = ET.fromstring(content)
    tag = root.tag.rsplit("}", 1)[-1].casefold()
    locations = [
        (node.text or "").strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].casefold() == "loc" and (node.text or "").strip()
    ]
    return (locations, []) if tag == "urlset" else ([], locations)


def fetch_resource(url: str, timeout_s: float, user_agent: str) -> FetchResult:
    request = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.5",
    })
    try:
        with urlopen(request, timeout=timeout_s, context=SSL_CONTEXT) as response:
            return FetchResult(
                url=response.geturl(),
                content_type=response.headers.get_content_type(),
                content=response.read(),
            )
    except URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise
        # macOS curl uses the system trust store and can validate a few legacy
        # certificate chains that OpenSSL/certifi cannot. Verification remains
        # enabled; this is not an insecure-certificate bypass.
        result = subprocess.run(
            [
                "curl", "--fail", "--silent", "--show-error", "--location",
                "--max-time", str(timeout_s), "--user-agent", user_agent, url,
            ],
            check=True,
            capture_output=True,
        )
        content_type = (
            "application/pdf" if result.stdout.startswith(b"%PDF")
            else "application/xml" if result.stdout.lstrip().startswith(b"<?xml")
            else "text/html"
        )
        return FetchResult(url=url, content_type=content_type, content=result.stdout)


class RobotsPolicy:
    def __init__(self, timeout_s: float, user_agent: str):
        self.timeout_s = timeout_s
        self.user_agent = user_agent
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._parsers:
            robots_url = f"{origin}/robots.txt"
            parser = urllib.robotparser.RobotFileParser(robots_url)
            try:
                request = Request(robots_url, headers={"User-Agent": self.user_agent})
                with urlopen(request, timeout=self.timeout_s, context=SSL_CONTEXT) as response:
                    parser.parse(
                        response.read().decode("utf-8", errors="replace").splitlines())
                self._parsers[origin] = parser
            except (HTTPError, URLError, TimeoutError, OSError):
                self._parsers[origin] = None
        policy = self._parsers[origin]
        return True if policy is None else policy.can_fetch(self.user_agent, url)


def url_allowed(url: str, config: CrawlConfig) -> bool:
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if config.allowed_domains and host not in config.allowed_domains:
        return False
    if config.include_patterns and not any(pattern.search(url) for pattern in config.include_patterns):
        return False
    return not any(pattern.search(url) for pattern in config.exclude_patterns)


def sitemap_urls(
    sitemap_seeds: Iterable[str],
    config: CrawlConfig,
    fetcher: Callable[[str, float, str], FetchResult] = fetch_resource,
) -> list[str]:
    pending = deque(sitemap_seeds)
    visited: set[str] = set()
    product_urls: list[str] = []
    while pending:
        url = pending.popleft()
        if url in visited:
            continue
        visited.add(url)
        result = fetcher(url, config.timeout_s, config.user_agent)
        urls, nested = parse_sitemap(result.content)
        normalized = (normalize_url(item) for item in urls)
        product_urls.extend(
            item for item in normalized
            if item is not None and url_allowed(item, config)
        )
        pending.extend(item for item in nested if item not in visited)
    return product_urls


def checkpoint_payload(queue: deque[tuple[str, int]], visited: set[str], presets: list[dict], failures: list[dict]) -> dict:
    return {
        "updated_at": utc_now(),
        "queue": list(queue),
        "visited": sorted(visited),
        "presets": presets,
        "failures": failures,
    }


def atomic_write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_checkpoint(path: Path) -> tuple[deque[tuple[str, int]], set[str], list[dict], list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queue = deque((str(url), int(depth)) for url, depth in payload.get("queue", []))
    return queue, set(payload.get("visited", [])), list(payload.get("presets", [])), list(payload.get("failures", []))


def crawl(
    config: CrawlConfig,
    fetcher: Callable[[str, float, str], FetchResult] = fetch_resource,
    robots_allowed: Callable[[str], bool] | None = None,
) -> tuple[list[dict], list[dict], set[str]]:
    if config.checkpoint.exists() and not config.fresh:
        queue, visited, presets, failures = load_checkpoint(config.checkpoint)
    else:
        discovered = sitemap_urls(config.sitemaps, config, fetcher) if config.sitemaps else []
        queue = deque((url, 0) for url in [*config.seeds, *discovered])
        visited, presets, failures = set(), [], []
    robots = RobotsPolicy(config.timeout_s, config.user_agent)
    allow = robots_allowed or robots.allowed

    while queue and len(visited) < config.max_pages:
        raw_url, depth = queue.popleft()
        url = normalize_url(raw_url)
        if not url or url in visited or not url_allowed(url, config):
            continue
        if not allow(url):
            failures.append({"url": url, "error": "blocked by robots.txt"})
            visited.add(url)
            continue
        visited.add(url)
        try:
            result = fetcher(url, config.timeout_s, config.user_agent)
            is_pdf = result.content_type == "application/pdf" or result.url.casefold().endswith(".pdf")
            page = parse_pdf(result.content) if is_pdf else parse_html(result.content)
            variants = [] if is_pdf else wavecor_variant_presets(
                result.content, page, result.url, config.source_name,
                config.brand_hint,
            )
            if variants:
                for preset in variants:
                    confidence = float(preset["website_fields"]["confidence"])
                    if confidence >= config.min_confidence:
                        presets.append(preset)
                        log(f"accepted {preset['name']} ({confidence:.2f})")
            else:
                preset, errors = build_preset(
                    page, result.url, config.source_name, config.brand_hint,
                    extraction_method="pdf" if is_pdf else "html",
                )
                if preset:
                    confidence = float(preset["website_fields"]["confidence"])
                    if confidence >= config.min_confidence:
                        presets.append(preset)
                        log(f"accepted {preset['name']} ({confidence:.2f})")
                elif len(errors) < len(REQUIRED_DRIVER_FIELDS):
                    failures.append({"url": result.url, "error": "; ".join(errors)})
            if config.follow_links and not is_pdf and depth < config.max_depth:
                for href in page.links:
                    child = normalize_url(href, result.url)
                    if child and child not in visited and url_allowed(child, config):
                        queue.append((child, depth + 1))
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ET.ParseError) as exc:
            failures.append({"url": url, "error": str(exc)})
        if not config.dry_run:
            atomic_write_json(config.checkpoint, checkpoint_payload(queue, visited, presets, failures))
        if config.sleep_s > 0 and queue:
            time.sleep(config.sleep_s)
    return presets, failures, visited


def preset_key(item: dict) -> tuple[str, str]:
    def clean(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).casefold())
    return clean(item.get("brand")), clean(item.get("model"))


def merge_presets(
    existing: list[dict], discovered: list[dict], overwrite: bool = False,
    refresh_source: str = "",
) -> tuple[list[dict], dict[str, int]]:
    merged = list(existing)
    index = {preset_key(item): pos for pos, item in enumerate(merged)}
    source_urls = {
        str(item.get("url") or ""): pos
        for pos, item in enumerate(merged)
        if refresh_source
        and str(item.get("source") or "").casefold() == refresh_source.casefold()
        and item.get("url")
    }
    stats = {"added": 0, "updated": 0, "unchanged": 0}
    for item in discovered:
        key = preset_key(item)
        if not all(key) or key not in index:
            source_url = str(item.get("url") or "")
            if source_url and source_url in source_urls:
                pos = source_urls[source_url]
                index.pop(preset_key(merged[pos]), None)
                merged[pos] = item
                index[key] = pos
                stats["updated"] += 1
                continue
            if (item.get("website_fields") or {}).get("partial_observation"):
                stats["unchanged"] += 1
                continue
            index[key] = len(merged)
            merged.append(item)
            stats["added"] += 1
            continue
        pos = index[key]
        if overwrite or (
            refresh_source
            and str(merged[pos].get("source") or "").casefold()
            == refresh_source.casefold()
        ):
            merged[pos] = item
            stats["updated"] += 1
            continue
        current = merged[pos]
        changed = False
        driver = dict(current.get("driver") or {})
        for field_name, value in (item.get("driver") or {}).items():
            if driver.get(field_name) in (None, 0, 0.0, "") and value not in (None, 0, 0.0, ""):
                driver[field_name] = value
                changed = True
        for section in ("mechanical", "published_specs"):
            section_values = dict(current.get(section) or {})
            for field_name, value in (item.get(section) or {}).items():
                if section_values.get(field_name) in (None, "") and value not in (None, ""):
                    section_values[field_name] = value
                    changed = True
            if section_values:
                current = dict(current)
                current[section] = section_values
        if changed:
            current = dict(current)
            current["driver"] = driver
            fields = dict(current.get("website_fields") or {})
            sources = list(fields.get("additional_sources") or [])
            source_url = str(item.get("url") or "")
            if source_url and source_url not in sources:
                sources.append(source_url)
            fields["additional_sources"] = sources
            observations = dict(fields.get("published_measurements") or {})
            for key, value in (
                (item.get("website_fields") or {}).get("raw_measurements") or {}
            ).items():
                observations.setdefault(key, value)
            if observations:
                fields["published_measurements"] = observations
            current["website_fields"] = fields
            merged[pos] = current
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
    return merged, stats


def populate_database(config: CrawlConfig, presets: list[dict]) -> dict[str, int]:
    presets = [
        item for item in presets
        if is_standalone_lf_driver_model(
            str(item.get("model") or ""),
            str((item.get("website_fields") or {}).get("title") or item.get("name") or ""),
        )
    ]
    if config.output.exists():
        payload = json.loads(config.output.read_text(encoding="utf-8"))
    else:
        payload = {"presets": []}
    existing = list(payload.get("presets", []))
    if config.refresh_source:
        existing = [
            item for item in existing
            if not (
                str(item.get("source") or "").casefold()
                == config.refresh_source.casefold()
                and not is_standalone_lf_driver_model(
                    str(item.get("model") or ""),
                    str(
                        (item.get("website_fields") or {}).get("title")
                        or item.get("name")
                        or ""
                    ),
                )
            )
        ]
    merged, stats = merge_presets(
        existing, presets, config.overwrite,
        config.refresh_source,
    )
    payload["presets"] = merged
    payload["downloaded_at"] = utc_now()
    payload["usable_presets"] = len(merged)
    origins = {
        f"{parsed.scheme}://{parsed.netloc}"
        for item in presets
        if (parsed := urlparse(str(item.get("url") or ""))).scheme and parsed.netloc
    }
    payload["crawl_sources"] = sorted({
        *payload.get("crawl_sources", []),
        *origins,
    })
    if not config.dry_run:
        atomic_write_json(config.output, payload)
    return stats


def compiled_patterns(values: list[str] | None) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(value, re.I) for value in (values or []))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="append", default=[], help="Product/catalog URL; repeatable.")
    parser.add_argument("--sitemap", action="append", default=[], help="XML sitemap URL; repeatable.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--source-name", default="Web crawler")
    parser.add_argument("--brand", default="", help="Fallback brand when pages expose none.")
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--include", action="append", help="Only crawl URLs matching this regex.")
    parser.add_argument("--exclude", action="append", help="Skip URLs matching this regex.")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--min-confidence", type=float, default=0.75)
    parser.add_argument("--no-follow-links", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--refresh-source", default="",
        help="Replace matching records only when their current source has this name.",
    )
    parser.add_argument("--fresh", action="store_true", help="Ignore an existing checkpoint.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.seed and not args.sitemap and (args.fresh or not args.checkpoint.exists()):
        raise SystemExit("provide at least one --seed or --sitemap (or resume an existing checkpoint)")
    domains = {item.casefold().removeprefix("www.") for item in args.allow_domain}
    if not domains:
        domains = {
            (urlparse(url).hostname or "").casefold().removeprefix("www.")
            for url in [*args.seed, *args.sitemap]
            if urlparse(url).hostname
        }
    config = CrawlConfig(
        seeds=list(args.seed), sitemaps=list(args.sitemap), output=args.output,
        checkpoint=args.checkpoint, source_name=args.source_name,
        brand_hint=args.brand, allowed_domains=domains,
        include_patterns=compiled_patterns(args.include),
        exclude_patterns=compiled_patterns(args.exclude), max_pages=args.max_pages,
        max_depth=args.max_depth, timeout_s=args.timeout, sleep_s=args.sleep,
        min_confidence=args.min_confidence, follow_links=not args.no_follow_links,
        overwrite=args.overwrite, fresh=args.fresh, dry_run=args.dry_run,
        refresh_source=args.refresh_source,
        user_agent=args.user_agent,
    )
    presets, failures, visited = crawl(config)
    stats = populate_database(config, presets)
    log(
        f"visited={len(visited)} extracted={len(presets)} "
        f"added={stats['added']} updated={stats['updated']} "
        f"unchanged={stats['unchanged']} failures={len(failures)}"
    )
    if config.dry_run and (presets or failures):
        print(json.dumps({"presets": presets, "failures": failures}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
