"""Bass Match preview in Box Design: similar drivers in the visitor's own box.

Shown to everyone (guests included) right under the Box Design analysis: the
~25 catalog drivers most similar to the current one (nominal size, Fs, Qts,
Vas) are ranked with the same load type and total volume, and the best five
are listed with an "Open" action. It is the free taste of Bass Match; the full
search (whole catalog, filters, optimizer) stays behind sign-in.

Public API: ``render_alternatives(driver_name, load_type, box, voltage_v)``,
plus the pure helpers ``box_total_volume_l`` and ``similar_driver_names``.
Ranking uses ``ranking.rank_preset_row`` without optimizer goals (suggested
alignment at the given volume), ~1 ms per driver, cached per
(driver, load, volume, voltage). See docs/ui/alternatives.md.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any

import streamlit as st

import acoustics as _acoustics
import driver_plausibility as _plausibility
import ranking as _ranking

from . import account as _account
from . import catalog as _catalog
from . import constants as _constants
from . import runtime as _runtime
from . import state as _state
from . import usage as _usage

POOL_SIZE = 25
SHOWN = 5
_SOURCE_PREFIX = re.compile(r"^[A-Z]{2,6}:\s*")


def box_total_volume_l(load_type: str, box: Any) -> float | None:
    """Total internal volume of the current design (same rule as the summary strip)."""
    if load_type == "Infinite baffle" or box is None:
        return None
    if load_type == "Bandpass 4th order":
        return float(box.vs_l + box.vp_l)
    if load_type == "Bandpass 6th order":
        return float(box.vr_l + box.vp_l)
    if load_type == "Bandpass 8th order":
        return float(box.v1_l + box.v2_l + box.v3_l)
    if load_type == "DCCAV":
        return float(box.vh_l + box.vl_l)
    return float(box.vb_l)


_OHM_WORD = re.compile(r"(?<=\d)\s*(ohms?|Ω)\b|\bohms?\b", re.IGNORECASE)


def _identity(name: str) -> str:
    """The same unit listed by several sources collapses to one key.

    "FRS 7 - 8" and "FRS 7 - 8 Ohm" are one product; 4 Ω and 8 Ω stay distinct.
    """
    return re.sub(r"[^a-z0-9]", "", _OHM_WORD.sub("", _SOURCE_PREFIX.sub("", name)).casefold())


def _log_gap(a: float | None, b: float | None, missing: float = 0.5) -> float:
    if not a or not b or a <= 0 or b <= 0:
        return missing
    return abs(math.log(a / b))


def similar_driver_names(
    current: str,
    features: dict[str, tuple[float | None, float, float, float, float]],
    *,
    limit: int = POOL_SIZE,
    needs_xmax: bool = True,
) -> list[str]:
    """Closest drivers to ``current`` by size, Fs, Qts and Vas (pure).

    ``features`` maps name → (size_in, fs_hz, qts, vas_l, xmax_mm). Duplicates
    of one unit from different sources, and the current driver itself, are
    skipped; vented/bandpass loads need a published Xmax.
    """
    ref = features.get(current)
    if ref is None:
        return []
    size, fs, qts, vas, _ = ref
    seen = {_identity(current)}
    scored = []
    for name, (c_size, c_fs, c_qts, c_vas, c_xmax) in features.items():
        if needs_xmax and not (c_xmax and c_xmax > 0):
            continue
        distance = (
            2.0 * _log_gap(c_size, size)
            + _log_gap(c_fs, fs) + _log_gap(c_qts, qts) + 0.5 * _log_gap(c_vas, vas)
        )
        scored.append((distance, name))
    scored.sort()
    picked = []
    for _, name in scored:
        key = _identity(name)
        if key in seen:
            continue
        seen.add(key)
        picked.append(name)
        if len(picked) >= limit:
            break
    return picked


def driver_issues(name: str) -> list[str]:
    """Plausibility problems of one catalog record (see driver_plausibility)."""
    try:
        ts = _acoustics.get_driver_preset(name)
    except Exception:
        return []
    return _plausibility.plausibility_issues(name, qts=ts.qts, le_mh=ts.le_mh, sd_cm2=ts.sd_cm2)


@lru_cache(maxsize=2)
def _catalog_features(names: tuple[str, ...]) -> dict[str, tuple]:
    """Size/Fs/Qts/Vas/Xmax per trustworthy record; implausible ones are never suggested."""
    features = {}
    for name in names:
        try:
            ts = _acoustics.get_driver_preset(name)
            info = _acoustics.driver_preset_info(name)
        except Exception:
            continue
        if _plausibility.plausibility_issues(name, qts=ts.qts, le_mh=ts.le_mh, sd_cm2=ts.sd_cm2):
            continue
        features[name] = (info.size_in, ts.fs_hz, ts.qts, ts.vas_l, ts.xmax_mm)
    return features


@st.cache_data(show_spinner=False, max_entries=512, ttl=24 * 3600)
def _ranked_alternatives(pool: tuple[str, ...], load_type: str, volume_l: float, voltage_v: float) -> list[dict]:
    rows = [
        row for row in (
            _ranking.rank_preset_row(name, load_type, volume_l, voltage_v, 10.0, 500.0, 160)
            for name in pool
        ) if row
    ]
    return _ranking.sort_ranked_rows(rows)[:SHOWN]


_ON_TOP_KEY = "_lf_alternatives_on_top"


def wants_on_top() -> bool:
    """True after a ``?compare=1`` entry (portal "Compare with Bass Match"), until dismissed."""
    if str(st.query_params.get("compare", "")) == "1":
        st.query_params.pop("compare", None)
        st.session_state[_ON_TOP_KEY] = True
    return bool(st.session_state.get(_ON_TOP_KEY))


def _dismiss_on_top() -> None:
    st.session_state[_ON_TOP_KEY] = False


def _open_alternative(row: dict, load_type: str, voltage_v: float) -> None:
    _usage.track("alternative_opened", {"driver": row.get("Driver", ""), "load_type": load_type})
    # Same path as Bass Match's "Open in Box Design" (applied on the next run).
    st.session_state["batch_pending_result"] = {"row": row, "load_type": load_type, "voltage_v": voltage_v}


def _fmt(value: Any, digits: int, unit: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "–"
    return f"{number:.{digits}f} {unit}" if math.isfinite(number) else "–"


def render_alternatives(driver_name: str, load_type: str, box: Any, voltage_v: float, *, on_top: bool = False) -> None:
    """Five similar drivers in this box; never raises into the Box Design page.

    ``on_top``: rendered above the chart for a portal compare entry, with a
    "Hide" action that moves it back under the analysis.
    """
    volume_l = box_total_volume_l(load_type, box)
    if not volume_l or not driver_name:
        return
    issues = driver_issues(driver_name)
    if issues:
        # A comparison built on wrong data would mislead: say so instead.
        _usage.track("alternatives_shown", {"driver": driver_name, "load_type": load_type, "unreliable": True},
                     once=f"{driver_name}|{load_type}")
        with st.container(border=True, key="lf_alternatives"):
            st.warning(
                f"**The catalog parameters of {driver_name} look unreliable** — "
                + "; ".join(issues)
                + ". This design and any comparison built on it would be misleading. "
                "Check the manufacturer's datasheet, or pick a single driver from the library."
            )
            if on_top:
                st.button("Hide", key="lf_alt_hide", on_click=_dismiss_on_top)
        return
    try:
        names = tuple(_catalog._available_driver_preset_names())
        features = dict(_catalog_features(names))
        if driver_name not in features:
            # The current (trustworthy) driver may be a user edit or outside the cached set.
            ts = _acoustics.get_driver_preset(driver_name)
            info = _acoustics.driver_preset_info(driver_name)
            features[driver_name] = (info.size_in, ts.fs_hz, ts.qts, ts.vas_l, ts.xmax_mm)
        pool = similar_driver_names(driver_name, features, needs_xmax=load_type not in ("Sealed",))
        rows = _ranked_alternatives(tuple(pool), load_type, round(volume_l, 1), round(float(voltage_v), 2))
    except Exception:
        _runtime.logger.exception("Alternatives preview failed")
        return
    if not rows:
        return
    _usage.track("alternatives_shown", {"driver": driver_name, "load_type": load_type, "on_top": on_top},
                 once=f"{driver_name}|{load_type}")
    label = _constants.load_type_label(load_type)
    with st.container(border=True, key="lf_alternatives"):
        if on_top:
            c_title, c_hide = st.columns([6, 1], vertical_alignment="center")
            c_title.markdown(f"**Bass Match · drivers similar to {driver_name} in this {volume_l:.0f} L {label}**")
            c_hide.button("Hide", key="lf_alt_hide", width="stretch", on_click=_dismiss_on_top)
        else:
            st.markdown(f"**Similar drivers in this {volume_l:.0f} L {label}** · Bass Match preview")
        for index, row in enumerate(rows):
            c_name, c_f3, c_spl, c_exc, c_price, c_open = st.columns(
                [3.2, 1, 1, 1.1, 1.1, 1], vertical_alignment="center")
            c_name.markdown(str(row.get("Driver", "")))
            c_f3.markdown(f"F3 **{_fmt(row.get('F3 Hz'), 1, 'Hz')}**")
            c_spl.markdown(_fmt(row.get("Peak dB"), 1, "dB"))
            c_exc.markdown(_fmt(row.get("Max excursion mm"), 1, "mm"))
            price = row.get("Price")
            c_price.markdown(
                f"{float(price):.0f} {row.get('Currency', '')}"
                if isinstance(price, (int, float)) and math.isfinite(float(price)) else "–")
            c_open.button("Open", key=f"lf_alt_open_{index}", width="stretch",
                          on_click=_open_alternative, args=(row, load_type, float(voltage_v)))
        total = len(_catalog._available_driver_preset_names())
        if _runtime._GUEST:
            st.button(f"Search all {total:,} drivers with filters — sign in free", key="lf_alt_full_search",
                      type="primary", on_click=_account.request_sign_in, args=("bass_match",))
        else:
            st.button("Open the full Bass Match", key="lf_alt_full_search",
                      on_click=_state._select_workspace, args=("Bass Match",))
