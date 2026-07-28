#!/usr/bin/env python3
"""Import validated Altec Lansing and TAD/Pioneer heritage T/S tables."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from tools import crawl_thiele_small as crawler
except ImportError:  # direct ``python tools/import_heritage_drivers.py``
    import crawl_thiele_small as crawler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "manufacturer_drivers.json"
ALTEC_URL = (
    "https://archive.greatplainsacoustics.com/altec-lansing-library/"
    "altec-lansing-thiele-small-parameters/"
)
TAD_TABLE_URL = (
    "https://www.audioheritage.org/vbulletin/attachment.php?"
    "attachmentid=17142&d=1154455138"
)
TAD_ARCHIVE_URL = (
    "https://www.technicalaudiodevices.com/archived-product/archived-hf-lf/"
)
TAD_CURRENT_URL = "https://www.technicalaudiodevices.com/lf-units/"
USER_AGENT = (
    "LoadForge-Heritage-Importer/1.0 "
    "(+https://github.com/playloud679/a_load_forge)"
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def fetch_text(url: str, timeout_s: float) -> str:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8", errors="replace")


def number(value: object) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class AltecTableParser(HTMLParser):
    """Read data-original-value cells from Great Plains' Supsystic table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.current: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = {key: value or "" for key, value in attrs}
        if tag == "table" and values.get("id") == "supsystic-table-6":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current = []
        elif self.in_table and tag == "td" and self.current is not None:
            self.current.append(values.get("data-original-value", "").strip())

    def handle_endtag(self, tag: str):
        if tag == "tr" and self.in_table and self.current is not None:
            if self.current:
                self.rows.append(self.current)
            self.current = None
        elif tag == "table" and self.in_table:
            self.in_table = False


def infer_nominal_size(model: str, sd_cm2: float) -> float | None:
    clean = model.casefold().replace(" ", "")
    if "6x9" in clean:
        return 6.0
    for prefix in ("er-",):
        if clean.startswith(prefix):
            digits = "".join(char for char in clean[len(prefix):] if char.isdigit())
            if digits:
                size = float(digits[:2])
                if 4.0 <= size <= 21.0:
                    return size
    effective_in = math.sqrt(4.0 * sd_cm2 / math.pi) / 2.54
    for nominal in (4.0, 5.25, 6.5, 8.0, 10.0, 12.0, 15.0, 18.0, 21.0):
        if effective_in <= nominal * 0.91:
            return nominal
    return None


def altec_presets(text: str, fetched_at: str) -> tuple[list[dict], list[dict]]:
    parser = AltecTableParser()
    parser.feed(text)
    rows = parser.rows
    if not rows or rows[0][:3] != ["Model No:", "Xmax (inch)", "Re (ohms)"]:
        raise ValueError("Altec Technical Letter table not found or changed")
    presets: list[dict] = []
    failures: list[dict] = []
    for cells in rows[1:]:
        if len(cells) != 11:
            failures.append({"model": cells[0] if cells else "", "error": "invalid column count"})
            continue
        model = cells[0]
        xmax_in, re_ohm, vd_in3, fs_hz, vas_ft3 = map(number, cells[1:6])
        qts, qms, qes = map(number, cells[7:10])
        if None in (xmax_in, re_ohm, vd_in3, fs_hz, vas_ft3, qts, qms, qes):
            failures.append({"model": model, "error": "missing simulation field"})
            continue
        sd_cm2 = vd_in3 / xmax_in * 6.4516
        driver = {
            "fs_hz": round(fs_hz, 8),
            "vas_l": round(vas_ft3 * 28.316846592, 8),
            "qts": round(qts, 8),
            "qms": round(qms, 8),
            "qes": round(qes, 8),
            "re_ohm": round(re_ohm, 8),
            "sd_cm2": round(sd_cm2, 8),
            "xmax_mm": round(xmax_in * 25.4, 8),
        }
        errors = crawler.validate_driver(driver)
        if errors:
            failures.append({"model": model, "error": "; ".join(errors)})
            continue
        presets.append({
            "name": f"WEB: Altec Lansing {model}",
            "brand": "Altec Lansing",
            "model": model,
            "size_in": infer_nominal_size(model, sd_cm2),
            "kind": "Heritage low-frequency driver",
            "url": ALTEC_URL,
            "source": "Altec Technical Letter 267B archive",
            "driver": driver,
            "website_fields": {
                "title": f"Altec Lansing {model}",
                "brand": "Altec Lansing",
                "model": model,
                "source": "Altec Technical Letter 267B archive",
                "url": ALTEC_URL,
                "fetched_at": fetched_at,
                "extraction_method": "html.table",
                "document": "Altec Lansing Technical Letter No. 267B",
                "archive_host": "Great Plains Acoustic",
                "raw_measurements": {
                    "xmax_in": xmax_in,
                    "re_ohm": re_ohm,
                    "vd_in3": vd_in3,
                    "fs_hz": fs_hz,
                    "vas_ft3": vas_ft3,
                    "qts": qts,
                    "qms": qms,
                    "qes": qes,
                },
                "derived_fields": ["sd_cm2"],
                "derivations": {
                    "sd_cm2": {
                        "formula": "Vd_in3 / Xmax_in * 6.4516",
                        "source_fields": ["Vd", "Xmax"],
                        "confidence": "high",
                    }
                },
            },
        })
    return presets, failures


TAD_MODELS = (
    "TL-1601c", "TL-1601a", "TL-1601b", "TL-1602", "TL-1603",
    "TL-1801", "TL-1102", "TL-1101h", "TM-1201", "TM-1201h",
)
TAD_COLUMNS = {
    "size_in": (16, 16, 16, 16, 16, 18, 11, 11, 12, 12),
    "re_ohm": (6.6, 6.6, 6.6, 6.2, 6.6, 6.6, 7.2, 13, 5.3, 5.3),
    "sd_cm2": (881, 881, 881, 881, 881, 1220, 366, 366, 531, 531),
    "le_mh": (1.9, 1.7, 1.6, 0.9, 1.6, 2.0, 1.1, 2.0, 0.68, 0.68),
    "bl_tm": (20.5, 20.5, 19.5, 21.0, 19.5, 21.0, 13.5, 20.5, 26.0, 36.8),
    "vas_l": (304, 304, 307, 519, 304, 500, 121, 92, 63, 63),
    "cms_mm_per_n": (
        0.2761, 0.2761, 0.2785, 0.4708, 0.2761,
        0.2372, 0.6382, 0.4832, 0.1561, 0.1561,
    ),
    "mms_g": (117, 117, 116, 122, 117, 158, 41.3, 36.3, 6, 6),
    "fs_hz": (28, 28, 28, 21, 28, 26, 31, 38, 52, 52),
    "qms": (8.76, 6.8, 6.8, 2.78, 6.8, 7.94, 4.35, 3.86, 1.43, 1.43),
    "qes": (0.32, 0.32, 0.36, 0.23, 0.36, 0.39, 0.32, 0.27, 0.15, 0.15),
    "qts": (0.31, 0.31, 0.34, 0.21, 0.34, 0.37, 0.30, 0.25, 0.14, 0.14),
    "xmax_mm": (7.5, 8, 8, 5.5, 8, 7.5, 6.2, 2.5, 2.5, 2.5),
    "pe_w": (500, 500, 300, 300, 500, 800, 500, 500, 300, 300),
}


def tad_presets(imported_at: str) -> list[dict]:
    presets: list[dict] = []
    for index, model in enumerate(TAD_MODELS):
        driver = {
            key: float(values[index])
            for key, values in TAD_COLUMNS.items()
            if key != "size_in"
        }
        errors = crawler.validate_driver(driver)
        if errors:
            raise ValueError(f"TAD {model}: {'; '.join(errors)}")
        current = model in {"TL-1601b", "TL-1801"}
        product_url = TAD_CURRENT_URL if current else TAD_ARCHIVE_URL
        presets.append({
            "name": f"PDF: TAD {model}",
            "brand": "TAD",
            "model": model,
            "size_in": float(TAD_COLUMNS["size_in"][index]),
            "kind": "Professional low-frequency driver",
            "url": product_url,
            "source": "TAD/Pioneer official specification archive",
            "driver": driver,
            "website_fields": {
                "title": f"TAD {model}",
                "brand": "TAD",
                "model": model,
                "source": "TAD/Pioneer official specification archive",
                "url": product_url,
                "table_archive_url": TAD_TABLE_URL,
                "imported_at": imported_at,
                "extraction_method": "official.pdf.table",
                "document": "Pioneer TAD Thiele-Small Parameters, © 2005 Pioneer Electronics",
                "raw_measurements": {
                    key: values[index]
                    for key, values in TAD_COLUMNS.items()
                },
                "derivations": {
                    "sd_cm2": {"formula": "Sd_m2 * 10000", "confidence": "exact unit conversion"},
                    "cms_mm_per_n": {
                        "formula": "Cms_1e-4_m_per_n * 0.1",
                        "confidence": "exact unit conversion",
                    },
                },
            },
        })
    return presets


def merge_catalog(path: Path, discovered: list[dict], dry_run: bool) -> dict:
    payload = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"presets": []}
    )
    merged, stats = crawler.merge_presets(payload.get("presets", []), discovered)
    payload["presets"] = merged
    payload["downloaded_at"] = utc_now()
    payload["usable_presets"] = len(merged)
    payload["crawl_sources"] = sorted({
        *payload.get("crawl_sources", []),
        "https://archive.greatplainsacoustics.com",
        "https://www.technicalaudiodevices.com",
    })
    if not dry_run:
        crawler.atomic_write_json(path, payload)
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Altec Technical Letter 267B and Pioneer/TAD official T/S tables."
    )
    parser.add_argument("--altec-input", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    fetched_at = utc_now()
    altec_text = (
        args.altec_input.read_text(encoding="utf-8")
        if args.altec_input
        else fetch_text(ALTEC_URL, args.timeout)
    )
    altec, failures = altec_presets(altec_text, fetched_at)
    tad = tad_presets(fetched_at)
    stats = merge_catalog(args.output, [*altec, *tad], args.dry_run)
    print(json.dumps({
        "altec": len(altec),
        "tad": len(tad),
        "failures": failures,
        **stats,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
