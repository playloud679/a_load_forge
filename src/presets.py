"""
Driver preset catalog: built-in presets plus the optional Loudspeaker
Database import, with brand/size metadata and retailer price enrichment.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from .engine import DriverTS, sd_from_diameter
    from .pricing import _preset_price, _valid_price
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    from engine import DriverTS, sd_from_diameter
    from pricing import _preset_price, _valid_price

LOUDSPEAKER_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "loudspeaker_database_drivers.json"
)
# Presets extracted directly from manufacturer sites (HTML/PDF/API), kept in a
# separate file from the loudspeakerdatabase.com import above: this file is
# safe to ship in a public build, the LSDB one is not (see docs/presets.md).
MANUFACTURER_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "manufacturer_drivers.json"
)


@dataclass(frozen=True)
class DriverPresetInfo:
    """Metadata used to filter a named driver preset in the UI."""

    name: str
    source: str
    brand: str
    model: str
    size_in: float | None = None
    price: float | None = None
    currency: str = ""
    kind: str = ""
    url: str = ""




DRIVER_PRESETS: dict[str, DriverTS] = {
    "KEF B110B article example": DriverTS(
        fs_hz=48.14,
        vas_l=11.52,
        qts=0.362,
        qms=2.372,
        re_ohm=6.89,
        sd_cm2=sd_from_diameter(104.0),
        le_mh=0.421,
        xmax_mm=3.1,
        pe_w=60.0,
    ),
    "Beyma 12CMV2": DriverTS(
        fs_hz=49.0,
        vas_l=76.0,
        qts=0.47,
        qms=3.9,
        re_ohm=6.0,
        sd_cm2=530.0,
        le_mh=1.0,
        xmax_mm=7.0,
        pe_w=320.0,
        mms_g=54.0,
        cms_mm_per_n=0.193,
        bl_tm=13.7,
    ),
    "Beyma 12G40": DriverTS(
        fs_hz=44.0,
        vas_l=81.0,
        qts=0.30,
        qms=11.6,
        re_ohm=6.0,
        sd_cm2=530.0,
        le_mh=2.1,
        xmax_mm=7.0,
        pe_w=500.0,
        mms_g=62.0,
        cms_mm_per_n=0.206,
        bl_tm=18.4,
    ),
    "Beyma 12LX60V2": DriverTS(
        fs_hz=49.0,
        vas_l=43.0,
        qts=0.38,
        qms=15.3,
        re_ohm=5.1,
        sd_cm2=550.0,
        le_mh=2.1,
        xmax_mm=9.0,
        pe_w=700.0,
        mms_g=102.0,
        cms_mm_per_n=0.099,
        bl_tm=20.0,
    ),
    "Beyma 12BR70": DriverTS(
        fs_hz=31.0,
        vas_l=142.0,
        qts=0.50,
        qms=4.44,
        re_ohm=5.6,
        sd_cm2=540.0,
        le_mh=0.8,
        xmax_mm=8.0,
        pe_w=125.0,
        mms_g=74.0,
        cms_mm_per_n=0.345,
        bl_tm=12.1,
    ),
    "Beyma 12MC500": DriverTS(
        fs_hz=57.0,
        vas_l=57.0,
        qts=0.34,
        qms=7.8,
        re_ohm=5.6,
        sd_cm2=550.0,
        le_mh=0.7,
        xmax_mm=8.0,
        pe_w=500.0,
        mms_g=59.0,
        cms_mm_per_n=0.132,
        bl_tm=18.3,
    ),
    "Beyma 12MCS500": DriverTS(
        fs_hz=57.0,
        vas_l=57.0,
        qts=0.36,
        qms=7.8,
        re_ohm=5.6,
        sd_cm2=550.0,
        le_mh=1.1,
        xmax_mm=8.0,
        pe_w=500.0,
        mms_g=59.0,
        cms_mm_per_n=0.132,
        bl_tm=17.6,
    ),
    "Beyma 12WRS400": DriverTS(
        fs_hz=42.0,
        vas_l=91.0,
        qts=0.29,
        qms=7.7,
        re_ohm=5.6,
        sd_cm2=530.0,
        le_mh=1.3,
        xmax_mm=6.3,
        pe_w=400.0,
        mms_g=63.0,
        cms_mm_per_n=0.228,
        bl_tm=17.4,
    ),
    "Beyma 12P80Nd/V2": DriverTS(
        fs_hz=47.0,
        vas_l=65.0,
        qts=0.19,
        qms=5.2,
        re_ohm=5.0,
        sd_cm2=550.0,
        le_mh=0.9,
        xmax_mm=7.5,
        pe_w=700.0,
        mms_g=74.0,
        cms_mm_per_n=0.152,
        bl_tm=23.7,
    ),
    "Beyma 12P1000/Nd": DriverTS(
        fs_hz=47.0,
        vas_l=49.0,
        qts=0.26,
        qms=7.9,
        re_ohm=5.1,
        sd_cm2=550.0,
        le_mh=2.0,
        xmax_mm=8.0,
        pe_w=900.0,
        mms_g=100.0,
        cms_mm_per_n=0.115,
        bl_tm=23.5,
    ),
    "Beyma 12LEX1000Fe": DriverTS(
        fs_hz=49.0,
        vas_l=38.4,
        qts=0.30,
        qms=3.6,
        re_ohm=5.4,
        sd_cm2=550.0,
        le_mh=1.7,
        xmax_mm=11.0,
        pe_w=1000.0,
        mms_g=118.0,
        cms_mm_per_n=0.089,
        bl_tm=24.6,
    ),
    "Beyma 12LEX1300Nd": DriverTS(
        fs_hz=45.0,
        vas_l=43.0,
        qts=0.24,
        qms=4.2,
        re_ohm=5.0,
        sd_cm2=550.0,
        le_mh=1.3,
        xmax_mm=11.0,
        pe_w=1300.0,
        mms_g=125.0,
        cms_mm_per_n=0.100,
        bl_tm=26.4,
    ),
    "Beyma 12CMV3": DriverTS(
        fs_hz=52.0,
        vas_l=85.0,
        qts=0.55,
        qms=10.6,
        re_ohm=6.1,
        sd_cm2=530.0,
        le_mh=0.89,
        xmax_mm=7.0,
        pe_w=320.0,
        mms_g=44.0,
        cms_mm_per_n=0.214,
        bl_tm=12.3,
    ),
    "Turbosound TS-12W350/8W": DriverTS(
        fs_hz=61.0,
        vas_l=19.26,
        qts=0.43,
        qms=11.37,
        re_ohm=5.5,
        sd_cm2=551.55,
        le_mh=1.6,
        xmax_mm=3.8,
        pe_w=350.0,
        mms_g=67.78,
        cms_mm_per_n=0.1,
        bl_tm=17.9,
    ),
    "Turbosound TS-15W300/8A": DriverTS(
        fs_hz=46.0,
        vas_l=130.2,
        qts=0.47,
        qms=16.6,
        re_ohm=6.5,
        sd_cm2=865.7,
        le_mh=1.2,
        xmax_mm=4.9,
        pe_w=300.0,
        mms_g=96.4,
        cms_mm_per_n=0.12,
        bl_tm=19.3,
    ),
    "Scan-Speak 30W/4558T00": DriverTS(
        fs_hz=17.0,
        vas_l=197.0,
        qts=0.32,
        qms=5.01,
        re_ohm=2.6,
        sd_cm2=466.0,
        le_mh=0.83,
        xmax_mm=12.5,
        pe_w=150.0,
        mms_g=135.0,
        cms_mm_per_n=0.65,
        bl_tm=10.5,
    ),
    "Scan-Speak 15W/4531G00": DriverTS(
        fs_hz=40.0,
        vas_l=15.8,
        qts=0.32,
        qms=4.60,
        re_ohm=3.4,
        sd_cm2=95.0,
        le_mh=0.25,
        xmax_mm=6.5,
        pe_w=60.0,
        mms_g=13.0,
        cms_mm_per_n=1.25,
        bl_tm=5.7,
    ),
    "Dayton Audio RSS315HO-4": DriverTS(
        fs_hz=26.2,
        vas_l=53.7,
        qts=0.31,
        qms=3.63,
        re_ohm=3.2,
        sd_cm2=514.7,
        le_mh=1.75,
        xmax_mm=12.3,
        pe_w=700.0,
        mms_g=251.0,
        cms_mm_per_n=0.15,
        bl_tm=20.0,
    ),
    "SB Audience BIANCO-12OB150-01": DriverTS(
        fs_hz=44.0,
        vas_l=103.8,
        qts=0.63,
        qms=6.39,
        re_ohm=7.2,
        sd_cm2=539.1,
        le_mh=1.18,
        xmax_mm=6.79,
        pe_w=150.0,
        mms_g=52.4,
        cms_mm_per_n=0.25,
        bl_tm=12.2,
    ),
    "LaVoce WSF122.02": DriverTS(
        fs_hz=50.0,
        vas_l=88.0,
        qts=0.40,
        qms=4.0,
        re_ohm=5.2,
        sd_cm2=531.0,
        le_mh=0.53,
        xmax_mm=4.3,
        pe_w=200.0,
        mms_g=44.8,
        cms_mm_per_n=0.22,
        bl_tm=12.8,
    ),
    "LaVoce WSF122.50": DriverTS(
        fs_hz=50.0,
        vas_l=72.0,
        qts=0.32,
        qms=5.5,
        re_ohm=5.5,
        sd_cm2=531.0,
        le_mh=0.76,
        xmax_mm=4.7,
        pe_w=250.0,
        mms_g=58.4,
        cms_mm_per_n=0.18,
        bl_tm=17.1,
    ),
    "Aiyima 4ohm 5w 40mm black": DriverTS(
        fs_hz=153.6,
        vas_l=0.1,
        qts=0.459,
        qms=6.015,
        re_ohm=3.56,
        sd_cm2=7.40229915,
        pe_w=5.0,
        mms_g=0.87,
        cms_mm_per_n=1.235,
        bl_tm=2.486,
    ),
    "Aiyima 6ohm 8w 56mm": DriverTS(
        fs_hz=187.6,
        vas_l=0.05,
        qts=0.56,
        qms=4.524,
        re_ohm=6.1,
        sd_cm2=8.24479576,
        pe_w=8.0,
        mms_g=1.39,
        cms_mm_per_n=0.519,
        bl_tm=3.977,
    ),
    "Aiyima 4ohm 20w 58mm": DriverTS(
        fs_hz=156.6,
        vas_l=0.18,
        qts=0.874,
        qms=3.912,
        re_ohm=3.5,
        sd_cm2=16.4029621,
        pe_w=20.0,
        mms_g=2.2,
        cms_mm_per_n=0.47,
        bl_tm=2.62,
    ),
    "Aiyima 4ohm 20w 1.75in": DriverTS(
        fs_hz=168.4,
        vas_l=0.11,
        qts=1.281,
        qms=7.916,
        re_ohm=4.08,
        sd_cm2=8.552985999,
        pe_w=20.0,
        mms_g=0.87,
        cms_mm_per_n=1.025,
        bl_tm=1.565,
    ),
    "Aiyima 4ohm 5w 40mm zinc": DriverTS(
        fs_hz=149.1,
        vas_l=0.1,
        qts=0.389,
        qms=2.739,
        re_ohm=3.0,
        sd_cm2=7.694467267,
        pe_w=5.0,
        mms_g=0.98,
        cms_mm_per_n=1.16,
        bl_tm=2.527,
    ),
    "Aiyima 4ohm 10w 40mm": DriverTS(
        fs_hz=155.6,
        vas_l=0.05,
        qts=0.48,
        qms=3.728,
        re_ohm=4.0,
        sd_cm2=7.258335667,
        pe_w=10.0,
        mms_g=1.7,
        cms_mm_per_n=0.614,
        bl_tm=3.599,
    ),
    "Aiyima 8ohm 15w 3in flat": DriverTS(
        fs_hz=152.5,
        vas_l=0.28,
        qts=0.912,
        qms=2.352,
        re_ohm=7.0,
        sd_cm2=30.48358038,
        pe_w=15.0,
        mms_g=5.14,
        cms_mm_per_n=0.212,
        bl_tm=4.993,
    ),
    "Aiyima 8ohm 4w 1in for harman": DriverTS(
        fs_hz=552.0,
        vas_l=0.01,
        qts=1.451,
        qms=3.993,
        re_ohm=6.79,
        sd_cm2=4.523893421,
        pe_w=4.0,
        mms_g=0.39,
        cms_mm_per_n=0.212,
        bl_tm=2.01,
    ),
    "Aiyima 4ohm 12w 2in": DriverTS(
        fs_hz=188.5,
        vas_l=0.1,
        qts=1.244,
        qms=5.724,
        re_ohm=3.35,
        sd_cm2=12.19220693,
        pe_w=12.0,
        mms_g=1.56,
        cms_mm_per_n=0.458,
        bl_tm=1.964,
    ),
    "Aiyima 8ohm 3w 40mm": DriverTS(
        fs_hz=239.2,
        vas_l=0.04,
        qts=3.758,
        qms=8.05,
        re_ohm=7.21,
        sd_cm2=6.6966189,
        pe_w=3.0,
        mms_g=0.65,
        cms_mm_per_n=0.683,
        bl_tm=1.002,
    ),
    "Aiyima 4ohm 3w 1in": DriverTS(
        fs_hz=478.3,
        vas_l=0.01,
        qts=0.933,
        qms=1.742,
        re_ohm=3.57,
        sd_cm2=5.027255104,
        pe_w=3.0,
        mms_g=0.61,
        cms_mm_per_n=0.182,
        bl_tm=1.823,
    ),
    "Aiyima 4ohm 3w 36mm": DriverTS(
        fs_hz=172.1,
        vas_l=0.07,
        qts=0.623,
        qms=5.192,
        re_ohm=3.68,
        sd_cm2=6.026281568,
        pe_w=3.0,
        mms_g=0.65,
        cms_mm_per_n=1.319,
        bl_tm=1.927,
    ),
    "Aiyima 4ohm 10w 53mm": DriverTS(
        fs_hz=142.6,
        vas_l=0.16,
        qts=0.43,
        qms=4.86,
        re_ohm=4.07,
        sd_cm2=12.37858191,
        pe_w=10.0,
        mms_g=1.74,
        cms_mm_per_n=0.716,
        bl_tm=3.668,
    ),
    "Aiyima 10ohm 10w 50mm": DriverTS(
        fs_hz=191.9,
        vas_l=0.1,
        qts=1.738,
        qms=5.938,
        re_ohm=9.28,
        sd_cm2=12.37858191,
        pe_w=10.0,
        mms_g=1.57,
        cms_mm_per_n=0.439,
        bl_tm=2.686,
    ),
    "Aiyima 4ohm 10w 53mm LY1124-2": DriverTS(
        fs_hz=140.7,
        vas_l=0.22,
        qts=0.534,
        qms=3.245,
        re_ohm=3.14,
        sd_cm2=13.7885287,
        pe_w=10.0,
        mms_g=1.58,
        cms_mm_per_n=0.807,
        bl_tm=2.667,
    ),
    "Aiyima 4ohm 2w 33mm": DriverTS(
        fs_hz=310.0,
        vas_l=0.02,
        qts=1.207,
        qms=5.734,
        re_ohm=3.52,
        sd_cm2=5.309291585,
        pe_w=2.0,
        mms_g=0.42,
        cms_mm_per_n=0.623,
        bl_tm=1.397,
    ),
    "Aiyima 8ohm 1w 25mm altavoz portatil": DriverTS(
        fs_hz=348.0,
        vas_l=0.01,
        qts=0.82,
        qms=3.61,
        re_ohm=7.28,
        sd_cm2=3.204738666,
        pe_w=1.0,
        mms_g=0.3,
        cms_mm_per_n=0.702,
        bl_tm=2.12,
    ),
    "Aiyima 8ohm 3w 30mm altavoz portatil": DriverTS(
        fs_hz=286.4,
        vas_l=0.02,
        qts=1.411,
        qms=6.584,
        re_ohm=7.13,
        sd_cm2=3.870756308,
        pe_w=3.0,
        mms_g=0.36,
        cms_mm_per_n=0.854,
        bl_tm=1.63,
    ),
    "Aiyima 4ohm 5w 1.5in": DriverTS(
        fs_hz=221.2,
        vas_l=0.05,
        qts=0.419,
        qms=1.693,
        re_ohm=3.47,
        sd_cm2=8.193980499,
        pe_w=5.0,
        mms_g=1.0,
        cms_mm_per_n=0.52,
        bl_tm=2.937,
    ),
    "MarkAudio CHR-70": DriverTS(
        fs_hz=65.4,
        vas_l=5.17,
        qts=0.55,
        qms=2.66,
        re_ohm=7.2,
        sd_cm2=50.2,
        le_mh=0.03244,
        xmax_mm=4.3,
        pe_w=20.0,
        mms_g=4.10,
        cms_mm_per_n=1.44,
        bl_tm=4.20,
    ),
}


_BUILT_IN_PRESET_BRANDS = (
    "Aiyima",
    "Beyma",
    "Turbosound",
    "Scan-Speak",
    "Dayton Audio",
    "SB Audience",
    "LaVoce",
    "MarkAudio",
    "KEF",
)


def _built_in_preset_brand(name: str) -> str:
    for brand in _BUILT_IN_PRESET_BRANDS:
        if name.startswith(brand):
            return brand
    return "Other"


def _preset_identity(brand: str, model: str) -> tuple[str, str]:
    """Return the case-insensitive catalog identity used for deduplication."""
    return brand.strip().casefold(), model.strip().casefold()


def _external_catalog_identity(brand: str, model: str, driver: DriverTS) -> tuple[str, str, float]:
    """Return a tolerant identity for duplicate web/retailer listings.

    Retailers frequently omit impedance, inch marks or generic words from the
    model title.  The electrical resistance remains in the key so real 4/8 Ω
    variants are not collapsed accidentally.
    """
    clean = model.casefold().replace("″", '"').replace("–", "-").replace("—", "-")
    clean = re.sub(r"\b\d+(?:\.\d+)?\s*(?:ohm|ohms|ω)\b", " ", clean)
    clean = re.sub(r"\b\d+(?:\.\d+)?\s*(?:in|inch|inches)\b", " ", clean)
    clean = re.sub(r"\b(?:woofer|speaker|driver|loudspeaker)\b", " ", clean)
    clean = re.sub(r"[^a-z0-9]+", "", clean)
    return brand.strip().casefold(), clean, round(float(driver.re_ohm), 1)


def _driver_ts_from_mapping(values: dict) -> DriverTS:
    return DriverTS(
        fs_hz=float(values["fs_hz"]),
        vas_l=float(values["vas_l"]),
        qts=float(values["qts"]),
        qms=float(values["qms"]),
        re_ohm=float(values["re_ohm"]),
        sd_cm2=float(values["sd_cm2"]),
        le_mh=float(values.get("le_mh", 0.0)),
        le10k_mh=float(values["le10k_mh"]) if values.get("le10k_mh") is not None else None,
        xmax_mm=float(values.get("xmax_mm", 0.0)),
        pe_w=float(values.get("pe_w", 0.0)),
        mms_g=float(values["mms_g"]) if values.get("mms_g") is not None else None,
        cms_mm_per_n=(
            float(values["cms_mm_per_n"]) if values.get("cms_mm_per_n") is not None else None
        ),
        bl_tm=float(values["bl_tm"]) if values.get("bl_tm") is not None else None,
    )



def _load_external_presets(
    path: Path,
    *,
    default_source: str,
    dedupe_tag: str,
    reserved: dict[str, DriverTS],
) -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load one optional external preset file (LSDB import or manufacturer crawl).

    ``reserved`` holds every name already claimed by an earlier tier (built-in,
    then LSDB, then manufacturer) so later tiers dedupe against all of them.
    """
    if not path.exists():
        return {}, {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    presets: dict[str, DriverTS] = {}
    info: dict[str, DriverPresetInfo] = {}
    built_in_identities = {
        _preset_identity(
            brand := _built_in_preset_brand(name),
            name.removeprefix(brand).strip() if brand != "Other" else name,
        )
        for name in DRIVER_PRESETS
    }
    taken = {*reserved, *DRIVER_PRESETS}
    identity_to_name: dict[tuple[str, str, float], str] = {}
    identity_score: dict[tuple[str, str, float], tuple[int, float]] = {}
    for item in payload.get("presets", []):
        base_name = str(item["name"])
        item_brand = str(item.get("brand") or "Other")
        item_model = str(item.get("model") or base_name.removeprefix("LSDB: "))
        if _preset_identity(item_brand, item_model) in built_in_identities:
            continue
        name = base_name
        if name in taken or name in presets:
            suffix = str(item.get("lsdb_id") or len(presets) + 1)
            name = f"{base_name} [{dedupe_tag} {suffix}]"
        while name in taken or name in presets:
            name = f"{base_name} [{dedupe_tag} {len(presets) + 1}]"
        try:
            driver = _driver_ts_from_mapping(item["driver"])
        except (KeyError, TypeError, ValueError):
            continue
        item_price = _valid_price(item.get("price"))
        item_currency = str(item.get("currency") or "")
        item_source = str(item.get("source") or default_source)
        enriched_price, enriched_currency, enriched_url = _preset_price(name, item_model, item_brand)
        item_info = DriverPresetInfo(
            name=name,
            source=item_source,
            brand=item_brand,
            model=item_model,
            size_in=(
                float(item["size_in"])
                if item.get("size_in") is not None
                else None
            ),
            price=enriched_price if enriched_price is not None else item_price,
            currency=enriched_currency or item_currency,
            kind=str(item.get("kind") or ""),
            url=enriched_url or str(item.get("url") or ""),
        )
        identity = _external_catalog_identity(item_brand, item_model, driver)
        score = (
            sum(value is not None and float(value or 0.0) != 0.0 for value in (
                driver.le_mh, driver.le10k_mh, driver.xmax_mm, driver.pe_w,
                driver.mms_g, driver.cms_mm_per_n, driver.bl_tm,
            )),
            -float(item_info.price) if item_info.price is not None else float("inf"),
        )
        previous = identity_to_name.get(identity)
        if previous is not None and score <= identity_score[identity]:
            continue
        if previous is not None:
            presets.pop(previous, None)
            info.pop(previous, None)
        presets[name] = driver
        info[name] = item_info
        identity_to_name[identity] = name
        identity_score[identity] = score
    return presets, info


@lru_cache(maxsize=1)
def _load_loudspeaker_database_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load optional loudspeakerdatabase.com presets generated into data/.

    This file is not safe to redistribute in a public build (see
    docs/presets.md); it is expected to be absent outside local development.
    """
    return _load_external_presets(
        LOUDSPEAKER_DATABASE_PATH,
        default_source="Loudspeaker Database",
        dedupe_tag="LSDB",
        reserved={},
    )


@lru_cache(maxsize=1)
def _load_manufacturer_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load presets crawled directly from manufacturer sites (HTML/PDF/API).

    Independent of loudspeakerdatabase.com and safe to ship publicly.
    """
    lsdb_presets, _lsdb_info = _load_loudspeaker_database_presets()
    return _load_external_presets(
        MANUFACTURER_DATABASE_PATH,
        default_source="Manufacturer crawl",
        dedupe_tag="MFR",
        reserved=lsdb_presets,
    )


@lru_cache(maxsize=1)
def _external_tiers() -> list[tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]]:
    return [_load_loudspeaker_database_presets(), _load_manufacturer_presets()]


@lru_cache(maxsize=1)
def driver_preset_names() -> list[str]:
    """Return driver preset names in display order."""
    names = list(DRIVER_PRESETS)
    for presets, _info in _external_tiers():
        names.extend(presets)
    return names


@lru_cache(maxsize=8192)
def driver_preset_info(name: str) -> DriverPresetInfo:
    """Return source, brand and sizing metadata for a driver preset."""
    if name in DRIVER_PRESETS:
        brand = _built_in_preset_brand(name)
        model = name.removeprefix(brand).strip() if brand != "Other" else name
        price, currency, url = _preset_price(name, model, brand)
        return DriverPresetInfo(
            name=name,
            source="Built-in",
            brand=brand,
            model=model,
            price=price,
            currency=currency,
            url=url,
        )
    for _presets, info in _external_tiers():
        if name in info:
            return info[name]
    raise ValueError(f"Unknown driver preset: {name}")


@lru_cache(maxsize=8192)
def get_driver_preset(name: str) -> DriverTS:
    """Return a driver preset by name."""
    if name in DRIVER_PRESETS:
        return DRIVER_PRESETS[name]
    for presets, _info in _external_tiers():
        if name in presets:
            return presets[name]
    raise ValueError(f"Unknown driver preset: {name}")

# Trigger reload
