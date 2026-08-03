"""Merge AudioVideoParts price records into the shared catalog."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checkpoint = ROOT / "data/audiovideoparts_price_checkpoint.json"
catalog_paths = [
    ROOT / "data/catalog_proprietario.json",
    ROOT / "data/catalog_vituixcad.json",
    ROOT / "data/catalog_lsdb.json",
    ROOT / "data/catalog_speakerboxlite.json",
]


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def variants(value):
    raw = norm(value)
    return {raw, raw.replace("0", ""), re.sub(r"^0+", "", raw)} - {""}


cp = json.loads(checkpoint.read_text())
records = cp.get("prices", [])
total_added = total_updated = 0
for catalog_path in catalog_paths:
    data = json.loads(catalog_path.read_text())
    items = next((v for v in data.values() if isinstance(v, list)), [])
    by_id = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in ("model", "matched_mpn", "name", "matched_name"):
            for k in variants(item.get(field)):
                by_id.setdefault(k, []).append(item)
    added = updated = 0
    for rec in records:
        url = rec.get("url")
        if not url or not rec.get("price"):
            continue
        matches = []
        for k in variants(rec.get("name")):
            matches.extend(by_id.get(k, []))
        if not matches:
            rv = variants(rec.get("name"))
            for item in items:
                if any(
                    any(len(k) >= 5 and (k in r or r in k) for k in variants(item.get(field)) for r in rv)
                    for field in ("model", "matched_mpn")
                ):
                    matches.append(item)
        for existing in {id(x): x for x in matches}.values():
            existing["price_url"] = url
            existing["price_source"] = "Audio Video Parts"
            if not existing.get("price"):
                existing["price"] = rec["price"]
                existing["price_currency"] = rec.get("currency", "EUR")
                updated += 1
            added += 1
    catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(catalog_path.name, added, updated)
    total_added += added
    total_updated += updated
print(f"total matched/filled: {total_added}/{total_updated}")
