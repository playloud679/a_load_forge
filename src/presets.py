"""
Driver preset catalog: built-ins plus optional Loudspeaker Database,
manufacturer-crawl, VituixCAD and Speaker Box Lite imports, with brand/size
metadata and retailer price enrichment.
"""

from __future__ import annotations

import io
import json
import math
import os
import pickle
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from .engine import DriverTS, sd_from_diameter
    from .pricing import DRIVER_PRICES_PATH, _preset_price, _valid_price, convert_price
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    from engine import DriverTS, sd_from_diameter  # type: ignore[no-redef]
    from pricing import DRIVER_PRICES_PATH, _preset_price, _valid_price, convert_price  # type: ignore[no-redef]


class _SafeCatalogUnpickler(pickle.Unpickler):
    """Unpickler robust against top-level vs package module naming for acoustics/engine."""

    def find_class(self, module: str, name: str) -> object:
        if module.startswith("src."):
            mod_sub = module.removeprefix("src.")
            try:
                mod = __import__(module, fromlist=[name])
                return getattr(mod, name)
            except Exception:
                pass
            mod = __import__(mod_sub, fromlist=[name])
            return getattr(mod, name)
        elif module in {"engine", "presets", "pricing", "ranking"}:
            try:
                mod = __import__(f"src.{module}", fromlist=[name])
                return getattr(mod, name)
            except Exception:
                pass
            mod = __import__(module, fromlist=[name])
            return getattr(mod, name)
        return super().find_class(module, name)


def _safe_unpickle_bytes(data: bytes) -> object:
    return _SafeCatalogUnpickler(io.BytesIO(data)).load()

LOUDSPEAKER_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "catalog_lsdb.json"
)
FIRESTORE_PRESETS_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "catalog_firestore.cache.pickle"
)
# Presets extracted directly from manufacturer sites (HTML/PDF/API), kept in a
# separate file from the loudspeakerdatabase.com import above: this file is
# safe to ship in a public build, the LSDB one is not (see docs/presets.md).
def manufacturer_database_path(
    env: dict[str, str] | None = None,
) -> Path:
    """Return the built-in or read-only mounted manufacturer catalog path."""
    values = os.environ if env is None else env
    configured = str(values.get("LOAD_FORGE_MANUFACTURER_CATALOG_PATH", "")).strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "catalog_proprietario.json"


MANUFACTURER_DATABASE_PATH = manufacturer_database_path()
# Publicly reachable but third-party aggregated VituixCAD online database.
# Keep it separate from manufacturer-original data and review upstream terms
# before including the generated file in a public redistribution.
VITUIXCAD_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "catalog_vituixcad.json"
)
# Community-edited public aggregate. Its importer enforces the Q identity and
# checks Sd against Vas/Cms physics before this optional tier is generated.
SPEAKERBOXLITE_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "catalog_speakerboxlite.json"
)
ZTZ_AUDIO_DATABASE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data" / "catalog_ztzaudio_lf_ferrite_presets.json"
)

PRESET_PROVENANCE_CATEGORIES = (
    "Load Forge database",
    "Z Bench",
    "LSDB",
    "VituixCAD",
    "Speaker Box Lite",
)

# A conventional cone's effective piston is smaller than its nominal frame.
# Keep enough room for unusually wide surrounds, but reject model-number and
# catalog-label mistakes such as a 211 cm² piston being presented as 10".
NOMINAL_SIZE_SD_MIN_DIAMETER_RATIO = 0.70
NOMINAL_SIZE_SD_MAX_DIAMETER_RATIO = 1.15
NOMINAL_SIZE_SD_ANCHORS = (
    (0.75, 2.5), (1.0, 5.0), (1.5, 8.0), (2.0, 13.0), (2.5, 22.0),
    (3.0, 32.0), (3.5, 38.0), (4.0, 50.0), (4.5, 65.0),
    (5.0, 80.0), (5.25, 90.0), (5.5, 100.0), (6.0, 115.0),
    (6.5, 132.0), (7.0, 150.0), (7.5, 158.0), (8.0, 220.0),
    (8.5, 240.0), (9.0, 255.0), (9.5, 280.0), (10.0, 350.0),
    (11.0, 410.0), (12.0, 530.0), (13.0, 610.0), (13.5, 700.0),
    (14.0, 750.0), (15.0, 855.0), (16.0, 950.0), (18.0, 1210.0),
    (19.0, 1450.0), (21.0, 1680.0), (24.0, 2200.0),
)


def effective_piston_diameter_in(sd_cm2: float) -> float:
    """Return the circular effective-piston diameter represented by Sd."""
    sd = float(sd_cm2)
    if not math.isfinite(sd) or sd <= 0.0:
        raise ValueError("Sd must be positive and finite")
    return math.sqrt(4.0 * sd / math.pi) / 2.54


def nominal_size_matches_sd(size_in: float, sd_cm2: float) -> bool:
    """Return whether nominal frame size and effective piston area can coexist."""
    size = float(size_in)
    if not math.isfinite(size) or size <= 0.0:
        return False
    try:
        ratio = effective_piston_diameter_in(sd_cm2) / size
    except (TypeError, ValueError):
        return False
    return (
        NOMINAL_SIZE_SD_MIN_DIAMETER_RATIO
        <= ratio
        <= NOMINAL_SIZE_SD_MAX_DIAMETER_RATIO
    )


def coherent_nominal_size_in(
    size_in: float | None,
    sd_cm2: float,
) -> float | None:
    """Keep a plausible nominal size or infer the nearest class from Sd."""
    size = float(size_in) if size_in is not None else None
    if size is not None and nominal_size_matches_sd(size, sd_cm2):
        return size
    sd = float(sd_cm2)
    if not math.isfinite(sd) or sd <= 0.0:
        return size
    nominal, _anchor = min(
        NOMINAL_SIZE_SD_ANCHORS,
        key=lambda item: abs(math.log(sd / item[1])),
    )
    return nominal


@dataclass(frozen=True)
class MechanicalDimensions:
    """Physical driver envelope used by the drawing/layout tools, not T/S."""

    overall_diameter_mm: float | None = None
    cutout_diameter_mm: float | None = None
    depth_mm: float | None = None
    mounting_depth_mm: float | None = None
    bolt_circle_mm: float | None = None
    mounting_hole_count: int | None = None
    mounting_hole_diameter_mm: float | None = None
    weight_kg: float | None = None


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
    part_number: str = ""
    mechanical: MechanicalDimensions | None = None
    published_specs: dict[str, float] | None = None


@dataclass(frozen=True)
class PassiveRadiatorPreset:
    """Catalogued passive-radiator mechanical parameters."""

    name: str
    brand: str
    model: str
    sp_cm2: float
    fp_hz: float
    qmp: float
    mmp_g: float
    xmax_mm: float = 0.0
    source: str = "DIY Audio"
    url: str = ""


PASSIVE_RADIATOR_PRESETS: dict[str, PassiveRadiatorPreset] = {
    "Accuton ASP250": PassiveRadiatorPreset(
        name="Accuton ASP250", brand="Accuton", model="ASP250",
        sp_cm2=330.0, fp_hz=14.0, qmp=5.0, mmp_g=130.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/accuton-asp250.html",
    ),
    "Accuton P220": PassiveRadiatorPreset(
        name="Accuton P220", brand="Accuton", model="P220",
        sp_cm2=214.0, fp_hz=18.0, qmp=4.5, mmp_g=70.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/accuton-p220.html",
    ),
    "Accuton P280": PassiveRadiatorPreset(
        name="Accuton P280", brand="Accuton", model="P280",
        sp_cm2=400.0, fp_hz=15.0, qmp=4.5, mmp_g=150.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/accuton-p280.html",
    ),
    "CSS APR10": PassiveRadiatorPreset(
        name="CSS APR10", brand="CSS", model="APR10",
        sp_cm2=320.0, fp_hz=28.0, qmp=4.5, mmp_g=66.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/css-apr10.html",
    ),
    "CSS APR12": PassiveRadiatorPreset(
        name="CSS APR12", brand="CSS", model="APR12",
        sp_cm2=530.0, fp_hz=20.0, qmp=3.0, mmp_g=50.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/css-apr12.html",
    ),
    "Dayton Audio DMA105-PR": PassiveRadiatorPreset(
        name="Dayton Audio DMA105-PR", brand="Dayton Audio", model="DMA105-PR",
        sp_cm2=54.1, fp_hz=37.9, qmp=7.8, mmp_g=29.3, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dma105-pr.html",
    ),
    "Dayton Audio DMA45-PR": PassiveRadiatorPreset(
        name="Dayton Audio DMA45-PR", brand="Dayton Audio", model="DMA45-PR",
        sp_cm2=8.6, fp_hz=60.0, qmp=2.75, mmp_g=2.8, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dma45-pr.html",
    ),
    "Dayton Audio DMA58-PR": PassiveRadiatorPreset(
        name="Dayton Audio DMA58-PR", brand="Dayton Audio", model="DMA58-PR",
        sp_cm2=14.5, fp_hz=39.8, qmp=3.93, mmp_g=6.7, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dma58-pr.html",
    ),
    "Dayton Audio DMA70-PR": PassiveRadiatorPreset(
        name="Dayton Audio DMA70-PR", brand="Dayton Audio", model="DMA70-PR",
        sp_cm2=22.9, fp_hz=34.5, qmp=3.86, mmp_g=12.0, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dma70-pr.html",
    ),
    "Dayton Audio DMA80-PR": PassiveRadiatorPreset(
        name="Dayton Audio DMA80-PR", brand="Dayton Audio", model="DMA80-PR",
        sp_cm2=31.2, fp_hz=34.6, qmp=8.91, mmp_g=13.7, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dma80-pr.html",
    ),
    "Dayton Audio DS115-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS115-PR", brand="Dayton Audio", model="DS115-PR",
        sp_cm2=54.1, fp_hz=29.3, qmp=3.66, mmp_g=13.0, xmax_mm=6.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds115-pr.html",
    ),
    "Dayton Audio DS135-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS135-PR", brand="Dayton Audio", model="DS135-PR",
        sp_cm2=75.4, fp_hz=27.7, qmp=3.93, mmp_g=21.8, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds135-pr.html",
    ),
    "Dayton Audio DS175-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS175-PR", brand="Dayton Audio", model="DS175-PR",
        sp_cm2=128.7, fp_hz=30.2, qmp=1.8, mmp_g=37.5, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds175-pr.html",
    ),
    "Dayton Audio DS215-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS215-PR", brand="Dayton Audio", model="DS215-PR",
        sp_cm2=211.2, fp_hz=23.3, qmp=7.34, mmp_g=68.8, xmax_mm=11.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds215-pr.html",
    ),
    "Dayton Audio DS270-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS270-PR", brand="Dayton Audio", model="DS270-PR",
        sp_cm2=365.0, fp_hz=24.0, qmp=3.5, mmp_g=40.0, xmax_mm=7.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds270-pr.html",
    ),
    "Dayton Audio DS315-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS315-PR", brand="Dayton Audio", model="DS315-PR",
        sp_cm2=480.0, fp_hz=17.0, qmp=3.0, mmp_g=200.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds315-pr.html",
    ),
    "Dayton Audio DS90-PR": PassiveRadiatorPreset(
        name="Dayton Audio DS90-PR", brand="Dayton Audio", model="DS90-PR",
        sp_cm2=31.2, fp_hz=42.4, qmp=5.9, mmp_g=5.5, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ds90-pr.html",
    ),
    "Dayton Audio DSA115-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA115-PR", brand="Dayton Audio", model="DSA115-PR",
        sp_cm2=54.1, fp_hz=30.9, qmp=3.48, mmp_g=11.7, xmax_mm=6.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa115-pr.html",
    ),
    "Dayton Audio DSA135-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA135-PR", brand="Dayton Audio", model="DSA135-PR",
        sp_cm2=75.4, fp_hz=27.9, qmp=3.7, mmp_g=21.5, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa135-pr.html",
    ),
    "Dayton Audio DSA175-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA175-PR", brand="Dayton Audio", model="DSA175-PR",
        sp_cm2=128.7, fp_hz=26.8, qmp=4.3, mmp_g=30.7, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa175-pr.html",
    ),
    "Dayton Audio DSA215-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA215-PR", brand="Dayton Audio", model="DSA215-PR",
        sp_cm2=211.2, fp_hz=25.6, qmp=7.66, mmp_g=67.0, xmax_mm=11.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa215-pr.html",
    ),
    "Dayton Audio DSA270-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA270-PR", brand="Dayton Audio", model="DSA270-PR",
        sp_cm2=353.0, fp_hz=21.9, qmp=5.26, mmp_g=88.4, xmax_mm=11.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa270-pr.html",
    ),
    "Dayton Audio DSA315-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA315-PR", brand="Dayton Audio", model="DSA315-PR",
        sp_cm2=480.0, fp_hz=17.5, qmp=6.23, mmp_g=142.6, xmax_mm=13.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa315-pr.html",
    ),
    "Dayton Audio DSA90-PR": PassiveRadiatorPreset(
        name="Dayton Audio DSA90-PR", brand="Dayton Audio", model="DSA90-PR",
        sp_cm2=31.2, fp_hz=43.7, qmp=5.72, mmp_g=5.0, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-dsa90-pr.html",
    ),
    "Dayton Audio Epique E150HE-PR": PassiveRadiatorPreset(
        name="Dayton Audio Epique E150HE-PR", brand="Dayton Audio", model="Epique E150HE-PR",
        sp_cm2=132.0, fp_hz=30.0, qmp=3.8, mmp_g=15.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-epique-e150he-pr.html",
    ),
    "Dayton Audio Epique E180HE-PR": PassiveRadiatorPreset(
        name="Dayton Audio Epique E180HE-PR", brand="Dayton Audio", model="Epique E180HE-PR",
        sp_cm2=178.0, fp_hz=26.0, qmp=3.5, mmp_g=20.0, xmax_mm=9.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-epique-e180he-pr.html",
    ),
    "Dayton Audio ND105-PR": PassiveRadiatorPreset(
        name="Dayton Audio ND105-PR", brand="Dayton Audio", model="ND105-PR",
        sp_cm2=54.0, fp_hz=42.0, qmp=4.0, mmp_g=7.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-nd105-pr.html",
    ),
    "Dayton Audio ND140-PR": PassiveRadiatorPreset(
        name="Dayton Audio ND140-PR", brand="Dayton Audio", model="ND140-PR",
        sp_cm2=84.0, fp_hz=36.0, qmp=3.8, mmp_g=9.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-nd140-pr.html",
    ),
    "Dayton Audio ND65-PR": PassiveRadiatorPreset(
        name="Dayton Audio ND65-PR", brand="Dayton Audio", model="ND65-PR",
        sp_cm2=22.0, fp_hz=48.0, qmp=4.5, mmp_g=3.5, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-nd65-pr.html",
    ),
    "Dayton Audio ND90-PR": PassiveRadiatorPreset(
        name="Dayton Audio ND90-PR", brand="Dayton Audio", model="ND90-PR",
        sp_cm2=32.0, fp_hz=50.0, qmp=4.5, mmp_g=4.5, xmax_mm=4.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-nd90-pr.html",
    ),
    "Dayton Audio RSS210-PR": PassiveRadiatorPreset(
        name="Dayton Audio RSS210-PR", brand="Dayton Audio", model="RSS210-PR",
        sp_cm2=214.0, fp_hz=22.0, qmp=3.2, mmp_g=30.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-rss210-pr.html",
    ),
    "Dayton Audio RSS265-PR": PassiveRadiatorPreset(
        name="Dayton Audio RSS265-PR", brand="Dayton Audio", model="RSS265-PR",
        sp_cm2=356.3, fp_hz=19.6, qmp=4.92, mmp_g=200.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-rss265-pr.html",
    ),
    "Dayton Audio RSS315-PR": PassiveRadiatorPreset(
        name="Dayton Audio RSS315-PR", brand="Dayton Audio", model="RSS315-PR",
        sp_cm2=506.7, fp_hz=21.0, qmp=4.79, mmp_g=300.0, xmax_mm=15.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-rss315-pr.html",
    ),
    "Dayton Audio RSS390-PR": PassiveRadiatorPreset(
        name="Dayton Audio RSS390-PR", brand="Dayton Audio", model="RSS390-PR",
        sp_cm2=829.6, fp_hz=18.2, qmp=4.01, mmp_g=400.0, xmax_mm=18.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-rss390-pr.html",
    ),
    "Dayton Audio RSS460-PR": PassiveRadiatorPreset(
        name="Dayton Audio RSS460-PR", brand="Dayton Audio", model="RSS460-PR",
        sp_cm2=1164.0, fp_hz=14.7, qmp=5.03, mmp_g=500.0, xmax_mm=20.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-rss460-pr.html",
    ),
    "Dayton Audio SS10-PR": PassiveRadiatorPreset(
        name="Dayton Audio SS10-PR", brand="Dayton Audio", model="SS10-PR",
        sp_cm2=346.0, fp_hz=22.0, qmp=3.0, mmp_g=30.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ss10-pr.html",
    ),
    "Dayton Audio SS12-PR": PassiveRadiatorPreset(
        name="Dayton Audio SS12-PR", brand="Dayton Audio", model="SS12-PR",
        sp_cm2=530.0, fp_hz=20.0, qmp=2.8, mmp_g=45.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ss12-pr.html",
    ),
    "Dayton Audio SS15-PR": PassiveRadiatorPreset(
        name="Dayton Audio SS15-PR", brand="Dayton Audio", model="SS15-PR",
        sp_cm2=855.0, fp_hz=18.0, qmp=2.5, mmp_g=70.0, xmax_mm=15.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ss15-pr.html",
    ),
    "Dayton Audio SS18-PR": PassiveRadiatorPreset(
        name="Dayton Audio SS18-PR", brand="Dayton Audio", model="SS18-PR",
        sp_cm2=1210.0, fp_hz=16.0, qmp=2.2, mmp_g=100.0, xmax_mm=18.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ss18-pr.html",
    ),
    "Dayton Audio SS8-PR": PassiveRadiatorPreset(
        name="Dayton Audio SS8-PR", brand="Dayton Audio", model="SS8-PR",
        sp_cm2=214.0, fp_hz=25.0, qmp=3.2, mmp_g=18.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/dayton-audio-ss8-pr.html",
    ),
    "PURIFI PTT10.0PR-NA2-01": PassiveRadiatorPreset(
        name="PURIFI PTT10.0PR-NA2-01", brand="PURIFI", model="PTT10.0PR-NA2-01",
        sp_cm2=330.0, fp_hz=14.0, qmp=8.2, mmp_g=285.0, xmax_mm=25.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt100pr-na2-01.html",
    ),
    "PURIFI PTT4.0PR-NF2-01": PassiveRadiatorPreset(
        name="PURIFI PTT4.0PR-NF2-01", brand="PURIFI", model="PTT4.0PR-NF2-01",
        sp_cm2=54.0, fp_hz=32.0, qmp=4.5, mmp_g=18.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt40pr-nf2-01.html",
    ),
    "PURIFI PTT5.25PR-NA2-01": PassiveRadiatorPreset(
        name="PURIFI PTT5.25PR-NA2-01", brand="PURIFI", model="PTT5.25PR-NA2-01",
        sp_cm2=145.0, fp_hz=27.0, qmp=3.5, mmp_g=16.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt525pr-na2-01.html",
    ),
    "PURIFI PTT5.25PR-NF2-01": PassiveRadiatorPreset(
        name="PURIFI PTT5.25PR-NF2-01", brand="PURIFI", model="PTT5.25PR-NF2-01",
        sp_cm2=92.0, fp_hz=28.0, qmp=4.5, mmp_g=25.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt525pr-nf2-01.html",
    ),
    "PURIFI PTT6.5PR-NA2-03": PassiveRadiatorPreset(
        name="PURIFI PTT6.5PR-NA2-03", brand="PURIFI", model="PTT6.5PR-NA2-03",
        sp_cm2=140.0, fp_hz=19.0, qmp=13.1, mmp_g=45.0, xmax_mm=15.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purify-ptt65pr-na2-03.html",
    ),
    "PURIFI PTT6.5PR-NF2-02": PassiveRadiatorPreset(
        name="PURIFI PTT6.5PR-NF2-02", brand="PURIFI", model="PTT6.5PR-NF2-02",
        sp_cm2=140.0, fp_hz=22.0, qmp=4.5, mmp_g=45.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt65pr-nf2-02.html",
    ),
    "PURIFI PTT8.0PR-NA2-01": PassiveRadiatorPreset(
        name="PURIFI PTT8.0PR-NA2-01", brand="PURIFI", model="PTT8.0PR-NA2-01",
        sp_cm2=214.0, fp_hz=18.0, qmp=4.5, mmp_g=70.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/purifi-ptt80pr-na2-01.html",
    ),
    "Peerless SDS-P830878": PassiveRadiatorPreset(
        name="Peerless SDS-P830878", brand="Peerless", model="SDS-P830878",
        sp_cm2=132.0, fp_hz=31.0, qmp=3.8, mmp_g=13.5, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/peerless-by-tymphany-sds-p830878.html",
    ),
    "RS Speakers PASSIVO 6.5x10": PassiveRadiatorPreset(
        name="RS Speakers PASSIVO 6.5x10", brand="RS Speakers", model="PASSIVO 6.5x10",
        sp_cm2=233.3, fp_hz=35.0, qmp=4.0, mmp_g=91.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/rs-speakers-passivo-65x10.html",
    ),
    "SB Acoustics SB12PAC-00": PassiveRadiatorPreset(
        name="SB Acoustics SB12PAC-00", brand="SB Acoustics", model="SB12PAC-00",
        sp_cm2=50.0, fp_hz=40.0, qmp=4.7, mmp_g=12.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb12pac-00.html",
    ),
    "SB Acoustics SB12PACR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB12PACR-00", brand="SB Acoustics", model="SB12PACR-00",
        sp_cm2=50.0, fp_hz=33.0, qmp=12.4, mmp_g=19.2, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb12pacr-00.html",
    ),
    "SB Acoustics SB12PFC-00": PassiveRadiatorPreset(
        name="SB Acoustics SB12PFC-00", brand="SB Acoustics", model="SB12PFC-00",
        sp_cm2=52.0, fp_hz=40.0, qmp=4.7, mmp_g=12.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb12pfc-00.html",
    ),
    "SB Acoustics SB12PFCR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB12PFCR-00", brand="SB Acoustics", model="SB12PFCR-00",
        sp_cm2=52.0, fp_hz=40.0, qmp=4.7, mmp_g=12.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb12pfcr-00.html",
    ),
    "SB Acoustics SB13PFCR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB13PFCR-00", brand="SB Acoustics", model="SB13PFCR-00",
        sp_cm2=87.0, fp_hz=32.0, qmp=4.5, mmp_g=20.0, xmax_mm=6.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb13pfcr-00.html",
    ),
    "SB Acoustics SB15SFCR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB15SFCR-00", brand="SB Acoustics", model="SB15SFCR-00",
        sp_cm2=84.0, fp_hz=32.0, qmp=4.2, mmp_g=8.5, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb15sfcr-00.html",
    ),
    "SB Acoustics SB16PFCR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB16PFCR-00", brand="SB Acoustics", model="SB16PFCR-00",
        sp_cm2=108.0, fp_hz=29.0, qmp=4.0, mmp_g=11.0, xmax_mm=5.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb16pfcr-00.html",
    ),
    "SB Acoustics SB20PFC-00": PassiveRadiatorPreset(
        name="SB Acoustics SB20PFC-00", brand="SB Acoustics", model="SB20PFC-00",
        sp_cm2=214.0, fp_hz=22.0, qmp=4.0, mmp_g=60.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb20pfc-00.html",
    ),
    "SB Acoustics SB20PFCR-00": PassiveRadiatorPreset(
        name="SB Acoustics SB20PFCR-00", brand="SB Acoustics", model="SB20PFCR-00",
        sp_cm2=178.0, fp_hz=26.0, qmp=3.8, mmp_g=18.0, xmax_mm=6.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb20pfcr-00.html",
    ),
    "SB Acoustics SB23MFCL-0": PassiveRadiatorPreset(
        name="SB Acoustics SB23MFCL-0", brand="SB Acoustics", model="SB23MFCL-0",
        sp_cm2=214.0, fp_hz=18.0, qmp=4.0, mmp_g=80.0, xmax_mm=10.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb23mfcl-0.html",
    ),
    "SB Acoustics SB29NRX-00": PassiveRadiatorPreset(
        name="SB Acoustics SB29NRX-00", brand="SB Acoustics", model="SB29NRX-00",
        sp_cm2=330.0, fp_hz=16.0, qmp=4.0, mmp_g=120.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb29nrx-00.html",
    ),
    "SB Acoustics SB29NRX2-00": PassiveRadiatorPreset(
        name="SB Acoustics SB29NRX2-00", brand="SB Acoustics", model="SB29NRX2-00",
        sp_cm2=330.0, fp_hz=16.0, qmp=4.0, mmp_g=120.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb29nrx2-00.html",
    ),
    "SB Acoustics SB34NRX-00": PassiveRadiatorPreset(
        name="SB Acoustics SB34NRX-00", brand="SB Acoustics", model="SB34NRX-00",
        sp_cm2=470.0, fp_hz=14.0, qmp=4.0, mmp_g=180.0, xmax_mm=14.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb34nrx-00.html",
    ),
    "SB Acoustics SB34NRX2-00": PassiveRadiatorPreset(
        name="SB Acoustics SB34NRX2-00", brand="SB Acoustics", model="SB34NRX2-00",
        sp_cm2=470.0, fp_hz=14.0, qmp=8.62, mmp_g=294.0, xmax_mm=14.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sb34nrx2-00.html",
    ),
    "SB Acoustics SW26DAC-00": PassiveRadiatorPreset(
        name="SB Acoustics SW26DAC-00", brand="SB Acoustics", model="SW26DAC-00",
        sp_cm2=330.0, fp_hz=16.0, qmp=4.0, mmp_g=110.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sw26dac-00.html",
    ),
    "SB Acoustics SW26DBAC-00": PassiveRadiatorPreset(
        name="SB Acoustics SW26DBAC-00", brand="SB Acoustics", model="SW26DBAC-00",
        sp_cm2=330.0, fp_hz=16.0, qmp=4.0, mmp_g=110.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/sb-acoustics-sw26dbac-00.html",
    ),
    "SEAS SL26R - XM003": PassiveRadiatorPreset(
        name="SEAS SL26R - XM003", brand="SEAS", model="SL26R - XM003",
        sp_cm2=330.0, fp_hz=15.0, qmp=4.8, mmp_g=105.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/seas-sl26r.html",
    ),
    "SEAS SP18R - H9944": PassiveRadiatorPreset(
        name="SEAS SP18R - H9944", brand="SEAS", model="SP18R - H9944",
        sp_cm2=140.0, fp_hz=25.0, qmp=4.5, mmp_g=35.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/seas-sp18r.html",
    ),
    "SEAS SP22R - H9945": PassiveRadiatorPreset(
        name="SEAS SP22R - H9945", brand="SEAS", model="SP22R - H9945",
        sp_cm2=214.0, fp_hz=20.0, qmp=4.5, mmp_g=60.0, xmax_mm=8.0,
        source="SoundImports", url="https://www.soundimports.eu/it/seas-sp22r.html",
    ),
    "SEAS SP26R - H9946": PassiveRadiatorPreset(
        name="SEAS SP26R - H9946", brand="SEAS", model="SP26R - H9946",
        sp_cm2=330.0, fp_hz=15.0, qmp=4.8, mmp_g=105.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/seas-sp26r.html",
    ),
    "Scan-Speak 26W/0-00-00": PassiveRadiatorPreset(
        name="Scan-Speak 26W/0-00-00", brand="Scan-Speak", model="26W/0-00-00",
        sp_cm2=330.0, fp_hz=16.0, qmp=4.2, mmp_g=110.0, xmax_mm=12.0,
        source="SoundImports", url="https://www.soundimports.eu/it/scan-speak-26w-0-00-00.html",
    ),
    "Scan-Speak 30W/0-00-00": PassiveRadiatorPreset(
        name="Scan-Speak 30W/0-00-00", brand="Scan-Speak", model="30W/0-00-00",
        sp_cm2=480.0, fp_hz=14.0, qmp=4.2, mmp_g=160.0, xmax_mm=14.0,
        source="SoundImports", url="https://www.soundimports.eu/it/scan-speak-30w-0-00-00.html",
    ),
}


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


_EXTERNAL_MANUFACTURER_ALIASES = {
    "18sound": "Eighteen Sound",
    "eighteensound": "Eighteen Sound",
    "eminence": "Eminence",
    "eminencespeaker": "Eminence",
    "eminencespeakers": "Eminence",
    "eminencespeakersllc": "Eminence",
    "faneinternational": "Fane",
}
_EXTERNAL_MANUFACTURER_PREFIXES = {
    "Eminence": (
        "Eminence Speakers, LLC",
        "Eminence Speakers",
        "Eminence Speaker",
        "Eminence",
    ),
}


def _external_catalog_manufacturer(brand: str) -> str:
    """Return one display/deduplication name for known brand aliases."""
    raw = " ".join(str(brand).split()).strip()
    compact = re.sub(r"[^a-z0-9]+", "", raw.casefold())
    return _EXTERNAL_MANUFACTURER_ALIASES.get(compact, raw)


def _external_catalog_identity_model(record: dict, fallback: str = "") -> str:
    """Return the model/MPN text that manual catalog edits may override."""
    override = str(record.get("part_number_override") or "").strip()
    if override:
        return override
    # Backward compatibility for rows saved before part_number_override was
    # introduced: Catalog Maintenance already stored the edited value here.
    if str(record.get("source") or "") == "Manual catalog maintenance":
        manual_mpn = str(record.get("matched_mpn") or "").strip()
        if manual_mpn:
            return manual_mpn
    return str(
        record.get("model")
        or record.get("matched_mpn")
        or fallback
    ).strip()


def _external_catalog_model_code(brand: str, model: str) -> str:
    """Extract a stable manufacturer part number from decorated model titles."""
    brand_key = re.sub(r"[^a-z0-9]+", "", brand.casefold())
    if brand_key != "sbacoustics":
        return ""
    codes = re.findall(
        r"(?<![a-z0-9])"
        r"((?:sb|sw|mw|mr|wo)[a-z0-9]*(?:-[a-z0-9]+)+)"
        r"(?![a-z0-9])",
        model,
        flags=re.IGNORECASE,
    )
    return re.sub(r"-rev-\d+$", "", codes[-1], flags=re.IGNORECASE) if codes else ""


_BEYMA_CATALOG_TITLE = re.compile(
    r"^loudspeaker\s+(.+?)\s+\d+(?:[.,]\d+)?\s*oh(?:ms?)?$",
    flags=re.IGNORECASE,
)


def _beyma_catalog_part_number(brand: str, model: str) -> str:
    """Extract Beyma's code from its size/title/impedance catalog labels."""
    if re.sub(r"[^a-z0-9]+", "", brand.casefold()) != "beyma":
        return ""
    candidate = " ".join(str(model).split()).strip()
    # PDF download suffixes and publication years are metadata, not MPN text.
    candidate = re.sub(r"\.(?:ai|pdf)$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+(?:19|20)\d{2}$", "", candidate)
    match = _BEYMA_CATALOG_TITLE.match(candidate)
    if not match:
        # Bare scraped model codes can still be cleaned here; decorated
        # titles must continue through the generic title parser below.
        return candidate if candidate and " " not in candidate else ""
    code = re.sub(r"[\"″”\s]+", "", match.group(1))
    return code.strip(" -–—/,")


_MODEL_SIZE_VALUE = r"\d+(?:[.,]\d+|-\d+/\d+|/\d+)?"
_MODEL_LEADING_SIZE = re.compile(
    rf"^{_MODEL_SIZE_VALUE}\s*(?:[\"″”]|in(?:ch(?:es)?)?\b|mm\b)\s*",
    flags=re.IGNORECASE,
)
_MODEL_DESCRIPTION_START = re.compile(
    r"\s+(?:"
    rf"{_MODEL_SIZE_VALUE}\s*(?:[\"″”]|in(?:ch(?:es)?)?\b|mm\b)|"
    r"(?:subwoofer|woofer|midwoofer|midrange|tweeter|"
    r"full[- ]range|compression driver|coaxial(?: driver)?|"
    r"speaker(?: driver)?|loudspeaker|haut-parleur|large[- ]bande)\b|"
    r"\d+(?:[.,]\d+)?\s*(?:watts?|w)\b"
    r")",
    flags=re.IGNORECASE,
)
_MODEL_SERIES_SUFFIX = re.compile(
    r"\s+[a-z0-9-]+\s+series$",
    flags=re.IGNORECASE,
)
_MODEL_CODE_TOKEN = re.compile(r"\b[a-z0-9][a-z0-9._/-]*\b", re.IGNORECASE)
_GENERIC_MODEL_LABEL = re.compile(
    r"^(?:subwoofer|woofer|midwoofer|midrange|tweeter|full[- ]range|"
    r"compression driver|coaxial(?: driver)?|speaker(?: driver)?|"
    r"loudspeaker|haut-parleur|large[- ]bande|medio grave)$",
    flags=re.IGNORECASE,
)

_CIARE_IMPEDANCE_SUFFIX = re.compile(
    r"(?:\(\s*\d+(?:[.,]\d+)?\s*(?:oh(?:ms?)?|ω)\s*\)|"
    r"-\s*\d{1,2}(?:\s*\+\s*\d{1,2})?)$",
    flags=re.IGNORECASE,
)


def _ciare_catalog_part_number(brand: str, model: str) -> str:
    """Strip retailer/official impedance suffixes from a Ciare model code."""
    if re.sub(r"[^a-z0-9]+", "", brand.casefold()) != "ciare":
        return ""
    candidate = " ".join(str(model).split()).strip()
    return _CIARE_IMPEDANCE_SUFFIX.sub("", candidate).strip(" -")


def _external_catalog_part_number(brand: str, model: str) -> str:
    """Return a conservative manufacturer part number for runtime display.

    Retailer APIs sometimes put the complete product title in ``model``.  A
    strong description marker is required before trimming, so genuine
    multi-token codes such as ``GZRW 250-D2 FLAT`` remain untouched.
    """
    raw = " ".join(str(model).split()).strip()
    if not raw:
        return ""
    manufacturer = _external_catalog_manufacturer(brand)
    beyma_code = _beyma_catalog_part_number(manufacturer, raw)
    if beyma_code:
        return beyma_code
    model_code = _external_catalog_model_code(manufacturer, raw)
    if model_code:
        return model_code
    candidate = raw
    prefixes = _EXTERNAL_MANUFACTURER_PREFIXES.get(
        manufacturer, (manufacturer,)
    )
    for prefix in prefixes:
        without_prefix = re.sub(
            rf"^{re.escape(prefix)}\s+",
            "",
            candidate,
            count=1,
            flags=re.IGNORECASE,
        )
        if without_prefix != candidate:
            candidate = without_prefix.strip()
            break
    leading_size = _MODEL_LEADING_SIZE.match(candidate)
    candidate = _MODEL_LEADING_SIZE.sub("", candidate, count=1).strip()
    marker = _MODEL_DESCRIPTION_START.search(candidate)
    if marker:
        trimmed = candidate[:marker.start()].strip(" -–—/,")
        trimmed = _MODEL_SERIES_SUFFIX.sub("", trimmed).strip()
        # Some manufacturer titles start with only a transducer category,
        # followed by size and the real family/specification.  Returning that
        # category as an MPN would collapse unrelated products (for example
        # Bomber's WOOFER and MEDIO GRAVE ranges), so keep the complete title.
        if not _GENERIC_MODEL_LABEL.fullmatch(trimmed):
            candidate = trimmed
    if leading_size and len(candidate.split()) > 1:
        code_tokens = [
            token
            for token in _MODEL_CODE_TOKEN.findall(candidate)
            if (
                any(character.isalpha() for character in token)
                and any(character.isdigit() for character in token)
            )
            or (token.isdigit() and len(token) >= 4)
        ]
        if code_tokens:
            candidate = code_tokens[0]
    ciare_code = _ciare_catalog_part_number(manufacturer, candidate)
    return ciare_code or candidate or raw


def _external_catalog_identity(
    brand: str,
    model: str,
    driver: DriverTS,
    impedance_text: str = "",
) -> tuple[str, str, str]:
    """Return a tolerant identity for duplicate web/retailer listings.

    Retailers frequently omit impedance, inch marks or generic words from the
    model title.  The electrical resistance remains in the key so real 4/8 Ω
    variants are not collapsed accidentally.
    """
    manufacturer = _external_catalog_manufacturer(brand)
    brand_key = manufacturer.casefold()
    if re.sub(r"[^a-z0-9]+", "", manufacturer.casefold()) == "ciare":
        impedance_source = f"{model} {impedance_text}"
        explicit_impedance = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:oh(?:ms?)?|ω)\b",
            impedance_source,
            flags=re.IGNORECASE,
        )
        suffix_impedance = re.search(
            r"-(\d{1,2})(?:\s*\+\s*\1)?(?=\s|$)",
            str(impedance_text),
            flags=re.IGNORECASE,
        )
        if explicit_impedance:
            nominal_ohm = f"{float(explicit_impedance.group(1)):g}"
        elif suffix_impedance:
            nominal_ohm = f"{float(suffix_impedance.group(1)):g}"
        else:
            nominal_ohm = "8" if float(driver.re_ohm) >= 5.0 else "4"
        part_number = _ciare_catalog_part_number(manufacturer, model) or model
        clean_code = re.sub(r"[^a-z0-9]+", "", part_number.casefold())
        return brand_key, clean_code, nominal_ohm
    model_code = _external_catalog_model_code(manufacturer, model)
    if model_code:
        # SB Acoustics product pages decorate the actual part number with
        # nominal size, SATORI series and cone material. The final numeric
        # segment is impedance, including suffixes such as ``-4-COAX``.
        code_impedances = re.findall(r"-(\d{1,2})(?=-|$)", model_code)
        if code_impedances:
            clean_code = re.sub(r"[^a-z0-9]+", "", model_code.casefold())
            return brand_key, clean_code, code_impedances[-1]

    clean = model.casefold().replace("″", '"').replace("–", "-").replace("—", "-")
    impedance_source = f"{model} {impedance_text}"
    impedance = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:oh(?:ms?)?|ω)\b",
        impedance_source,
        flags=re.IGNORECASE,
    )
    if impedance:
        nominal_ohm = f"{float(impedance.group(1)):g}"
    else:
        # Re is retained as a fallback when a retailer omitted impedance from
        # the title; map it to the nearest common nominal voice-coil value.
        re_ohm = float(driver.re_ohm)
        nominal_ohm = "8" if re_ohm >= 5.0 else "4"
    clean = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:oh(?:ms?)?|ω)\b", " ", clean
    )
    clean = re.sub(r"\b\d+(?:\.\d+)?\s*(?:in|inch|inches)\b", " ", clean)
    clean = re.sub(r"\b(?:woofer|speaker|driver|loudspeaker)\b", " ", clean)
    clean = re.sub(r"[^a-z0-9]+", "", clean)
    return brand_key, clean, nominal_ohm


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


def _mechanical_dimensions_from_mapping(values: dict | None) -> MechanicalDimensions | None:
    """Parse optional physical dimensions without affecting acoustic fields."""
    if not isinstance(values, dict):
        return None
    def number(key: str) -> float | None:
        value = values.get(key)
        return float(value) if value is not None else None
    holes = values.get("mounting_hole_count")
    return MechanicalDimensions(
        overall_diameter_mm=number("overall_diameter_mm"),
        cutout_diameter_mm=number("cutout_diameter_mm"),
        depth_mm=number("depth_mm"),
        mounting_depth_mm=number("mounting_depth_mm"),
        bolt_circle_mm=number("bolt_circle_mm"),
        mounting_hole_count=int(holes) if holes is not None else None,
        mounting_hole_diameter_mm=number("mounting_hole_diameter_mm"),
        weight_kg=number("weight_kg"),
    )


def _published_specs_from_mapping(values: dict | None) -> dict[str, float] | None:
    """Retain source-backed numeric specifications not yet used by the solver."""
    if not isinstance(values, dict):
        return None
    parsed = {}
    for key, value in values.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            parsed[str(key)] = number
    return parsed or None



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

    cache_path = path.with_suffix(".cache.pickle")
    if cache_path.exists():
        try:
            cache_mtime = cache_path.stat().st_mtime
            prices_mtime = (
                DRIVER_PRICES_PATH.stat().st_mtime
                if DRIVER_PRICES_PATH.exists()
                else 0.0
            )
            if cache_mtime >= path.stat().st_mtime and cache_mtime >= prices_mtime:
                cached = _safe_unpickle_bytes(cache_path.read_bytes())
                if (
                    isinstance(cached, tuple)
                    and len(cached) == 2
                    and isinstance(cached[0], dict)
                    and isinstance(cached[1], dict)
                ):
                    return cached
        except Exception:
            pass

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
    identity_to_name: dict[tuple[str, str, str], str] = {}
    identity_score: dict[tuple[str, str, str], tuple[int, int, float]] = {}
    for item in payload.get("presets", []):
        if (
            (item.get("website_fields") or {}).get("quality_status")
            == "rejected_size_sd_conflict"
        ):
            continue
        base_name = str(item["name"])
        item_brand = _external_catalog_manufacturer(
            str(item.get("brand") or "Other")
        )
        item_model = str(item.get("model") or base_name.removeprefix("LSDB: "))
        identity_model = _external_catalog_identity_model(item, item_model)
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
        item_url = str(item.get("url") or "")
        item_source = str(item.get("source") or default_source)
        part_number = _external_catalog_part_number(item_brand, identity_model)
        enriched_price, enriched_currency, enriched_url = _preset_price(
            name, part_number or item_model, item_brand
        )
        if enriched_price is None and item_price is not None:
            enriched_price, enriched_currency, enriched_url = item_price, item_currency, item_url
        raw_size_in = (
            float(item["size_in"])
            if item.get("size_in") is not None
            else None
        )
        item_info = DriverPresetInfo(
            name=name,
            source=item_source,
            brand=item_brand,
            model=item_model,
            part_number=part_number or item_model,
            size_in=coherent_nominal_size_in(raw_size_in, driver.sd_cm2),
            price=enriched_price if enriched_price is not None else item_price,
            currency=enriched_currency or item_currency,
            kind=str(item.get("kind") or ""),
            url=enriched_url or item_url or str(item.get("url") or ""),
            mechanical=_mechanical_dimensions_from_mapping(item.get("mechanical")),
            published_specs=_published_specs_from_mapping(item.get("published_specs")),
        )
        identity = _external_catalog_identity(
            item_brand,
            part_number or item_model,
            driver,
            impedance_text=item_model,
        )
        source_key = item_source.casefold()
        source_priority = 0
        if (
            dedupe_tag == "MFR"
            and re.sub(r"[^a-z0-9]+", "", item_brand.casefold())
            == "sbacoustics"
        ):
            if "sb acoustics crawler" in source_key:
                source_priority = 2
            elif (
                "retailer" not in source_key
                and "distributor" not in source_key
            ):
                source_priority = 1
        score = (
            source_priority,
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

    try:
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_bytes(pickle.dumps((presets, info), protocol=pickle.HIGHEST_PROTOCOL))
        tmp_path.replace(cache_path)
    except Exception:
        pass

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
def _load_vituixcad_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load the optional, separately generated VituixCAD online database tier."""
    lsdb_presets, _lsdb_info = _load_loudspeaker_database_presets()
    manufacturer_presets, _manufacturer_info = _load_manufacturer_presets()
    return _load_external_presets(
        VITUIXCAD_DATABASE_PATH,
        default_source="VituixCAD online database",
        dedupe_tag="VCD",
        reserved={**lsdb_presets, **manufacturer_presets},
    )


@lru_cache(maxsize=1)
def _load_speakerboxlite_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load the physically validated Speaker Box Lite community tier."""
    lsdb_presets, _lsdb_info = _load_loudspeaker_database_presets()
    manufacturer_presets, _manufacturer_info = _load_manufacturer_presets()
    vituixcad_presets, _vituixcad_info = _load_vituixcad_presets()
    return _load_external_presets(
        SPEAKERBOXLITE_DATABASE_PATH,
        default_source="Speaker Box Lite public database",
        dedupe_tag="SBL",
        reserved={
            **lsdb_presets,
            **manufacturer_presets,
            **vituixcad_presets,
        },
    )


@lru_cache(maxsize=1)
def _load_ztzaudio_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load the validated ZTZ Audio LF ferrite manufacturer tier."""
    lsdb_presets, _lsdb_info = _load_loudspeaker_database_presets()
    manufacturer_presets, _manufacturer_info = _load_manufacturer_presets()
    vituixcad_presets, _vituixcad_info = _load_vituixcad_presets()
    speakerboxlite_presets, _speakerboxlite_info = _load_speakerboxlite_presets()
    return _load_external_presets(
        ZTZ_AUDIO_DATABASE_PATH,
        default_source="ZTZ Audio manufacturer catalog",
        dedupe_tag="ZTZ",
        reserved={
            **lsdb_presets,
            **manufacturer_presets,
            **vituixcad_presets,
            **speakerboxlite_presets,
        },
    )


@lru_cache(maxsize=1)
def _load_firestore_presets(
    client: Any | None = None,
) -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load driver presets dynamically from Google Cloud Firestore.

    Gracefully falls back to cached snapshot or empty if offline/unavailable.
    """
    if client is None and FIRESTORE_PRESETS_CACHE_PATH.exists():
        try:
            cache_age = time.time() - FIRESTORE_PRESETS_CACHE_PATH.stat().st_mtime
            if cache_age < 3600:
                cached = _safe_unpickle_bytes(FIRESTORE_PRESETS_CACHE_PATH.read_bytes())
                if (
                    isinstance(cached, tuple)
                    and len(cached) == 2
                    and isinstance(cached[0], dict)
                    and isinstance(cached[1], dict)
                ):
                    return cached
        except Exception:
            pass

    project_id = (
        os.environ.get("LOAD_FORGE_GCP_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or "civic-radio-502611-i8"
    )
    database_id = (
        os.environ.get("LF_FIRESTORE_CATALOG_RUNTIME_DB")
        or os.environ.get("LOAD_FORGE_FIRESTORE_CATALOG_RUNTIME_DB")
        or os.environ.get("LOAD_FORGE_FIRESTORE_DATABASE")
        or "(default)"
    )
    collection_name = os.environ.get("LOAD_FORGE_FIRESTORE_DRIVERS_COLLECTION", "driver_presets")
    presets: dict[str, DriverTS] = {}
    info: dict[str, DriverPresetInfo] = {}

    raw_items: list[dict[str, Any]] = []
    try:
        if client is None:
            from google.cloud import firestore
            client = firestore.Client(project=project_id, database=database_id)
        for doc in client.collection(collection_name).stream():
            data = doc.to_dict() if hasattr(doc, "to_dict") else doc
            if isinstance(data, dict):
                raw_items.append(data)
    except Exception:
        raw_items = []
        if client is None and FIRESTORE_PRESETS_CACHE_PATH.exists():
            try:
                cached = _safe_unpickle_bytes(FIRESTORE_PRESETS_CACHE_PATH.read_bytes())
                if (
                    isinstance(cached, tuple)
                    and len(cached) == 2
                    and isinstance(cached[0], dict)
                    and isinstance(cached[1], dict)
                ):
                    return cached
            except Exception:
                pass

    for item in raw_items:
        try:
            d = item.get("driver", {})
            if not isinstance(d, dict) or not d.get("fs_hz") or not d.get("re_ohm"):
                continue
            fs = float(d["fs_hz"])
            re = float(d["re_ohm"])
            qms = float(d.get("qms", 5.0))
            qes = float(d.get("qes", 0.4))
            qts = float(d.get("qts", 0.37))
            le_mh = float(d.get("le_mh", 0.0))
            le10k_mh = float(d["le10k_mh"]) if d.get("le10k_mh") is not None else None
            sd_cm2 = float(d.get("sd_cm2", 100.0)) if d.get("sd_cm2") is not None else 100.0
            vas_l = float(d.get("vas_l", 20.0)) if d.get("vas_l") is not None else 20.0
            mms_g = float(d["mms_g"]) if d.get("mms_g") is not None else None
            cms_mm_per_n = float(d["cms_mm_per_n"]) if d.get("cms_mm_per_n") is not None else None
            bl_tm = float(d["bl_tm"]) if d.get("bl_tm") is not None else None
            xmax_mm = float(d["xmax_mm"]) if d.get("xmax_mm") is not None else None
            pe_w = float(d["pe_w"]) if d.get("pe_w") is not None else None

            driver = DriverTS(
                fs_hz=fs,
                vas_l=vas_l,
                qts=qts,
                qms=qms,
                re_ohm=re,
                sd_cm2=sd_cm2,
                le_mh=le_mh,
                le10k_mh=le10k_mh,
                xmax_mm=xmax_mm if xmax_mm is not None else 0.0,
                pe_w=pe_w if pe_w is not None else 0.0,
                mms_g=mms_g,
                cms_mm_per_n=cms_mm_per_n,
                bl_tm=bl_tm,
            )
            brand = str(item.get("brand", "Custom")).strip()
            model = str(item.get("model", "Measured")).strip()
            name = str(item.get("name") or f"Z Bench: {brand} {model}").strip()
            source = str(item.get("source") or "Z Bench Measurement").strip()
            presets[name] = driver
            info[name] = DriverPresetInfo(
                name=name,
                source=source,
                brand=brand,
                model=model,
                part_number=model,
                size_in=coherent_nominal_size_in(None, driver.sd_cm2),
                price=_valid_price(item.get("price")),
                currency=str(item.get("currency") or "EUR"),
                url=str(item.get("url") or ""),
                published_specs=_published_specs_from_mapping(item.get("published_specs")),
            )
        except Exception:
            continue

    if client is None:
        try:
            tmp = FIRESTORE_PRESETS_CACHE_PATH.with_suffix(".tmp")
            tmp.write_bytes(pickle.dumps((presets, info), protocol=pickle.HIGHEST_PROTOCOL))
            tmp.replace(FIRESTORE_PRESETS_CACHE_PATH)
        except Exception:
            pass

    return presets, info


def invalidate_preset_caches() -> None:
    """Clear all LRU caches for driver and passive radiator presets."""
    _external_tiers.cache_clear()
    _load_firestore_presets.cache_clear()
    _load_manufacturer_presets.cache_clear()
    _load_loudspeaker_database_presets.cache_clear()
    _load_vituixcad_presets.cache_clear()
    _load_speakerboxlite_presets.cache_clear()
    _load_ztzaudio_presets.cache_clear()
    try:
        if FIRESTORE_PRESETS_CACHE_PATH.exists():
            FIRESTORE_PRESETS_CACHE_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    driver_preset_names.cache_clear()
    driver_preset_info.cache_clear()
    driver_preset_provenance_category.cache_clear()
    driver_preset_identity.cache_clear()
    driver_preset_preference.cache_clear()
    deduplicate_driver_preset_names.cache_clear()
    all_preset_brands.cache_clear()
    all_preset_price_currencies.cache_clear()
    all_preset_price_values.cache_clear()
    get_driver_preset.cache_clear()


@lru_cache(maxsize=1)
def _external_tiers() -> list[tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]]:
    return [
        _load_loudspeaker_database_presets(),
        _load_manufacturer_presets(),
        _load_firestore_presets(),
        _load_vituixcad_presets(),
        _load_speakerboxlite_presets(),
        _load_ztzaudio_presets(),
    ]


@lru_cache(maxsize=1)
def driver_preset_names() -> list[str]:
    """Return driver preset names in display order."""
    names = list(DRIVER_PRESETS)
    for presets, _info in _external_tiers():
        names.extend(presets)
    return names


def passive_radiator_preset_names() -> list[str]:
    """Return catalogued passive-radiator names in display order."""
    return list(PASSIVE_RADIATOR_PRESETS)


@lru_cache(maxsize=128)
def get_passive_radiator_preset(name: str) -> PassiveRadiatorPreset:
    """Return a passive-radiator mechanical preset by name."""
    try:
        return PASSIVE_RADIATOR_PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown passive-radiator preset: {name}") from exc


@lru_cache(maxsize=32768)
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
            part_number=model,
            size_in=coherent_nominal_size_in(None, DRIVER_PRESETS[name].sd_cm2),
            price=price,
            currency=currency,
            url=url,
        )
    for _presets, info in _external_tiers():
        if name in info:
            return info[name]
    raise ValueError(f"Unknown driver preset: {name}")


@lru_cache(maxsize=32768)
def driver_preset_provenance_category(name: str) -> str:
    """Return a stable, user-facing provenance bucket for one preset.

    Load Forge's curated, crawled and user-supplied rows share one category,
    while Z Bench measurements and the three third-party aggregate databases
    remain independently selectable. Exact source and URL remain available
    through :func:`driver_preset_info`.
    """
    info = driver_preset_info(name)
    source = info.source.strip()
    source_lower = source.casefold()
    if "z bench" in source_lower or "z_bench" in source_lower or "zbench" in source_lower:
        return "Z Bench"
    if source == "Loudspeaker Database":
        return "LSDB"
    if source == "VituixCAD online database":
        return "VituixCAD"
    if source == "Speaker Box Lite public database":
        return "Speaker Box Lite"
    return "Load Forge database"


@lru_cache(maxsize=32768)
def driver_preset_identity(name: str) -> tuple[str, str, str]:
    """Return one physical brand/model/impedance identity across catalogs."""
    try:
        info = driver_preset_info(name)
        ts = get_driver_preset(name)
        return _external_catalog_identity(
            info.brand or "Other",
            info.part_number or info.model or name,
            ts,
            impedance_text=info.model,
        )
    except Exception:
        normalized = re.sub(r"[^a-z0-9]+", "", name.casefold())
        return "unknown", normalized, ""


@lru_cache(maxsize=32768)
def driver_preset_preference(name: str) -> tuple[int, int, float, str]:
    """Prefer Load Forge provenance, then an available lower price."""
    try:
        info = driver_preset_info(name)
        category = driver_preset_provenance_category(name)
        price = float(info.price) if info.price is not None else float("inf")
    except Exception:
        category = "Other"
        price = float("inf")
    source_priority = {
        "Load Forge database": 0,
        "LSDB": 1,
        "VituixCAD": 2,
        "Speaker Box Lite": 3,
    }.get(category, 4)
    return (
        source_priority,
        0 if math.isfinite(price) else 1,
        price,
        name.casefold(),
    )


@lru_cache(maxsize=256)
def deduplicate_driver_preset_names(
    preset_names: tuple[str, ...],
) -> tuple[tuple[str, ...], int]:
    """Choose one preferred catalog record for each physical driver."""
    chosen: dict[tuple[str, str, str], str] = {}
    for name in preset_names:
        identity = driver_preset_identity(name)
        previous = chosen.get(identity)
        if (
            previous is None
            or driver_preset_preference(name) < driver_preset_preference(previous)
        ):
            chosen[identity] = name
    unique_names = tuple(chosen.values())
    return unique_names, len(preset_names) - len(unique_names)


@lru_cache(maxsize=1)
def all_preset_brands() -> tuple[str, ...]:
    """Return all unique brands across catalogs."""
    brands = {_built_in_preset_brand(name) for name in DRIVER_PRESETS}
    for _presets, info in _external_tiers():
        for item in info.values():
            if item.brand and item.brand.strip():
                brands.add(item.brand.strip())
    return tuple(sorted(brands, key=str.casefold))


@lru_cache(maxsize=1)
def all_preset_price_currencies() -> tuple[str, ...]:
    """Return all distinct non-empty currencies across driver presets with prices."""
    currencies = set()
    for name in DRIVER_PRESETS:
        brand = _built_in_preset_brand(name)
        model = name.removeprefix(brand).strip() if brand != "Other" else name
        price, currency, _url = _preset_price(name, model, brand)
        if price is not None and currency:
            currencies.add(currency)
    for _presets, info in _external_tiers():
        for item in info.values():
            if item.price is not None and item.currency and item.currency.strip():
                currencies.add(item.currency.strip())
    return tuple(sorted(currencies))


@lru_cache(maxsize=32)
def all_preset_price_values(
    currency: str = "",
    rates_tuple: tuple[tuple[str, float], ...] = (),
) -> tuple[float, ...]:
    """Return sorted/filtered price floats across all presets in requested currency."""
    rates = dict(rates_tuple) if rates_tuple else None
    values = []
    for name in DRIVER_PRESETS:
        brand = _built_in_preset_brand(name)
        model = name.removeprefix(brand).strip() if brand != "Other" else name
        price, curr, _url = _preset_price(name, model, brand)
        if price is None or not math.isfinite(float(price)):
            continue
        if not currency or curr == currency:
            values.append(float(price))
        else:
            converted = convert_price(price, curr, currency, rates)
            if converted is not None and math.isfinite(float(converted)):
                values.append(float(converted))
    for _presets, info in _external_tiers():
        for item in info.values():
            if item.price is None or not math.isfinite(float(item.price)):
                continue
            if not currency or item.currency == currency:
                values.append(float(item.price))
            else:
                converted = convert_price(item.price, item.currency, currency, rates)
                if converted is not None and math.isfinite(float(converted)):
                    values.append(float(converted))
    return tuple(values)


@lru_cache(maxsize=32768)
def get_driver_preset(name: str) -> DriverTS:
    """Return a driver preset by name."""
    if name in DRIVER_PRESETS:
        return DRIVER_PRESETS[name]
    for presets, _info in _external_tiers():
        if name in presets:
            return presets[name]
    raise ValueError(f"Unknown driver preset: {name}")
