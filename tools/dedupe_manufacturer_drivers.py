#!/usr/bin/env python3
"""Conservatively remove parameter-identical/subset manufacturer presets."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_REPORT = ROOT / "data" / "manufacturer_driver_dedup_report.json"
REQUIRED = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")


def normalized_identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def present_driver_values(item: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, raw in (item.get("driver") or {}).items():
        if not isinstance(raw, (int, float)):
            continue
        value = round(float(raw), 8)
        if value != 0.0:
            values[key] = value
    return values


def required_signature(item: dict) -> tuple[float, ...] | None:
    values = present_driver_values(item)
    if any(key not in values for key in REQUIRED):
        return None
    return tuple(values[key] for key in REQUIRED)


def dominates(keeper: dict, duplicate: dict) -> bool:
    """True only when duplicate has no value absent/different in keeper."""
    keeper_values = present_driver_values(keeper)
    duplicate_values = present_driver_values(duplicate)
    return bool(duplicate_values) and all(
        key in keeper_values and keeper_values[key] == value
        for key, value in duplicate_values.items()
    )


def compact_model(value: object) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./+_-]*", str(value or "").strip()))


def canonical_model(value: object) -> str:
    model = str(value or "").casefold()
    model = re.sub(r"\.(?:cdr|xlsx?)\b.*$", "", model)
    model = re.sub(r"\b(?:data\s*sheet|loudspeaker|satori|lf drivers?)\b", " ", model)
    model = re.sub(r"\b(?:paper|aluminum|aluminium|carbon|honeycomb|textreme|fiberglass)\b", " ", model)
    model = re.sub(r"\b(?:branco|preto|vermelho|white|black|quadrado)\b", " ", model)
    model = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:inches?|in)\b|\d+[\"″]", " ", model)
    model = re.sub(r"\b\d+\s*(?:ohms?|oh|ω|Ω)\b", " ", model)
    model = re.sub(r"\b(?:rev(?:ision)?|prototype|preliminary|mass production)\b.*$", "", model)
    model = re.sub(r"\(\s*copy\s*\)$", "", model)
    return normalized_identity(model)


def nominal_impedances(value: object) -> set[float]:
    """Return explicitly labelled nominal impedances from a model label."""
    matches = re.findall(
        r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*(?:ohms?|oh|ω|Ω)",
        str(value or "").casefold(),
    )
    return {float(match.replace(",", ".")) for match in matches}


def model_alias_match(left: dict, right: dict) -> bool:
    """Require a strong model alias; equal T/S values alone are insufficient."""
    left_model = str(left.get("model") or "").strip()
    right_model = str(right.get("model") or "").strip()
    left_raw = normalized_identity(left_model)
    right_raw = normalized_identity(right_model)
    if not left_raw or not right_raw:
        return False
    left_impedances = nominal_impedances(left_model)
    right_impedances = nominal_impedances(right_model)
    if left_impedances and right_impedances and left_impedances != right_impedances:
        return False
    if left_raw == right_raw:
        return True
    # Different clean manufacturer codes may legitimately share every T/S
    # value (magnet/version variants), so never infer aliases from numbers.
    if compact_model(left_model) and compact_model(right_model):
        return False
    left_clean = canonical_model(left_model)
    right_clean = canonical_model(right_model)
    if left_clean and left_clean == right_clean:
        return True
    if compact_model(left_model) and len(left_raw) >= 5 and left_raw in right_clean:
        return True
    if compact_model(right_model) and len(right_raw) >= 5 and right_raw in left_clean:
        return True
    return False


def source_score(value: object) -> int:
    source = str(value or "").casefold()
    if "official pdf" in source or "manufacturer datasheet" in source:
        return 5
    if "official" in source or "catalog" in source or " api" in source:
        return 4
    if "manufacturer website" in source:
        return 3
    if "crawler" in source:
        return 2
    if "retailer" in source:
        return 1
    return 0


def model_score(value: object) -> tuple[int, int]:
    model = str(value or "").strip()
    noisy = bool(re.search(
        r"(?:\bloudspeaker\b|\bdata\s*sheet\b|\buntitled\b|\.cdr\b|"
        r"\b(?:inch|ohm|lf drivers?)\b|[\"″])",
        model,
        re.I,
    ))
    compact = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./+_-]*", model))
    return ((2 if compact else 0) - (4 if noisy else 0), -len(model))


def quality_key(item: dict, index: int) -> tuple[int, int, int, int, int]:
    model_quality, inverse_length = model_score(item.get("model"))
    return (
        len(present_driver_values(item)),
        model_quality,
        source_score(item.get("source")),
        inverse_length,
        -index,
    )


def merge_duplicate_metadata(keeper: dict, duplicate: dict) -> None:
    fields = keeper.setdefault("website_fields", {})
    duplicate_fields = duplicate.get("website_fields") or {}

    aliases = list(fields.get("aliases") or [])
    for alias in [duplicate.get("model"), *(duplicate_fields.get("aliases") or [])]:
        alias = str(alias or "").strip()
        if (
            alias
            and normalized_identity(alias) != normalized_identity(keeper.get("model"))
            and alias not in aliases
        ):
            aliases.append(alias)
    if aliases:
        fields["aliases"] = aliases

    additional_sources = list(fields.get("additional_sources") or [])
    for url in [duplicate.get("url"), *(duplicate_fields.get("additional_sources") or [])]:
        url = str(url or "").strip()
        if url and url not in additional_sources:
            additional_sources.append(url)
    if additional_sources:
        fields["additional_sources"] = additional_sources

    merged = list(fields.get("merged_duplicates") or [])
    observation = {
        "brand": duplicate.get("brand"),
        "model": duplicate.get("model"),
        "source": duplicate.get("source"),
        "url": duplicate.get("url"),
    }
    if observation not in merged:
        merged.append(observation)
    fields["merged_duplicates"] = merged

    for key in ("price", "currency", "availability"):
        if keeper.get(key) in (None, "", 0, 0.0) and duplicate.get(key) not in (None, "", 0, 0.0):
            keeper[key] = duplicate[key]


def deduplicate_presets(presets: list[dict]) -> tuple[list[dict], dict]:
    working = copy.deepcopy(presets)
    grouped: dict[tuple[str, tuple[float, ...]], list[int]] = defaultdict(list)
    for index, item in enumerate(working):
        signature = required_signature(item)
        brand = normalized_identity(item.get("brand"))
        if brand and signature is not None:
            grouped[(brand, signature)].append(index)

    removals: dict[int, int] = {}
    decisions: list[dict] = []
    for indices in grouped.values():
        if len(indices) < 2:
            continue
        keepers: list[int] = []
        ordered = sorted(indices, key=lambda index: quality_key(working[index], index), reverse=True)
        for index in ordered:
            keeper_index = next(
                (
                    candidate for candidate in keepers
                    if model_alias_match(working[candidate], working[index])
                    and dominates(working[candidate], working[index])
                ),
                None,
            )
            if keeper_index is None:
                keepers.append(index)
                continue
            removals[index] = keeper_index
            merge_duplicate_metadata(working[keeper_index], working[index])
            decisions.append({
                "kept": {
                    "brand": working[keeper_index].get("brand"),
                    "model": working[keeper_index].get("model"),
                    "source": working[keeper_index].get("source"),
                    "url": working[keeper_index].get("url"),
                    "parameter_count": len(present_driver_values(working[keeper_index])),
                },
                "removed": {
                    "brand": working[index].get("brand"),
                    "model": working[index].get("model"),
                    "source": working[index].get("source"),
                    "url": working[index].get("url"),
                    "parameter_count": len(present_driver_values(working[index])),
                },
                "criterion": (
                    "all non-zero driver parameters identical"
                    if present_driver_values(working[keeper_index]) == present_driver_values(working[index])
                    else "removed driver parameters are an identical subset of kept driver"
                ),
            })

    result = [item for index, item in enumerate(working) if index not in removals]
    report = {
        "before": len(presets),
        "after": len(result),
        "removed": len(removals),
        "decisions": decisions,
    }
    return result, report


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="Write the deduplicated database atomically.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(args.database.read_text(encoding="utf-8"))
    presets, report = deduplicate_presets(list(payload.get("presets") or []))
    report.update({
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "database": str(args.database),
        "applied": bool(args.apply),
    })
    atomic_write(args.report, report)
    if args.apply:
        payload["presets"] = presets
        payload["usable_presets"] = len(presets)
        payload["downloaded_at"] = report["generated_at"]
        atomic_write(args.database, payload)
    print(
        f"before={report['before']} after={report['after']} removed={report['removed']} "
        f"applied={report['applied']} report={args.report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
