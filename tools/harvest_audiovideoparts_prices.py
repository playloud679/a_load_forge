#!/usr/bin/env python3
"""Incrementally harvest Audio Video Parts product prices."""
from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.audiovideoparts.com"
DEFAULT_SEED = BASE + "/ecommerce/en/154-speakers"
DRIVER_TERMS = ("speaker", "woofer", "subwoofer", "tweeter", "midrange", "loudspeaker", "coaxial", "driver")

def relevant(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(term in path for term in DRIVER_TERMS)

def fetch(url: str, timeout: float) -> str:
    req = Request(url, headers={"User-Agent": "LoadForge-PriceCrawler/1.0 (+https://github.com/playloud679/a_load_forge)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def links(html: str, page_url: str) -> list[str]:
    out=[]
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        u=urljoin(page_url,a["href"])
        if urlparse(u).netloc == urlparse(BASE).netloc and "/ecommerce/en/" in u and relevant(u) and u not in out:
            out.append(u.split("#",1)[0])
    return out

def product(html: str, url: str) -> dict | None:
    soup=BeautifulSoup(html,"html.parser")
    rows=[]
    for node in soup.select('script[type="application/ld+json"]'):
        try: rows.append(json.loads(node.string or node.get_text()))
        except Exception: pass
    items=[]
    for x in rows:
        items.extend(x if isinstance(x,list) else [x])
    data=next((x for x in items if isinstance(x,dict) and (x.get("@type")=="Product" or "Product" in (x.get("@type") or []))),None)
    if not data:
        amount = soup.select_one('meta[property="product:price:amount"]')
        title = soup.select_one("h1")
        if not amount or not amount.get("content"): return None
        try: price=float(str(amount["content"]).replace(",","."))
        except ValueError: return None
        return {"name":title.get_text(" ",strip=True) if title else url.rsplit("/",1)[-1],"sku":"","mpn":"","price":price,"currency":"EUR","url":url,"seller":"Audio Video Parts","source":"Audio Video Parts price crawler"}
    offer=data.get("offers") or {}; offer=offer[0] if isinstance(offer,list) else offer
    try: price=float(str(offer.get("price")).replace(",","."))
    except (TypeError,ValueError): return None
    if price < 0: return None
    return {"name":str(data.get("name") or "").strip(),"sku":str(data.get("sku") or data.get("mpn") or "").strip(),"mpn":str(data.get("mpn") or "").strip(),"price":price,"currency":str(offer.get("priceCurrency") or "EUR"),"url":url,"seller":"Audio Video Parts","source":"Audio Video Parts price crawler"}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--seed",default=DEFAULT_SEED); ap.add_argument("--checkpoint",type=Path,default=ROOT/"data/audiovideoparts_price_checkpoint.json"); ap.add_argument("--max-pages",type=int,default=500); ap.add_argument("--sleep",type=float,default=1.0); ap.add_argument("--timeout",type=float,default=20); args=ap.parse_args()
    state={"queue":[args.seed],"visited":[],"prices":[],"failures":[]}
    if args.checkpoint.exists(): state.update(json.loads(args.checkpoint.read_text()))
    seen=set(state["visited"]); queue=list(state["queue"])
    queue=[u for u in queue if relevant(u)]
    queue.sort(key=lambda u: (0 if u.endswith('.html') else 1, len(u)))
    for _ in range(args.max_pages):
        if not queue: break
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try:
            html=fetch(url,args.timeout); rec=product(html,url)
            if rec and not any(x.get("url")==url for x in state["prices"]): state["prices"].append(rec)
            new_links=links(html,url)
            new_links.sort(key=lambda u: (0 if (u.endswith('.html') or re.search(r'/ecommerce/en/[^/]+-[0-9]+\.html$',u)) else 1, len(u)))
            for u in new_links:
                if u not in seen and u not in queue and ("?" not in u or "?p=" in u): queue.append(u)
        except Exception as e: state["failures"].append({"url":url,"error":str(e)})
        state.update(queue=queue,visited=sorted(seen)); args.checkpoint.parent.mkdir(parents=True,exist_ok=True); args.checkpoint.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"visited={len(seen)} queue={len(queue)} prices={len(state['prices'])}",flush=True); time.sleep(args.sleep)
    return 0
if __name__ == "__main__": raise SystemExit(main())
