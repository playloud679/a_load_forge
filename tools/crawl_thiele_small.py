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
)
PARAMETER_BY_KEY = {item.key: item for item in PARAMETERS}
REQUIRED_DRIVER_FIELDS = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")
OPTIONAL_DRIVER_FIELDS = (
    "qes", "le_mh", "le10k_mh", "xmax_mm", "pe_w", "mms_g",
    "cms_mm_per_n", "bl_tm",
)
NUMBER_RE = r"[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][-+]?\d+)?"
INCH_SIZE_RE = re.compile(
    r"(?<![\d./])"
    r"(?P<whole>\d+(?:[.,]\d+)?)"
    r"(?:\s*[- ]\s*(?P<numerator>\d+)\s*/\s*(?P<denominator>\d+))?"
    r"\s*(?:inch(?:es)?|in\.?|[\"″])(?=\s|$|[),/x×])",
    re.I,
)
UNIT_RE = r"(?:k\s*hz|hz|sq\s*\.?\s*in(?:ches)?|sq\s*\.?\s*m(?:eters?)?|m(?:\s*\^?\s*3|³)|dm(?:\s*\^?\s*3|³)|ml|cm\s*(?:\^?\s*2|²)|k\s*/?\s*mm\s*(?:\^?\s*2|²|/2)|mm\s*(?:\^?\s*2|²)|m\s*(?:\^?\s*2|²)|in(?:\s*\^?\s*2|²)|ft\s*\.?\s*(?:\^?\s*3|³)|lit(?:er|re)s?|[lL]|k?ohms?|Ω|mΩ|mh|µh|μh|uh|henry|h|mm|cm|inch(?:es)?|in|kw|w\s*_?\s*rms|watts?|w|kg|grams?|g|mg|m/n|mm/n|µm/n|μm/n|um/n|t\s*[·*]?\s*m|tm|n/a|n\s*s/m|kg/s)?"
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
    for spec in PARAMETERS:
        for alias in spec.aliases:
            alias_norm = normalized_label(alias)
            if normalized == alias_norm or compact == alias_norm.replace(" ", ""):
                return spec.key
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
        "liter": "l", "liters": "l", "litre": "l", "litres": "l", "dm3": "l",
        "ohms": "ohm", "ohm": "ohm", "milliohm": "mohm", "mω": "mohm",
        "henry": "h", "watts": "w", "watt": "w", "wrms": "w", "grams": "g", "gram": "g",
        "inch": "in", "inches": "in", "µh": "uh", "µm/n": "um/n",
        "tsm": "tm", "n/a": "tm", "ns/m": "kg/s",
        "sqin": "in2", "sqinches": "in2", "sqm": "m2", "sqmeters": "m2", "sqmeter": "m2",
    }
    return aliases.get(unit, unit)


def convert_measurement(key: str, raw_value: object, raw_unit: str = "") -> float | None:
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
    raw_value, parsed_unit = split_value_and_unit(raw, unit)
    if key == "pe_w" and not normalize_unit(parsed_unit):
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
            if canonical_parameter(label) and (
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
        pattern = re.compile(
            rf"(?<![A-Za-z0-9])(?P<label>{alias_pattern})(?![A-Za-z0-9])"
            rf"(?:\)|\.)?\s*(?:\([^)]{{0,30}}\)|\[[^]]{{0,30}}\])?"
            rf"\s*(?:[*¹²³]+)?\s*(?:[:=\-–—：]|is)?\s*"
            rf"{tolerance_prefix}{signed_value_prefix}"
            rf"(?P<value>{NUMBER_RE})[\t \r\n]{{0,16}}"
            rf"\[?(?P<unit>{UNIT_RE})\]?",
            re.I,
        )
        for match in pattern.finditer(text):
            # A generic ``power rating`` substring inside ``continuous power
            # rating`` or ``program power rating`` is not Pe/AES/RMS power.
            # Those values are usually 2x the thermal rating and must not win
            # merely because they occur first on the page.
            if spec.key == "pe_w":
                prefix = text[max(0, match.start() - 24):match.start()].casefold()
                if re.search(r"(?:continuous|program|maximum|max\.?)[ \t]+$", prefix):
                    continue
            unit = match.group("unit") or ""
            if spec.key == "pe_w" and not normalize_unit(unit):
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
            unit = match.group("unit") or ""
            value = convert_measurement(spec.key, match.group("value"), unit)
            if value is not None:
                found.append(Measurement(
                    spec.key, value, match.group("value"), unit,
                    match.group("label"), "html.text",
                ))
    return found


def choose_measurements(items: Iterable[Measurement]) -> dict[str, Measurement]:
    priority = {
        "jsonld.additionalProperty": 4,
        "jsonld.field": 3,
        "html.table": 2,
        "pdf.table": 2,
        "html.text": 1,
        "pdf.text": 1,
    }
    unitless_keys = {"qts", "qms", "qes"}

    def quality(item: Measurement) -> tuple[int, int]:
        explicit_unit = int(bool(normalize_unit(item.unit))) if item.key not in unitless_keys else 0
        if item.key == "pe_w":
            return explicit_unit, priority.get(item.method, 0)
        return priority.get(item.method, 0), explicit_unit

    chosen: dict[str, Measurement] = {}
    for item in items:
        current = chosen.get(item.key)
        if current is None or quality(item) > quality(current):
            chosen[item.key] = item
    return chosen


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
    chosen = choose_measurements([*measurements, *table_items, *text_items])
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
    raw_measurements = {
        key: {
            "value": item.value,
            "raw_value": item.raw_value,
            "unit": item.unit,
            "label": item.label,
            "method": item.method,
        }
        for key, item in chosen.items()
    }
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
            "fetched_at": utc_now(),
            "extraction_method": extraction_method,
            "confidence": round(confidence, 3),
            "raw_measurements": raw_measurements,
            "derived_fields": derived_fields,
            "derivations": derivations,
        },
    }
    return preset, []


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
    try:
        layout = "\n".join(
            page.extract_text(extraction_mode="layout") or "" for page in reader.pages
        )
    except Exception:
        layout = ""
    plain = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = f"{layout}\n{plain}" if layout else plain
    metadata = reader.metadata or {}
    return PageData(title=str(metadata.get("/Title") or ""), text=text)


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
        if changed:
            current = dict(current)
            current["driver"] = driver
            fields = dict(current.get("website_fields") or {})
            sources = list(fields.get("additional_sources") or [])
            source_url = str(item.get("url") or "")
            if source_url and source_url not in sources:
                sources.append(source_url)
            fields["additional_sources"] = sources
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
