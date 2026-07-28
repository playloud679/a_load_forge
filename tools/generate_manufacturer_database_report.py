#!/usr/bin/env python3
"""Generate the current manufacturer-driver database status report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from dedupe_manufacturer_drivers import deduplicate_presets


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_PRICES = ROOT / "data" / "driver_prices.json"
DEFAULT_DEDUPE_REPORT = ROOT / "data" / "manufacturer_driver_dedup_report.json"
DEFAULT_OUTPUT = ROOT / "docs" / "manufacturer-database-status.md"

FIELDS = (
    ("fs_hz", "Fs"),
    ("vas_l", "Vas"),
    ("qts", "Qts"),
    ("qms", "Qms"),
    ("qes", "Qes"),
    ("re_ohm", "Re"),
    ("sd_cm2", "Sd"),
    ("mms_g", "Mms"),
    ("cms_mm_per_n", "Cms"),
    ("bl_tm", "BL"),
    ("xmax_mm", "Xmax"),
    ("pe_w", "Potenza Pe"),
    ("le_mh", "Le"),
)
REQUIRED = tuple(key for key, _ in FIELDS[:7])
OPTIONAL_PRIORITY = ("xmax_mm", "pe_w", "le_mh")
FIELD_LABELS = dict(FIELDS)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def is_present(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def percent(value: int, total: int) -> str:
    return f"{(100.0 * value / total if total else 0.0):.2f}%"


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def markdown_table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def missing_by_brand(rows: list[dict], field: str) -> Counter[str]:
    return Counter(
        str(row.get("brand") or "Senza marchio")
        for row in rows
        if not is_present((row.get("driver") or {}).get(field))
    )


def run_tests() -> tuple[str, str]:
    command = [str(ROOT / ".venv" / "bin" / "python"), "tests/test_all.py"]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    matches = re.findall(
        r"(\d+) passed, (\d+) failed, (\d+) skipped",
        output,
        flags=re.IGNORECASE,
    )
    if not matches:
        matches = re.findall(
            r"PASS:\s*(\d+)\s+FAIL:\s*(\d+)\s+SKIP:\s*(\d+)",
            output,
            flags=re.IGNORECASE,
        )
    if matches:
        passed, failed, skipped = matches[-1]
        summary = f"{passed} superati, {failed} falliti, {skipped} saltati"
    else:
        tail = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "nessun output")
        summary = f"uscita {completed.returncode}: {tail}"
    status = "superata" if completed.returncode == 0 else "fallita"
    return status, summary


def generate_report(
    database_path: Path,
    prices_path: Path,
    dedupe_report_path: Path,
    *,
    top: int,
    test_result: tuple[str, str] | None,
) -> str:
    database = load_json(database_path)
    rows = database.get("presets") or []
    if not isinstance(rows, list):
        raise ValueError(f"{database_path}: 'presets' deve essere una lista")

    total = len(rows)
    brands = {str(row.get("brand") or "").strip() for row in rows}
    brands.discard("")
    coverage = {
        field: sum(is_present((row.get("driver") or {}).get(field)) for row in rows)
        for field, _ in FIELDS
    }
    size_present = sum(is_present(row.get("size_in")) for row in rows)

    priced_rows = [row for row in rows if is_present(row.get("price"))]
    currencies = Counter(str(row.get("currency") or "Non indicata") for row in priced_rows)
    priced_with_url = sum(bool(str(row.get("price_url") or "").strip()) for row in priced_rows)
    priced_with_provenance = sum(
        isinstance((row.get("website_fields") or {}).get("price_provenance"), dict)
        for row in priced_rows
    )
    no_confident_match = sum(
        (row.get("website_fields") or {}).get("price_status") == "no_confident_retailer_match"
        for row in rows
    )

    source_counts = Counter(str(row.get("source") or "Non indicata") for row in rows)
    invalid_required = sum(
        any(not is_present((row.get("driver") or {}).get(field)) for field in REQUIRED)
        for row in rows
    )
    q_conflicts = sum(
        is_present((row.get("driver") or {}).get("qms"))
        and is_present((row.get("driver") or {}).get("qts"))
        and float(row["driver"]["qms"]) <= float(row["driver"]["qts"])
        for row in rows
    )
    invalidated_power = sum(
        isinstance((row.get("website_fields") or {}).get("invalidated_fields", {}).get("pe_w"), dict)
        for row in rows
    )
    field_provenance = {
        field: sum(
            isinstance((row.get("website_fields") or {}).get("field_provenance", {}).get(field), dict)
            for row in rows
        )
        for field in OPTIONAL_PRIORITY
    }
    derived = Counter(
        field
        for row in rows
        for field in ((row.get("website_fields") or {}).get("derived_fields") or [])
    )
    corrections = Counter(
        field
        for row in rows
        for field in ((row.get("website_fields") or {}).get("field_corrections") or {})
    )
    rejected_size_sd = [
        row
        for row in rows
        if (row.get("website_fields") or {}).get("quality_status")
        == "rejected_size_sd_conflict"
    ]

    _, dedupe_preview = deduplicate_presets(rows)
    previous_dedupe: dict[str, Any] = {}
    if dedupe_report_path.exists():
        previous_dedupe = load_json(dedupe_report_path)

    price_index_entries = 0
    price_index_updated = "non disponibile"
    if prices_path.exists():
        prices = load_json(prices_path)
        price_index_entries = len(prices.get("prices") or {})
        price_index_updated = str(prices.get("updated_at") or "non indicato")

    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    database_updated = dt.datetime.fromtimestamp(
        database_path.stat().st_mtime, tz=dt.timezone.utc
    ).astimezone().isoformat(timespec="seconds")

    coverage_rows = []
    for field, label in FIELDS:
        present = coverage[field]
        coverage_rows.append((label, fmt_int(present), fmt_int(total - present), percent(present, total)))
    coverage_rows.append(("Dimensione nominale", fmt_int(size_present), fmt_int(total - size_present), percent(size_present, total)))

    source_rows = [
        (source, fmt_int(count), percent(count, total))
        for source, count in source_counts.most_common(top)
    ]
    missing_sections = []
    for field in OPTIONAL_PRIORITY:
        counts = missing_by_brand(rows, field)
        missing_sections.extend(
            [
                f"### {FIELD_LABELS[field]}",
                "",
                markdown_table(
                    ("Produttore", "Record mancanti"),
                    [(brand, fmt_int(count)) for brand, count in counts.most_common(top)],
                ),
                "",
            ]
        )

    if test_result is None:
        test_text = (
            "Non eseguita durante questa rigenerazione. Usare `--run-tests` per "
            "inserire nel report l'esito fresco della suite completa."
        )
    else:
        status, summary = test_result
        test_text = f"Suite completa **{status}**: {summary}."

    prior_removed = int(previous_dedupe.get("before", 0)) - int(previous_dedupe.get("after", 0))
    prior_text = (
        f"L'ultimo report applicato ha ridotto il catalogo da "
        f"{fmt_int(int(previous_dedupe.get('before', total)))} a "
        f"{fmt_int(int(previous_dedupe.get('after', total)))} record "
        f"({fmt_int(max(prior_removed, 0))} rimossi)."
        if previous_dedupe.get("applied")
        else "Non è disponibile un precedente report di deduplica applicata."
    )

    lines = [
        "# Stato database manufacturer driver",
        "",
        "> File generato automaticamente: non modificare a mano i numeri.  ",
        "> Rigenerazione: `.venv/bin/python tools/generate_manufacturer_database_report.py`",
        "",
        f"Generato: **{generated_at}**",
        f"Database letto: `data/manufacturer_drivers.json` (modificato {database_updated})",
        "",
        "## Sintesi",
        "",
        f"Il catalogo contiene **{fmt_int(total)} driver** di **{fmt_int(len(brands))} produttori**. "
        f"L'app ne espone **{fmt_int(total - len(rejected_size_sd))}** dopo il controllo "
        f"`Sd`/diametro nominale. "
        f"I sette parametri fondamentali sono completi al "
        f"**{percent(sum(all(is_present((row.get('driver') or {}).get(field)) for field in REQUIRED) for row in rows), total)}** "
        f"dei record. I prezzi verificabili coprono il **{percent(len(priced_rows), total)}**.",
        "",
        "## Copertura parametri",
        "",
        markdown_table(("Parametro", "Presenti", "Mancanti", "Copertura"), coverage_rows),
        "",
        "## Prezzi",
        "",
        f"- Driver con prezzo: **{fmt_int(len(priced_rows))}/{fmt_int(total)}** ({percent(len(priced_rows), total)}).",
        f"- Senza prezzo: **{fmt_int(total - len(priced_rows))}**; marcati senza abbinamento commerciale affidabile: **{fmt_int(no_confident_match)}**.",
        f"- Prezzi con URL: **{fmt_int(priced_with_url)}**; con provenienza strutturata: **{fmt_int(priced_with_provenance)}**.",
        f"- Indice commerciale separato: **{fmt_int(price_index_entries)}** offerte; aggiornato `{price_index_updated}`.",
        "- Valute: " + ", ".join(f"{currency} {fmt_int(count)}" for currency, count in currencies.most_common()) + ".",
        "",
        "I record senza corrispondenza sicura restano intenzionalmente senza prezzo: il report non considera stime o medie inventate.",
        "",
        "## Qualità e provenienza",
        "",
        f"- Record con almeno un parametro fondamentale non valido: **{fmt_int(invalid_required)}**.",
        f"- Conflitti fisici `Qms <= Qts`: **{fmt_int(q_conflicts)}**.",
        f"- Vecchi valori Pe invalidati perché privi di unità W/kW: **{fmt_int(invalidated_power)}**.",
        f"- Correzioni tracciate `Sd`: **{fmt_int(corrections['sd_cm2'])}**; "
        f"dimensione nominale: **{fmt_int(corrections['size_in'])}**.",
        f"- Record esclusi per conflitto irrisolto `Sd`/diametro nominale: "
        f"**{fmt_int(len(rejected_size_sd))}**.",
        f"- Provenienza esplicita da refresh: Xmax **{fmt_int(field_provenance['xmax_mm'])}**, "
        f"Pe **{fmt_int(field_provenance['pe_w'])}**, Le **{fmt_int(field_provenance['le_mh'])}**.",
        "- Campi derivati tracciati: "
        + ", ".join(f"{FIELD_LABELS.get(field, field)} **{fmt_int(count)}**" for field, count in derived.most_common())
        + ".",
        "",
        "Le derivazioni vengono conteggiate solo quando memorizzate in `website_fields.derived_fields`; i valori pubblicati e quelli derivati restano distinguibili.",
        "",
        "### Conflitti Sd/dimensione nominale esclusi",
        "",
        markdown_table(
            ("Produttore", "Modello", "Nominale in", "Sd cm²", "Ø effettivo in"),
            [
                (
                    str(row.get("brand") or ""),
                    str(row.get("model") or ""),
                    f"{float(row.get('size_in') or 0.0):g}",
                    f"{float((row.get('driver') or {}).get('sd_cm2') or 0.0):g}",
                    f"{math.sqrt(4.0 * float((row.get('driver') or {}).get('sd_cm2') or 0.0) / math.pi) / 2.54:.2f}",
                )
                for row in rejected_size_sd
            ],
        ),
        "",
        "## Deduplicazione",
        "",
        f"Dry-run corrente: **{fmt_int(dedupe_preview['before'])} → {fmt_int(dedupe_preview['after'])}**, "
        f"duplicati conservativi rimovibili **{fmt_int(dedupe_preview['removed'])}**.",
        "",
        prior_text,
        "",
        "## Principali fonti",
        "",
        markdown_table(("Fonte", "Driver", "Quota"), source_rows),
        "",
        "## Lacune prioritarie per produttore",
        "",
        *missing_sections,
        "## Verifica software",
        "",
        test_text,
        "",
        "## Rigenerazione",
        "",
        "```bash",
        ".venv/bin/python tools/generate_manufacturer_database_report.py",
        "```",
        "",
        "Per aggiornare anche l'esito della suite completa:",
        "",
        "```bash",
        ".venv/bin/python tools/generate_manufacturer_database_report.py --run-tests",
        "```",
        "",
        "Il comando è di sola lettura sui database e sovrascrive atomicamente soltanto questo report.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument("--dedupe-report", type=Path, default=DEFAULT_DEDUPE_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=15, help="Righe massime per classifica")
    parser.add_argument("--run-tests", action="store_true", help="Esegue e registra tests/test_all.py")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.top < 1:
        raise SystemExit("--top deve essere almeno 1")
    test_result = run_tests() if args.run_tests else None
    report = generate_report(
        args.database.resolve(),
        args.prices.resolve(),
        args.dedupe_report.resolve(),
        top=args.top,
        test_result=test_result,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(output)
    print(f"Report aggiornato: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
