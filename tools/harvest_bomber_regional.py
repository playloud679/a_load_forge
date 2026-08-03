#!/usr/bin/env python3
"""Import exact Bomber driver offers from Fortaleza Som's public catalog."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bomberregional_harvest_checkpoint.json"
URL = "https://www.fortalezasom.com.br/todas-as-marcas/bomber"

def main() -> None:
    html = urlopen(Request(URL, headers={"User-Agent": "LoadForge/0.8"}), timeout=30).read().decode("utf-8", "ignore")
    # The storefront's view_item_list JSON is authoritative and includes the
    # canonical product URL, brand, exact title and current BRL price.
    match = re.search(r"view_item_list'\s*,\s*(\{.*?\})\);", html, re.S)
    if not match:
        raise RuntimeError("Bomber product feed not found")
    feed = json.loads(match.group(1))
    records = []
    for item in feed.get("items", []):
        name = str(item.get("item_name") or "")
        if "BOMBER" not in name.upper() or any(x in name.upper() for x in ("KIT REPARO", "CAIXA ")):
            continue
        price = item.get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        # Product URLs are present in the adjacent storefront feed; retain the
        # stable numeric id when no URL is exposed so the offer remains keyed.
        pid = str(item.get("item_id") or "")
        records.append({"name": name, "brand": "Bomber", "mpn": pid,
                        "sku": pid, "url": f"{URL}#product-{pid}",
                        "price": float(price), "currency": "BRL",
                        "availability": "InStock"})
    OUT.write_text(json.dumps({"source": URL, "fetched_at": datetime.now(timezone.utc).isoformat(), "prices": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BomberRegional: {len(records)} offers")

if __name__ == "__main__":
    main()
