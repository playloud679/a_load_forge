"""Bass Match driver search, ranking workers, results and candidate pool."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
import atexit
import multiprocessing
import os
import time
import uuid

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import acoustics as _acoustics
import engine as _engine
import presets as _presets
import pricing as _pricing
import ranking as _ranking

from . import account as _account
from . import analysis as _analysis
from . import catalog as _catalog
from . import constants as _constants
from . import optimizer as _optimizer
from . import projects as _projects
from . import runtime as _runtime
from . import state as _state


def _apply_alignment(alignment: _acoustics.DccavAlignment):
    st.session_state["box_vh_l"] = float(alignment.vh_l)
    st.session_state["box_fh_hz"] = float(alignment.fh_hz)
    st.session_state["box_vl_l"] = float(alignment.vl_l)
    st.session_state["box_fl_hz"] = float(alignment.fl_hz)

def _apply_reflex_alignment(alignment: _acoustics.ReflexAlignment):
    st.session_state["reflex_vb_l"] = float(alignment.vb_l)
    st.session_state["reflex_fb_hz"] = float(alignment.fb_hz)

def _apply_sealed_alignment(alignment: _acoustics.SealedAlignment):
    st.session_state["sealed_vb_l"] = float(alignment.vb_l)

def _apply_bandpass4_alignment(alignment: _acoustics.Bandpass4Alignment):
    st.session_state["bandpass4_vs_l"] = float(alignment.vs_l)
    st.session_state["bandpass4_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass4_fp_hz"] = float(alignment.fp_hz)

def _apply_bandpass6_alignment(alignment: _acoustics.Bandpass6Alignment):
    st.session_state["bandpass6_vr_l"] = float(alignment.vr_l)
    st.session_state["bandpass6_fr_hz"] = float(alignment.fr_hz)
    st.session_state["bandpass6_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass6_fp_hz"] = float(alignment.fp_hz)

def _apply_bandpass8_alignment(alignment: _acoustics.Bandpass8Alignment) -> None:
    st.session_state["bp8_v1_l"] = float(alignment.v1_l)
    st.session_state["bp8_f1_hz"] = float(alignment.f1_hz)
    st.session_state["bp8_v2_l"] = float(alignment.v2_l)
    st.session_state["bp8_f2_hz"] = float(alignment.f2_hz)
    st.session_state["bp8_v3_l"] = float(alignment.v3_l)
    st.session_state["bp8_f3_hz"] = float(alignment.f3_hz)

def _auto_align_current_driver():
    if not _state._box_strategy_is_auto():
        return
    try:
        driver = _state._driver_from_state()
        _optimizer._apply_suggested_box_for(driver)
        _mark_auto_alignment_synced(driver)
    except Exception:
        pass

def _optimizer_goals_signature() -> tuple:
    if not _optimizer._alignment_uses_optimizer():
        return ()
    goals = _optimizer._optimizer_goals_from_state()
    return (
        "optimized",
        goals.objective,
        goals.max_total_volume_l,
        goals.target_f3_hz,
        goals.max_ripple_db,
        goals.max_excursion_ratio,
        goals.max_group_delay_ms,
        round(float(st.session_state.get("sim_voltage", 2.83)), 3),
    )

def _auto_alignment_signature(driver: _acoustics.DriverTS | None = None) -> tuple:
    driver = driver or _state._driver_from_state()
    return (
        st.session_state.get("load_type", "DCCAV"),
        st.session_state.get("reflex_resonator_type", _constants._RESONATOR_PORT),
        *_optimizer_goals_signature(),
        round(float(driver.fs_hz), 6),
        round(float(driver.vas_l), 6),
        round(float(driver.qts), 6),
        round(float(driver.qms), 6),
        round(float(driver.re_ohm), 6),
        round(float(driver.sd_cm2), 6),
        round(float(driver.le_mh), 6),
        round(float(driver.xmax_mm), 6),
        round(float(driver.pe_w), 6),
        round(float(driver.mms_g or 0.0), 6),
        round(float(driver.cms_mm_per_n or 0.0), 6),
        round(float(driver.bl_tm or 0.0), 6),
        bool(driver.panel_air_load),
        round(float(driver.panel_coupling), 6),
    )

def _mark_auto_alignment_synced(driver: _acoustics.DriverTS | None = None):
    try:
        st.session_state["_auto_align_signature"] = _auto_alignment_signature(driver)
    except Exception:
        pass

def _sync_auto_alignment_if_needed():
    if not _state._box_strategy_is_auto():
        return
    try:
        driver = _state._driver_from_state()
        signature = _auto_alignment_signature(driver)
        if st.session_state.get("_auto_align_signature") == signature:
            return
        _optimizer._apply_suggested_box_for(driver)
        st.session_state["_auto_align_signature"] = signature
    except Exception:
        pass

def _initialize_alignment_defaults() -> None:
    """Seed enclosure fields once instead of recomputing five alignments per click."""
    default_groups = (
        (
            ("box_vh_l", "vh_l"), ("box_fh_hz", "fh_hz"),
            ("box_vl_l", "vl_l"), ("box_fl_hz", "fl_hz"),
            _acoustics.suggest_alignment,
            _acoustics.DccavAlignment(3.1, 162.0, 6.25, 62.0, 51.5),
        ),
        (
            ("reflex_vb_l", "vb_l"), ("reflex_fb_hz", "fb_hz"),
            _acoustics.suggest_reflex_alignment,
            _acoustics.ReflexAlignment(11.52, 48.14),
        ),
        (
            ("bandpass4_vs_l", "vs_l"), ("bandpass4_vp_l", "vp_l"),
            ("bandpass4_fp_hz", "fp_hz"),
            _acoustics.suggest_bandpass4_alignment,
            _acoustics.Bandpass4Alignment(4.09, 11.52, 94.0),
        ),
        (
            ("bandpass6_vr_l", "vr_l"), ("bandpass6_fr_hz", "fr_hz"),
            ("bandpass6_vp_l", "vp_l"), ("bandpass6_fp_hz", "fp_hz"),
            _acoustics.suggest_bandpass6_alignment,
            _acoustics.Bandpass6Alignment(4.09, 60.0, 11.52, 94.0),
        ),
        (
            ("sealed_vb_l", "vb_l"),
            _acoustics.suggest_sealed_alignment,
            _acoustics.SealedAlignment(11.52, 68.1, 0.512),
        ),
    )
    if all(
        state_key in st.session_state
        for group in default_groups
        for item in group[:-2]
        for state_key in (item[0],)
    ):
        return
    try:
        driver = _state._driver_from_state()
    except Exception:
        driver = None
    for group in default_groups:
        fields, suggest, fallback = group[:-2], group[-2], group[-1]
        if all(state_key in st.session_state for state_key, _attr in fields):
            continue
        try:
            alignment = suggest(driver) if driver is not None else fallback
        except Exception:
            alignment = fallback
        for state_key, attr in fields:
            _state._default(state_key, float(getattr(alignment, attr)))

def _step5(key, default, calc_val=None):
    val = st.session_state.get(key)
    if val is not None:
        try:
            val = float(val)
            if val == 0.0 and calc_val is not None:
                val = float(calc_val)
            if val > 0:
                s_default = str(default)
                decimals = len(s_default.split('.')[1]) if '.' in s_default else 0
                step_val = round(val * 0.05, decimals)
                if isinstance(default, int):
                    return max(default, int(step_val))
                return max(default, step_val)
        except (ValueError, TypeError):
            pass
    return default

def _on_driver_param_change():
    # Keep the source identity for the administrator's explicit catalog-save
    # action even though edited parameters make this a Custom design.
    current_preset = str(st.session_state.get("driver_preset_name", "Custom"))
    if current_preset != "Custom":
        st.session_state["_admin_catalog_source_preset"] = current_preset
    st.session_state["driver_preset_name"] = "Custom"
    _auto_align_current_driver()

def _on_load_type_change():
    _auto_align_current_driver()

def _on_pr_preset_change():
    """Apply a catalogued passive radiator to the editable PR fields."""
    name = str(st.session_state.get("pr_preset_name", "Custom"))
    if name == "Custom":
        return
    pr = _acoustics.get_passive_radiator_preset(name)
    for key, value in (
        ("pr_sp_cm2", pr.sp_cm2),
        ("pr_fp_hz", pr.fp_hz),
        ("pr_qmp", pr.qmp),
        ("pr_mmp_g", pr.mmp_g),
        ("pr_xmax_mm", pr.xmax_mm),
        ("pr_added_mass_g", 0.0),
    ):
        st.session_state[key] = value

def _apply_pr_combo(name: str, count: int, added_mass_g: float) -> None:
    """Apply a matched plausible PR combination to Box Design."""
    pr = _acoustics.get_passive_radiator_preset(name)
    st.session_state["pr_preset_name"] = name
    st.session_state["pr_sp_cm2"] = float(pr.sp_cm2 * count)
    st.session_state["pr_fp_hz"] = float(pr.fp_hz)
    st.session_state["pr_qmp"] = float(pr.qmp)
    st.session_state["pr_mmp_g"] = float(pr.mmp_g * count)
    st.session_state["pr_xmax_mm"] = float(pr.xmax_mm)
    st.session_state["pr_added_mass_g"] = float(added_mass_g * count)

def _rank_value(value: float) -> float:
    return _acoustics.rank_sort_value(value)

def _batch_dccav_box(ts: _acoustics.DriverTS, total_volume_l: float) -> _acoustics.DccavBox:
    """Starter-shaped DCCAV box constrained to an exact total volume."""
    return _acoustics.design_space_box(
        ts, "DCCAV", float(total_volume_l), _acoustics.suggest_alignment(ts).fl_hz)

@st.cache_data(show_spinner=False)
def _batch_rank_presets(
    # Cache busted to reflect JSON DB fixes 3
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _acoustics.OptimizationGoals | None = None,
    driver_configuration: str = "Single driver",
    ranking_version: int = _constants._FINDER_RANKING_VERSION,
) -> list[dict]:
    if ranking_version != _constants._FINDER_RANKING_VERSION:
        raise ValueError("Unsupported Finder ranking revision")
    rows: list[dict] = []
    for name in preset_names[:int(candidate_limit)]:
        row = _acoustics.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
            driver_configuration,
        )
        if row is not None:
            rows.append(row)
    return _acoustics.sort_ranked_rows(rows)

def _is_streamlit_community_cloud(app_path: Path | None = None) -> bool:
    """Recognize Community Cloud's checkout convention."""
    resolved_path = (app_path or Path(__file__)).resolve()
    return resolved_path.is_relative_to(Path("/mount/src"))

def _finder_executor_backend(app_path: Path | None = None) -> str:
    """Keep Finder workers in the live Streamlit process.

    Python's process backends re-import ``ui_app.py`` outside Streamlit and
    can retain a different optimizer module than the active Box Design. NumPy
    releases the GIL for the heavy solver operations, so shared-memory threads
    retain useful parallelism without allowing two engine revisions to coexist.
    """
    return "thread"

def _finder_worker_limit(app_path: Path | None = None) -> int:
    """Bound duplicated catalog memory on Streamlit Community Cloud."""
    return 4 if _is_streamlit_community_cloud(app_path) else 8

def _finder_pool_fingerprint(workers: int) -> tuple:
    """Identity of the code+data the Finder workers hold in memory."""
    paths = [
        Path(module.__file__)
        for module in (_engine, _presets, _pricing, _ranking, _acoustics)
    ]
    paths.extend([
        _presets.MANUFACTURER_DATABASE_PATH,
        _presets.LOUDSPEAKER_DATABASE_PATH,
        _presets.ZTZ_AUDIO_DATABASE_PATH,
        _pricing.DRIVER_PRICES_PATH,
    ])
    mtimes = tuple(
        path.stat().st_mtime if path.exists() else None for path in paths
    )
    return (
        _constants._FINDER_RANKING_VERSION,
        _presets._CATALOG_CACHE_REVISION,
        _ranking.FINDER_WORKER_PROTOCOL_REVISION,
        _engine.OPTIMIZER_ENGINE_REVISION,
        _finder_executor_backend(),
        workers,
        *mtimes,
    )

def _finder_worker_pool(
    workers: int,
) -> ProcessPoolExecutor | ThreadPoolExecutor:
    """Return the process-wide match worker pool, warming it on first use.

    Spawning the pool and cold-importing the simulation stack in every worker
    costs seconds per Run match when the executor is recreated on each click.
    The pool is stashed on the persistent ``ranking`` module (this script's
    own globals are wiped by every Streamlit rerun, and one pool per session
    would leak workers across sessions/AppTest runs), and it is rebuilt
    whenever the src modules or driver/price datasets change on disk so the
    workers never serve stale code or catalogs.
    """
    key = _finder_pool_fingerprint(workers)
    pool = getattr(_ranking, "_finder_shared_pool", None)
    if pool is not None and getattr(_ranking, "_finder_shared_pool_key", None) == key:
        return pool
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)

    def thread_fallback() -> ThreadPoolExecutor:
        fallback = ThreadPoolExecutor(max_workers=workers)
        for _ in range(workers):
            fallback.submit(_presets.driver_preset_names)
        _ranking._finder_shared_pool = fallback
        _ranking._finder_shared_pool_key = key
        _ranking._finder_shared_pool_backend = "thread"
        return fallback

    # Cloud Run stays on shared-memory threads because its CPU/memory profile
    # is explicitly tuned for them.
    if _finder_executor_backend() == "thread":
        return thread_fallback()
    # forkserver: no re-import of the caller's __main__ in the workers (the
    # spawn method would re-execute entrypoint scripts) and no fork of a
    # thread-filled Streamlit process.
    mp_context = multiprocessing.get_context(
        "forkserver" if "forkserver" in multiprocessing.get_all_start_methods()
        else "spawn"
    )
    pool = None
    try:
        pool = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=mp_context,
        )
        warmups = [
            pool.submit(_ranking.finder_worker_ready)
            for _ in range(workers)
        ]
        # A persistent forkserver can create a brand-new pool whose children
        # still inherit an old engine module. Verify the semantic revisions,
        # not only process startup/file mtimes, before accepting any rows.
        expected_revisions = (
            _ranking.FINDER_WORKER_PROTOCOL_REVISION,
            _engine.OPTIMIZER_ENGINE_REVISION,
        )
        deadline = time.monotonic() + 10.0
        for future in warmups:
            ready = future.result(
                timeout=max(0.01, deadline - time.monotonic())
            )
            if not (
                isinstance(ready, tuple)
                and len(ready) == 3
                and tuple(ready[1:]) == expected_revisions
            ):
                raise RuntimeError(
                    "Finder worker loaded a stale ranking or optimizer engine"
                )
    except Exception:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        _runtime.logger.warning(
            "Finder process startup failed; using shared-memory threads",
            exc_info=True,
        )
        return thread_fallback()
    _ranking._finder_shared_pool = pool
    _ranking._finder_shared_pool_key = key
    _ranking._finder_shared_pool_backend = "process"
    if not getattr(_ranking, "_finder_pool_atexit_registered", False):
        atexit.register(_drop_finder_worker_pool)
        _ranking._finder_pool_atexit_registered = True
    return pool

def _drop_finder_worker_pool() -> None:
    pool = getattr(_ranking, "_finder_shared_pool", None)
    _ranking._finder_shared_pool = None
    _ranking._finder_shared_pool_key = None
    _ranking._finder_shared_pool_backend = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)

def _batch_rank_presets_parallel(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _acoustics.OptimizationGoals | None,
    progress_widget: object | None = None,
    progress_text_widget: object | None = None,
    completed_offset: int = 0,
    progress_total: int | None = None,
    driver_configuration: str = "Single driver",
    search_profile: str = _ranking.SEARCH_PROFILE_STANDARD,
) -> list[dict]:
    """Rank candidates across worker processes with a real progress bar."""
    names = list(preset_names)[:int(candidate_limit)]
    total = max(len(names), 1)
    overall_total = max(int(progress_total or total), 1)
    workers = max(1, min(os.cpu_count() or 2, _finder_worker_limit()))
    owns_progress = progress_widget is None
    if progress_widget is None:
        progress_text_widget = st.empty()
        progress = st.progress(completed_offset / overall_total)
        progress_text_widget.caption(f"Matching {completed_offset}/{overall_total} simulations")
    else:
        progress = progress_widget
    rows: list[dict] = []
    done = 0
    try:
        pool = _finder_worker_pool(workers)
        # Resolve names in the parent, whose catalog is already loaded. Worker
        # processes receive only compact T/S + display metadata payloads and
        # therefore never duplicate the full external catalog in Cloud RAM.
        candidates = [_ranking.ranking_candidate(name) for name in names]
        # Small chunks keep the ordered map streaming: with large chunks the
        # first result (and the progress bar) stalls until a whole chunk of
        # hundreds of simulations completes, which reads as a hung start.
        results = pool.map(
            _ranking.rank_candidate_row,
            candidates,
            [load_type] * len(names),
            [float(max_volume_l)] * len(names),
            [float(voltage_v)] * len(names),
            [float(f_min_hz)] * len(names),
            [float(f_max_hz)] * len(names),
            [int(points)] * len(names),
            [goals] * len(names),
            [driver_configuration] * len(names),
            [search_profile] * len(names),
            chunksize=max(1, min(32, len(names) // (workers * 4))),
        )
        progress_step = max(1, overall_total // 25)
        last_progress_t = time.monotonic()
        for row in results:
            done += 1
            now = time.monotonic()
            if done % progress_step == 0 or done == len(names) or (now - last_progress_t) >= 0.15:
                last_progress_t = now
                progress.progress(min((completed_offset + done) / overall_total, 1.0))
                if progress_text_widget is not None:
                    progress_text_widget.caption(
                        f"Matching {completed_offset + done}/{overall_total} simulations"
                        f" · {load_type}"
                    )
            if row is not None:
                rows.append(row)
    except Exception:
        _drop_finder_worker_pool()
        _runtime.logger.warning(
            "Parallel Finder optimization unavailable; falling back to serial ranking",
            exc_info=True,
        )
        progress.progress(completed_offset / overall_total)
        if progress_text_widget is not None:
            progress_text_widget.caption("Parallel matching unavailable; continuing in safe mode")
        return _batch_rank_presets_with_progress(
            tuple(names), load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), len(names), goals,
            progress, progress_text_widget, completed_offset, overall_total,
            driver_configuration, search_profile,
        )
    finally:
        if owns_progress:
            progress.empty()
            if progress_text_widget is not None:
                progress_text_widget.empty()
    return _acoustics.sort_ranked_rows(rows)

def _batch_rank_presets_with_progress(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _acoustics.OptimizationGoals | None,
    progress: object,
    progress_text: object | None,
    completed_offset: int,
    progress_total: int,
    driver_configuration: str = "Single driver",
    search_profile: str = _ranking.SEARCH_PROFILE_STANDARD,
) -> list[dict]:
    """Serial ranking path that reports real per-candidate progress."""
    names = list(preset_names)[:int(candidate_limit)]
    overall_total = max(int(progress_total), 1)
    progress_step = max(1, overall_total // 25)
    last_progress_t = time.monotonic()
    rows: list[dict] = []
    for done, name in enumerate(names, start=1):
        row = _acoustics.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
            driver_configuration, search_profile,
        )
        if row is not None:
            rows.append(row)
        current = completed_offset + done
        now = time.monotonic()
        if done % progress_step == 0 or done == len(names) or (now - last_progress_t) >= 0.15:
            last_progress_t = now
            progress.progress(min(current / overall_total, 1.0))
            if progress_text is not None:
                progress_text.caption(f"Matching {current}/{overall_total} simulations · {load_type}")
    return _acoustics.sort_ranked_rows(rows)

def _finder_row_driver(row: dict) -> _acoustics.DriverTS:
    """Return the exact base driver used to calculate a Finder row."""
    payload = row.get("_driver_ts")
    if isinstance(payload, dict):
        fields = _acoustics.DriverTS.__dataclass_fields__
        try:
            return _acoustics.DriverTS(**{
                name: payload[name]
                for name in fields
                if name in payload
            })
        except (TypeError, ValueError):
            _runtime.logger.warning("Invalid Finder driver snapshot; using live preset")
    return _acoustics.get_driver_preset(str(row["Driver"]))

def _finder_row_box_params(row: dict) -> dict:
    """Return the complete physical box snapshot saved by Finder."""
    payload = row.get("_box_params")
    return dict(payload) if isinstance(payload, dict) else {}

def _finder_box_value(row: dict, key: str, default):
    return _finder_row_box_params(row).get(key, default)

def _apply_batch_result(row: dict, load_type: str) -> None:
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    legacy_pr = load_type == "Passive radiator"
    if legacy_pr:
        load_type = "Bass reflex"
    name = str(row["Driver"])
    driver = _finder_row_driver(row)
    driver_configuration = str(
        row.get("Driver configuration", "Single driver")
    )
    configured_driver = _acoustics.apply_driver_configuration(
        driver,
        driver_configuration,
    )
    st.session_state["load_type"] = load_type
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = driver_configuration
    _catalog._apply_driver_preset(driver)
    st.session_state["driver_panel_air_load"] = bool(driver.panel_air_load)
    st.session_state["driver_panel_coupling"] = float(driver.panel_coupling)
    _optimizer._use_manual_box_strategy()
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["opt_max_ripple_freq_hz"] = float(st.session_state.get("finder_max_ripple_freq_hz", 0.0) or 0.0)
    if load_type == "Bass reflex":
        st.session_state["reflex_vb_l"] = float(row["Vb L"])
        resonator = str(row.get(
            "Resonator", _constants._RESONATOR_PR if legacy_pr else _constants._RESONATOR_PORT))
        st.session_state["reflex_resonator_type"] = resonator
        if resonator == _constants._RESONATOR_PR:
            pr = _acoustics.suggest_pr_alignment(configured_driver)
            st.session_state["pr_sp_cm2"] = float(pr.pr_sp_cm2)
            st.session_state["pr_fp_hz"] = float(pr.pr_fp_hz)
            st.session_state["pr_qmp"] = float(pr.pr_qmp)
            st.session_state["pr_mmp_g"] = float(pr.pr_mmp_g)
            st.session_state["pr_xmax_mm"] = float(pr.pr_xmax_mm)
            st.session_state["pr_q_abs"] = float(_finder_box_value(row, "q_abs", 15.0))
            st.session_state["pr_q_leak"] = float(_finder_box_value(row, "q_leak", 1000.0))
        else:
            st.session_state["reflex_fb_hz"] = float(row["Fb Hz"])
            st.session_state["reflex_q_abs"] = float(_finder_box_value(row, "q_abs", _constants._DEFAULT_REFLEX_Q_ABS))
            st.session_state["reflex_q_leak"] = float(_finder_box_value(row, "q_leak", _constants._DEFAULT_REFLEX_Q_LEAK))
            st.session_state["reflex_q_port"] = float(_finder_box_value(row, "q_port", _constants._DEFAULT_REFLEX_Q_PORT))
            st.session_state["reflex_custom_losses"] = True
    elif load_type == "Bandpass 4th order":
        st.session_state["bandpass4_vs_l"] = float(row["Vs L"])
        st.session_state["bandpass4_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass4_fp_hz"] = float(row["Fp Hz"])
        for key in ("q_abs_s", "q_abs_p", "q_leak_s", "q_leak_p", "q_port"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bandpass4_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Bandpass 6th order":
        st.session_state["bandpass6_vr_l"] = float(row["Vr L"])
        st.session_state["bandpass6_fr_hz"] = float(row["Fr Hz"])
        st.session_state["bandpass6_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass6_fp_hz"] = float(row["Fp Hz"])
        for key in ("q_abs_r", "q_abs_p", "q_leak_r", "q_leak_p", "q_port_r", "q_port_p"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bandpass6_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Bandpass 8th order":
        st.session_state["bp8_v1_l"] = float(row["V1 L"])
        st.session_state["bp8_f1_hz"] = float(row["f1 Hz"])
        st.session_state["bp8_v2_l"] = float(row["V2 L"])
        st.session_state["bp8_f2_hz"] = float(row["f2 Hz"])
        st.session_state["bp8_v3_l"] = float(row["V3 L"])
        st.session_state["bp8_f3_hz"] = float(row["f3 Hz"])
        for key in ("q_abs_1", "q_abs_2", "q_abs_3", "q_leak_1", "q_leak_2", "q_leak_3", "q_port_1", "q_port_2", "q_port_3"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bp8_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Sealed":
        st.session_state["sealed_vb_l"] = float(row["Vb L"])
        st.session_state["sealed_q_abs"] = float(_finder_box_value(row, "q_abs", 15.0))
        st.session_state["sealed_q_leak"] = float(_finder_box_value(row, "q_leak", 1000.0))
    elif load_type == "DCCAV":
        st.session_state["box_vh_l"] = float(row["Vh L"])
        st.session_state["box_fh_hz"] = float(row["fh Hz"])
        st.session_state["box_vl_l"] = float(row["Vl L"])
        st.session_state["box_fl_hz"] = float(row["fl Hz"])
        for key in ("q_abs_h", "q_abs_l", "q_leak_h", "q_leak_l", "q_port_h", "q_port_l"):
            if key in _finder_row_box_params(row):
                st.session_state[f"loss_{key}"] = float(_finder_box_value(row, key, 0.0))
    if load_type == "Bass reflex" and not _state._reflex_uses_passive_radiator():
        optimized_box = _state._reflex_box_from_state()
    elif load_type == "Bandpass 4th order":
        optimized_box = _state._bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        optimized_box = _state._bandpass6_box_from_state()
    elif load_type == "Bandpass 8th order":
        optimized_box = _state._bandpass8_box_from_state()
    elif load_type == "DCCAV":
        optimized_box = _state._box_from_state()
    else:
        optimized_box = None
    if optimized_box is not None:
        _optimizer._apply_optimized_port_geometry(driver, optimized_box)
    _mark_auto_alignment_synced(driver)

def _finder_result_snapshot(
    row: dict,
    load_type: str,
    frequency_hz: np.ndarray,
    voltage_v: float,
) -> dict:
    """Simulate one ranked Finder row as a reusable Box Design comparison."""
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    legacy_pr = load_type == "Passive radiator"
    if legacy_pr:
        load_type = "Bass reflex"
    resonator = str(
        row.get("Resonator", _constants._RESONATOR_PR if legacy_pr else _constants._RESONATOR_PORT)
    )
    name = str(row["Driver"])
    configuration = str(
        row.get("Driver configuration", "Single driver")
    )
    driver = _acoustics.apply_driver_configuration(
        _finder_row_driver(row),
        configuration,
    )
    if load_type == "Bass reflex" and resonator == _constants._RESONATOR_PR:
        suggested = _acoustics.suggest_pr_alignment(driver)
        box = _acoustics.PassiveRadiatorBox(
            vb_l=float(row["Vb L"]),
            pr_sp_cm2=float(suggested.pr_sp_cm2),
            pr_fp_hz=float(suggested.pr_fp_hz),
            pr_qmp=float(suggested.pr_qmp),
            pr_mmp_g=float(suggested.pr_mmp_g),
            pr_xmax_mm=float(suggested.pr_xmax_mm),
            q_abs=float(_finder_box_value(row, "q_abs", 15.0)),
            q_leak=float(_finder_box_value(row, "q_leak", 1000.0)),
        )
        result = _acoustics.simulate_passive_radiator(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bass reflex":
        box = _acoustics.ReflexBox(
            vb_l=float(row["Vb L"]),
            fb_hz=float(row["Fb Hz"]),
            q_abs=float(_finder_box_value(row, "q_abs", _constants._DEFAULT_REFLEX_Q_ABS)),
            q_leak=float(_finder_box_value(row, "q_leak", _constants._DEFAULT_REFLEX_Q_LEAK)),
            q_port=float(_finder_box_value(row, "q_port", _constants._DEFAULT_REFLEX_Q_PORT)),
        )
        result = _acoustics.simulate_reflex(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 4th order":
        box = _acoustics.Bandpass4Box(
            vs_l=float(row["Vs L"]),
            vp_l=float(row["Vp L"]),
            fp_hz=float(row["Fp Hz"]),
            q_abs_s=float(_finder_box_value(row, "q_abs_s", 15.0)),
            q_abs_p=float(_finder_box_value(row, "q_abs_p", 15.0)),
            q_leak_s=float(_finder_box_value(row, "q_leak_s", 1000.0)),
            q_leak_p=float(_finder_box_value(row, "q_leak_p", 1000.0)),
            q_port=float(_finder_box_value(row, "q_port", 15.0)),
        )
        result = _acoustics.simulate_bandpass4(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 6th order":
        box = _acoustics.Bandpass6Box(
            vr_l=float(row["Vr L"]),
            fr_hz=float(row["Fr Hz"]),
            vp_l=float(row["Vp L"]),
            fp_hz=float(row["Fp Hz"]),
            q_abs_r=float(_finder_box_value(row, "q_abs_r", 15.0)),
            q_abs_p=float(_finder_box_value(row, "q_abs_p", 15.0)),
            q_leak_r=float(_finder_box_value(row, "q_leak_r", 1000.0)),
            q_leak_p=float(_finder_box_value(row, "q_leak_p", 1000.0)),
            q_port_r=float(_finder_box_value(row, "q_port_r", 15.0)),
            q_port_p=float(_finder_box_value(row, "q_port_p", 15.0)),
        )
        result = _acoustics.simulate_bandpass6(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 8th order":
        box = _acoustics.Bandpass8Box(
            v1_l=float(row["V1 L"]),
            f1_hz=float(row["f1 Hz"]),
            v2_l=float(row["V2 L"]),
            f2_hz=float(row["f2 Hz"]),
            v3_l=float(row["V3 L"]),
            f3_hz=float(row["f3 Hz"]),
            q_abs_1=float(_finder_box_value(row, "q_abs_1", 15.0)),
            q_abs_2=float(_finder_box_value(row, "q_abs_2", 15.0)),
            q_abs_3=float(_finder_box_value(row, "q_abs_3", 15.0)),
            q_leak_1=float(_finder_box_value(row, "q_leak_1", 1000.0)),
            q_leak_2=float(_finder_box_value(row, "q_leak_2", 1000.0)),
            q_leak_3=float(_finder_box_value(row, "q_leak_3", 1000.0)),
            q_port_1=float(_finder_box_value(row, "q_port_1", 15.0)),
            q_port_2=float(_finder_box_value(row, "q_port_2", 15.0)),
            q_port_3=float(_finder_box_value(row, "q_port_3", 15.0)),
        )
        result = _acoustics.simulate_bandpass8(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Sealed":
        box = _acoustics.SealedBox(
            vb_l=float(row["Vb L"]),
            q_abs=float(_finder_box_value(row, "q_abs", 15.0)),
            q_leak=float(_finder_box_value(row, "q_leak", 1000.0)),
        )
        result = _acoustics.simulate_sealed(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Infinite baffle":
        box = None
        result = _acoustics.simulate_infinite_baffle(
            driver, frequency_hz, voltage_v
        )
    else:
        load_type = "DCCAV"
        box = _acoustics.DccavBox(
            vh_l=float(row["Vh L"]),
            fh_hz=float(row["fh Hz"]),
            vl_l=float(row["Vl L"]),
            fl_hz=float(row["fl Hz"]),
            q_abs_h=float(_finder_box_value(row, "q_abs_h", 15.0)),
            q_abs_l=float(_finder_box_value(row, "q_abs_l", 15.0)),
            q_leak_h=float(_finder_box_value(row, "q_leak_h", 1000.0)),
            q_leak_l=float(_finder_box_value(row, "q_leak_l", 1000.0)),
            q_port_h=float(_finder_box_value(row, "q_port_h", 15.0)),
            q_port_l=float(_finder_box_value(row, "q_port_l", 15.0)),
        )
        result = _acoustics.simulate(driver, box, frequency_hz, voltage_v)
    return _analysis._pinned_response_snapshot(
        load_type,
        box,
        result,
        label=_analysis._pin_label(
            load_type,
            box,
            preset=name,
            config=configuration,
        ),
    )

def _apply_pending_batch_result() -> None:
    pending = st.session_state.pop("batch_pending_result", None)
    if not pending:
        return
    existing_tabs = _analysis._design_comparison_tabs()
    added = _add_finder_designs_to_comparison(
        [{
            "row": pending["row"],
            "load_type": str(pending["load_type"]),
        }],
        float(pending.get(
            "voltage_v",
            st.session_state.get("finder_voltage", 2.83),
        )),
    )
    if added:
        action = "Added" if existing_tabs else "Opened"
        st.toast(f"{action} {added[0]['label']} in Box Design")
    else:
        st.toast(
            f"Box Design already has {_constants._MAX_COMPARISON_DESIGNS} designs"
        )

def _add_finder_designs_to_comparison(
    designs: list[dict],
    voltage_v: float,
) -> list[dict]:
    """Append Finder matches as editable tabs without replacing open designs."""
    comparison_tabs = _analysis._design_comparison_tabs()
    available = max(0, _constants._MAX_COMPARISON_DESIGNS - len(comparison_tabs))
    if available <= 0:
        return []
    frequency_hz = np.geomspace(
        float(st.session_state["sim_f_min"]),
        float(st.session_state["sim_f_max"]),
        int(st.session_state["sim_points"]),
    )
    added_tabs = []
    for design in designs[:available]:
        row = design["row"]
        load_type = str(design["load_type"])
        _apply_batch_result(row, load_type)
        st.session_state["sim_voltage"] = float(voltage_v)
        st.session_state["sim_series_r_ohm"] = 0.0
        tab_number = len(comparison_tabs) + 1
        tab_id = f"design_{uuid.uuid4().hex}"
        label = _analysis._design_comparison_tab_label(
            tab_number,
            load_type,
            preset=str(row["Driver"]),
            config=str(row.get("Driver configuration", "Single driver")),
        )
        color = _constants._DESIGN_COMPARISON_TRACE_COLORS[
            len(comparison_tabs) % len(_constants._DESIGN_COMPARISON_TRACE_COLORS)
        ]
        snapshot = _finder_result_snapshot(
            row,
            load_type,
            frequency_hz,
            float(voltage_v),
        )
        snapshot["label"] = label
        snapshot["color"] = color
        new_tab = {
            "id": tab_id,
            "label": label,
            "color": color,
            "driver_preset_name": str(row["Driver"]),
            "display_driver_name": str(row["Driver"]),
            "load_type": load_type,
            "visible": True,
            "parameters": _state._json_safe(_state._collect_params()),
            "snapshot": snapshot,
        }
        comparison_tabs.append(new_tab)
        added_tabs.append(new_tab)
    if not added_tabs:
        return []
    active = added_tabs[0]
    _projects._apply_loaded_params(dict(active["parameters"]))
    st.session_state["design_comparison_tabs"] = comparison_tabs
    st.session_state["design_comparison_active_id"] = active["id"]
    st.session_state["design_comparison_loaded_id"] = active["id"]
    st.session_state["pinned_responses"] = [
        dict(item["snapshot"])
        for item in comparison_tabs
        if str(item["id"]) != str(active["id"])
        and isinstance(item.get("snapshot"), dict)
    ]
    st.session_state["plot_compare_loads"] = False
    st.session_state["workspace_mode"] = "Box Design"
    return added_tabs

def _apply_pending_batch_comparison() -> None:
    pending = st.session_state.pop("batch_pending_comparison", None)
    if not isinstance(pending, dict):
        return
    designs = pending.get("designs", [])
    if not isinstance(designs, list) or len(designs) < 2:
        return
    voltage_v = float(pending.get("voltage_v", 2.83))
    existing_count = len(_analysis._design_comparison_tabs())
    added = _add_finder_designs_to_comparison(designs, voltage_v)
    action = "Added" if existing_count else "Created"
    st.toast(f"{action} {len(added)} editable Box Design tabs")

def _apply_library_driver(name: str) -> None:
    """Load one library preset into the current simulation workspace."""
    _analysis._end_design_comparison()
    driver = _acoustics.get_driver_preset(name)
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = "Single driver"
    _catalog._apply_driver_preset(driver)
    if _state._box_strategy_is_auto():
        _optimizer._apply_suggested_box_for(driver)
        _mark_auto_alignment_synced(driver)
    st.session_state["workspace_mode"] = "Box Design"

def _apply_library_pr(name: str) -> None:
    """Load one passive radiator preset into the current simulation workspace."""
    _analysis._end_design_comparison()
    pr = _acoustics.get_passive_radiator_preset(name)
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["load_type"] = "Bass reflex"
    st.session_state["reflex_resonator_type"] = "Passive radiator"
    st.session_state["pr_preset_name"] = name
    st.session_state["pr_sp_cm2"] = pr.sp_cm2
    st.session_state["pr_fp_hz"] = pr.fp_hz
    st.session_state["pr_qmp"] = pr.qmp
    st.session_state["pr_mmp_g"] = pr.mmp_g
    st.session_state["pr_xmax_mm"] = pr.xmax_mm
    st.session_state["pr_added_mass_g"] = 0.0

def _apply_pending_atlas_point() -> None:
    pending = st.session_state.pop("atlas_pending_point", None)
    if not pending:
        return
    load_type = str(pending["load_type"])
    try:
        driver = _state._driver_from_state()
        if load_type == "Bass reflex":
            template = _state._reflex_box_from_state()
        elif load_type == "Bandpass 4th order":
            template = _state._bandpass4_box_from_state()
        elif load_type == "Bandpass 6th order":
            template = _state._bandpass6_box_from_state()
        elif load_type == "Bandpass 8th order":
            template = _state._bandpass8_box_from_state()
        elif load_type == "Sealed":
            template = _state._sealed_box_from_state()
        else:
            template = _state._box_from_state()
        box = _acoustics.design_space_box(
            driver, load_type, float(pending["x"]), float(pending["y"]), template)
    except Exception:
        _runtime.logger.exception("Could not apply the atlas point")
        return
    _optimizer._use_manual_box_strategy()
    _optimizer._apply_optimized_box(box)
    _mark_auto_alignment_synced(driver)
    st.toast("Applied the atlas box to the design (Manual strategy)")

def _queue_atlas_point(load_type: str, x: float, y: float) -> None:
    """Queue an Atlas box change before Streamlit reruns the full design."""
    st.session_state["atlas_pending_point"] = {
        "load_type": load_type,
        "x": float(x),
        "y": float(y),
    }

def _atlas_loss_signature(load_type: str, box) -> tuple:
    if load_type == "Bass reflex":
        return (box.q_abs, box.q_leak, box.q_port)
    if load_type == "Bandpass 4th order":
        return (box.q_abs_s, box.q_abs_p, box.q_leak_s, box.q_leak_p, box.q_port)
    if load_type == "Bandpass 6th order":
        return (
            box.q_abs_r, box.q_abs_p, box.q_leak_r, box.q_leak_p,
            box.q_port_r, box.q_port_p,
        )
    if load_type == "Bandpass 8th order":
        return (
            box.q_abs_1, box.q_abs_2, box.q_abs_3,
            box.q_leak_1, box.q_leak_2, box.q_leak_3,
            box.q_port_1, box.q_port_2, box.q_port_3,
        )
    if load_type == "Sealed":
        return (box.q_abs, box.q_leak)
    return (
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )

def _atlas_frame(space: _acoustics.DesignSpaceMap) -> pd.DataFrame:
    rows = []
    for iy, y in enumerate(space.y_values):
        for ix, x in enumerate(space.x_values):
            rows.append({
                "x_value": round(float(x), 3),
                "y_value": round(float(y), 3),
                "f3_hz": float(space.f3_hz[iy, ix]),
                "ripple_db": float(space.ripple_db[iy, ix]),
            })
    return pd.DataFrame(rows)

def _render_atlas_tab(current_ts, load_type: str, box, sim_voltage: float) -> None:
    st.subheader("Design Space Atlas")
    if load_type == "Infinite baffle":
        st.caption("Infinite baffle has no box parameters to map.")
        return
    st.toggle(
        "Compute atlas", key="atlas_enabled",
        help="Simulates a grid of boxes around the empirical starter "
             "(a few hundred runs, cached per driver, losses and voltage).",
    )
    if not st.session_state.get("atlas_enabled", False):
        st.caption(
            "Enable to map F3 and ripple over the box plane and apply any "
            "point to the design with a click."
        )
        return
    space = _analysis._design_space_cached(
        current_ts, load_type, _atlas_loss_signature(load_type, box), sim_voltage)
    frame = _atlas_frame(space)
    metric = st.radio(
        "Color by", ("F3 (Hz)", "Ripple (dB)"), horizontal=True, key="atlas_metric")
    field = "f3_hz" if str(metric).startswith("F3") else "ripple_db"
    picker = alt.selection_point(
        name="atlas_point", fields=["x_value", "y_value"], on="click", empty=False)
    color = alt.Color(
        f"{field}:Q", title=str(metric),
        scale=alt.Scale(scheme="viridis", reverse=True))
    tooltips = [
        alt.Tooltip("x_value:Q", title=space.x_label, format=".2f"),
        alt.Tooltip("y_value:Q", title=space.y_label or "-", format=".2f"),
        alt.Tooltip("f3_hz:Q", title="F3 (Hz)", format=".1f"),
        alt.Tooltip("ripple_db:Q", title="Ripple (dB)", format=".2f"),
    ]
    if len(space.y_values) > 1:
        chart = alt.Chart(frame).mark_rect().encode(
            x=alt.X(
                "x_value:O", title=space.x_label,
                axis=alt.Axis(format="~g", labelAngle=-45, labelOverlap="greedy"),
            ),
            y=alt.Y(
                "y_value:O", title=space.y_label, sort="descending",
                axis=alt.Axis(format="~g"),
            ),
            color=color,
            tooltip=tooltips,
        ).add_params(picker).properties(height=520)
    else:
        chart = alt.Chart(frame).mark_line(point=True).encode(
            x=alt.X(
                "x_value:Q", title=space.x_label,
                scale=alt.Scale(type="log", nice=False),
            ),
            y=alt.Y("f3_hz:Q", title="F3 (Hz)"),
            tooltip=tooltips,
        ).add_params(picker).properties(height=420)
    event = st.altair_chart(
        chart, width="stretch", key="atlas_chart", on_select="rerun")
    st.caption(
        f"{len(space.x_values)}×{len(space.y_values)} grid around the empirical "
        f"starter, evaluated at {sim_voltage:.2f} V with 0 Ω series resistance "
        "and the current loss factors."
    )
    try:
        picked = list(event.selection["atlas_point"])
    except Exception:
        picked = []
    if not picked:
        st.caption("Click a point to inspect it, then apply it to the design.")
        return
    point = picked[0]
    x_sel = float(point.get("x_value", 0.0))
    y_sel = float(point.get("y_value", 0.0))
    match = frame[(frame["x_value"] == x_sel) & (frame["y_value"] == y_sel)]
    if match.empty:
        return
    row = match.iloc[0]
    y_txt = f" · {space.y_label} {y_sel:.2f}" if space.y_label else ""
    st.markdown(
        f"**Selected:** {space.x_label} {x_sel:.2f}{y_txt} · "
        f"F3 {_optimizer._fmt_hz(row['f3_hz'])} · ripple {_optimizer._fmt_db(row['ripple_db'])}"
    )
    st.button(
        "Apply selected box",
        type="primary",
        width="stretch",
        on_click=_queue_atlas_point,
        args=(load_type, x_sel, y_sel),
    )

def _finder_optimizer_goals_from_state() -> _acoustics.OptimizationGoals:
    return _acoustics.OptimizationGoals(
        objective=_constants._OPT_OBJECTIVE_LABELS[
            st.session_state.get("finder_objective", "Max extension")
        ],
        max_total_volume_l=float(st.session_state.get("finder_volume_l", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("finder_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("finder_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("finder_max_gd_ms", 0.0)) or None,
        min_spl_db=float(st.session_state.get("finder_min_spl_db", 0.0)) or None,
        ripple_max_freq_hz=float(st.session_state.get("finder_max_ripple_freq_hz", 0.0)) or None,
    )

def _show_advanced_controls() -> bool:
    """Return whether the expert sidebar controls are visible."""
    return bool(st.session_state.get("ui_show_advanced", False))

def _apply_finder_scenario() -> None:
    """Apply a guided scenario to the live Finder sidebar state."""
    scenario = str(st.session_state.get("finder_scenario", "Custom"))
    preset = _constants._FINDER_SCENARIOS.get(scenario)
    if not preset:
        return
    for key, value in preset.items():
        st.session_state[key] = value

def _render_finder_scenario_selector() -> None:
    """Offer practical scenarios that configure the Finder brief in one click."""
    st.selectbox(
        "Guided setup",
        list(_constants._FINDER_SCENARIOS),
        key="finder_scenario",
        on_change=_apply_finder_scenario,
        help="Preconfigure the brief for a typical use case: Home theater "
             "(deep extension below 80 Hz), Car SPL (compact box, high output), "
             "Hi-Fi (flat response) or Infinite baffle. Choose Custom to keep "
             "your own settings.",
    )

def _render_find_driver_target_sidebar() -> None:
    """Render the enclosure conditions used for every Finder candidate."""
    finder_load_types, only_infinite_baffle = _catalog._finder_load_context()
    if _show_advanced_controls():
        _state._finder_selectbox(
            "Driver configuration",
            list(_acoustics.DRIVER_CONFIGURATIONS),
            key="finder_driver_configuration",
            help="Rank every candidate as one driver; a 2–8-driver series, "
                 "parallel or mixed array; or an isobaric array up to 16 total drivers.",
        )
    _state._finder_number_input(
        "Maximum volume (L)",
        min_value=0.1,
        max_value=2000.0,
        step=1.0,
        key="finder_volume_l",
        disabled=only_infinite_baffle,
        help="Upper limit for Vh+Vl (DCCAV), chamber total (bandpass), or Vb "
             "(reflex/sealed). Finder may choose a smaller optimal volume.",
    )
    if only_infinite_baffle:
        st.caption("Infinite baffle does not use a box volume.")
    if _show_advanced_controls() and "Bass reflex" in finder_load_types:
        with st.expander("Ports", expanded=True):
            _state._finder_selectbox(
                "Bass-reflex resonator",
                list(_constants._RESONATOR_TYPES),
                key="finder_reflex_resonator_type",
                help="Rank the reflex enclosure with an air vent or a passive radiator.",
            )
    if _show_advanced_controls():
        _state._finder_number_input(
            "Comparison voltage (V)", min_value=0.01, max_value=200.0,
            step=0.01, key="finder_voltage",
            help="All candidates are compared at the same input voltage; 2.83 V is the standard reference.",
        )

def _run_find_driver_search(
    filtered_preset_names: list[str],
    context_preset_names: list[str] | None = None,
    stats_slot=None,
) -> None:
    """Rank the filtered candidates from the current Finder sidebar state."""
    price_enabled = bool(st.session_state.get("preset_price_enabled", False))
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
    max_price = float(st.session_state.get("preset_max_price", 0.0) or 0.0)
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    finder_volume_l = float(_state._finder_value("finder_volume_l"))
    finder_driver_configuration = str(
        _state._finder_value("finder_driver_configuration")
    )
    candidate_pools, prefilter_stats = _catalog._finder_prefilter(
        filtered_preset_names
    )
    scan_count = len(filtered_preset_names)
    eligible_total = prefilter_stats["eligible_simulations"]
    progress_total = max(eligible_total, 1)
    t_start = time.perf_counter()
    with st.container(key="finder_match_progress"):
        progress = st.progress(0.0)
        progress_text = st.empty()
        progress_text.caption(
            f"Bass Match · 0/{eligible_total} simulations"
            f" · {prefilter_stats['rejected_simulations']} skipped a priori"
        )
    all_rows: list[dict] = []
    load_run_stats: dict[str, dict] = {}
    completed_offset = 0
    finder_search_profile = str(_state._finder_value("finder_search_profile"))
    evaluations_per_load = {
        lt: _ranking.finder_optimizer_evaluation_limit(
            profile=finder_search_profile, load_type=lt)
        for lt in finder_load_types
    }
    for lt in finder_load_types:
        load_preset_names = candidate_pools.get(lt, [])
        load_scan_count = len(load_preset_names)
        is_infinite_baffle = lt == "Infinite baffle"
        uses_pr = lt == "Bass reflex" and _state._reflex_uses_passive_radiator(finder=True)
        ranking_load_type = "Passive radiator" if uses_pr else lt
        # PR ranking uses the dedicated physical starter because the generic
        # enclosure optimizer currently sweeps vented-box geometry only.
        goals = (
            None if is_infinite_baffle or uses_pr
            else _finder_optimizer_goals_from_state()
        )
        rank_args = (
            tuple(load_preset_names),
            ranking_load_type,
            finder_volume_l,
            float(_state._finder_value("finder_voltage")),
            float(_state._finder_value("finder_f_min")),
            float(_state._finder_value("finder_f_max")),
            min(int(_state._finder_value("finder_points")), 80)
            if os.getenv("K_SERVICE") else int(_state._finder_value("finder_points")),
            load_scan_count,
        )
        load_started = time.perf_counter()
        if load_scan_count > 8:
            batch_rows = _batch_rank_presets_parallel(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
                finder_driver_configuration,
                finder_search_profile,
            )
            # A worker can hold a stale external-catalog module after a
            # Streamlit reload. If the whole pool returns no rows, retry this
            # load serially in the current process before reporting failure.
            if not batch_rows and load_scan_count:
                batch_rows = _batch_rank_presets_with_progress(
                    tuple(load_preset_names),
                    ranking_load_type,
                    finder_volume_l,
                    float(_state._finder_value("finder_voltage")),
                    float(_state._finder_value("finder_f_min")),
                    float(_state._finder_value("finder_f_max")),
                    int(_state._finder_value("finder_points")),
                    load_scan_count,
                    goals,
                    progress,
                    progress_text,
                    completed_offset,
                    progress_total,
                    finder_driver_configuration,
                    finder_search_profile,
                )
        else:
            batch_rows = _batch_rank_presets_with_progress(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
                finder_driver_configuration,
                finder_search_profile,
            )
        load_run_stats[lt] = {
            "attempted": load_scan_count,
            "usable": len(batch_rows),
            "elapsed_s": time.perf_counter() - load_started,
            "evaluations_per_driver": (
                0 if (is_infinite_baffle or uses_pr)
                else int(evaluations_per_load.get(lt, 0))
            ),
        }
        if lt == "Bass reflex":
            for row in batch_rows:
                row["_load_type"] = "Bass reflex"
                row["Resonator"] = _constants._RESONATOR_PR if uses_pr else _constants._RESONATOR_PORT
        all_rows.extend(batch_rows)
        completed_offset += load_scan_count
    min_spl_db = float(st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    min_mol_f3_db = float(
        st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0
    )
    max_f3_hz = float(
        st.session_state.get("finder_max_f3_hz", 0.0) or 0.0
    )
    max_ripple_db = float(
        st.session_state.get("finder_max_ripple_db", 0.0) or 0.0
    )
    all_rows = _catalog._filter_finder_performance_rows(
        all_rows, min_spl_db, min_mol_f3_db, max_f3_hz, max_ripple_db
    )
    # Apply the active price constraint to the final ranked rows as well as
    # to the library pool.  This keeps stale/cached simulations from leaking
    # unpriced drivers (or drivers above the limit) into the results table
    # after the user changes the maximum price.
    rates = _catalog._current_exchange_rates()[0]
    filtered_rows = []
    for row in all_rows:
        driver_name = str(row.get("Driver", ""))
        display_currency = price_currency or _catalog._driver_preset_currency(driver_name)
        normalized_price = _catalog._normalized_preset_price(
            driver_name, display_currency, rates
        )
        has_price = (
            normalized_price is not None
            and np.isfinite(float(normalized_price))
        )
        if price_enabled and (
            not has_price or float(normalized_price) > max_price
        ):
            continue
        # Keep table/export consistent with the catalog whenever a price is
        # available, independently of whether the max-price filter is on.
        if has_price:
            row["Price"] = float(normalized_price)
            row["Currency"] = display_currency
        filtered_rows.append(row)
    all_rows = filtered_rows
    all_rows = _acoustics.sort_ranked_rows(all_rows)
    all_rows, collapsed_result_rows = _catalog._deduplicate_finder_result_rows(
        all_rows
    )
    t_end = time.perf_counter()
    elapsed_s = t_end - t_start
    elapsed_ms_per_simulation = (
        (elapsed_s * 1000) / eligible_total
        if eligible_total > 0
        else 0.0
    )
    unique_driver_total = int(prefilter_stats["unique_drivers"])
    elapsed_ms_per_driver = (
        (elapsed_s * 1000) / unique_driver_total
        if unique_driver_total > 0
        else 0.0
    )
    simulations_per_second = (
        eligible_total / elapsed_s if elapsed_s > 0.0 else 0.0
    )
    progress.progress(1.0)
    progress_text.empty()
    progress.empty()
    st.session_state["batch_results"] = all_rows
    st.session_state["batch_search_completed"] = True
    evals_per_candidate = max(evaluations_per_load.values(), default=0)
    # Each candidate undergoes full compass evaluations + narrow F3 refinement passes + finalist adaptive grid verification
    actual_acoustic_simulations = 0
    for lt, budget in evaluations_per_load.items():
        attempted = int(load_run_stats.get(lt, {}).get("attempted", 0))
        refine_mult = 1.25 if budget >= 30 else 1.0
        actual_acoustic_simulations += int(attempted * budget * refine_mult)

    st.session_state["finder_last_run_stats"] = {
        "elapsed_s": elapsed_s,
        "milliseconds_per_simulation": elapsed_ms_per_simulation,
        "milliseconds_per_driver": elapsed_ms_per_driver,
        "simulations_per_second": simulations_per_second,
        "simulations": eligible_total,
        "actual_acoustic_simulations": actual_acoustic_simulations,
        "evaluations_per_driver": evals_per_candidate,
        "evaluations_per_load": evaluations_per_load,
        "search_profile": finder_search_profile,
        "unique_drivers": unique_driver_total,
        "skipped_a_priori": int(prefilter_stats["rejected_simulations"]),
        "loads": load_run_stats,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    # Fill the statistics placeholder created before the run instead of
    # triggering a full-page rerun, which moved the user's scroll position.
    _render_finder_run_statistics(stats_slot)
    st.session_state["batch_result_context"] = (
        tuple(finder_load_types),
        finder_volume_l,
        scan_count,
        bool(_finder_optimizer_goals_from_state()),
        str(st.session_state.get("finder_objective", "Max extension")),
        str(st.session_state.get("finder_reflex_resonator_type", _constants._RESONATOR_PORT)),
        min_spl_db,
        min_mol_f3_db,
        float(st.session_state.get("finder_max_mms_g", 0.0) or 0.0),
        float(st.session_state.get("finder_max_le_mh", 0.0) or 0.0),
        _constants._FINDER_RANKING_VERSION,
        prefilter_stats["eligible_simulations"],
        prefilter_stats["total_simulations"],
        prefilter_stats["rejected_simulations"],
        collapsed_result_rows,
        _catalog._finder_result_context_signature(
            context_preset_names
            if context_preset_names is not None
            else filtered_preset_names
        ),
        _constants._FINDER_CONTEXT_FILTERED_POOL_VERSION,
    )
    st.session_state.pop("_restored_bass_match_controls_signature", None)
    _projects._invalidate_bass_match_results_signature()

def _render_find_driver_goal_sidebar() -> None:
    """Render Finder objective and constraints as the second workflow step."""
    finder_load_types, only_infinite_baffle = _catalog._finder_load_context()
    only_passive_radiator = (
        finder_load_types == ["Bass reflex"]
        and _state._reflex_uses_passive_radiator(finder=True)
    )
    advanced_controls = _show_advanced_controls()
    if advanced_controls:
        _state._finder_number_input(
            "Maximum F3 (Hz, 0 = off)",
            min_value=0.0,
            max_value=500.0,
            step=1.0,
            key="finder_max_f3_hz",
            help="Exclude simulated designs whose F3 is above this hard limit; "
                 "0 disables the constraint.",
        )
        _state._finder_number_input(
            "Minimum MOL at F3 (dB, 0 = off)",
            min_value=0.0,
            max_value=150.0,
            step=0.5,
            key="finder_min_mol_f3_db",
            help="Require the excursion/thermal limited maximum output at the "
                 "candidate's F3 to reach this level; 0 disables.",
        )
    if only_infinite_baffle:
        st.caption(
            "Infinite baffle has no enclosure to optimize; candidates are "
            "ranked on their free-air response."
        )
    else:
        if advanced_controls:
            _state._finder_number_input(
                "Minimum SPL (dB, 0 = off)", min_value=0.0, max_value=150.0,
                step=0.5, key="finder_min_spl_db",
                help="Require at least this simulated peak SPL at the comparison "
                     "voltage. A conservative reference-sensitivity check first "
                     "removes candidates that cannot plausibly reach it; the final "
                     "hard check uses the simulated response. 0 disables.",
            )
        if only_passive_radiator:
            st.caption(
                "Passive-radiator candidates use the dedicated physical starter, "
                "capped by the selected maximum Vb, and are ranked by the resulting response."
            )
        else:
            if "Bass reflex" in finder_load_types and _state._reflex_uses_passive_radiator(finder=True):
                st.caption(
                    "The selected objective optimizes the other loads; passive-radiator "
                    "candidates use their dedicated starter under the same volume cap."
                )
            _state._finder_selectbox(
                "Optimization goal", list(_constants._OPT_OBJECTIVE_LABELS), key="finder_objective",
                help="Every candidate box is derived by the same optimizer as the "
                     "Design workspace, without exceeding Maximum volume. Balanced "
                     "trades extension against smoothness and box practicality.",
            )
            if advanced_controls:
                _state._finder_number_input(
                    "Allowed response ripple (dB)", min_value=0.0, max_value=12.0,
                    step=0.5, key="finder_max_ripple_db",
                    help="Maximum peak-to-valley variation in the evaluated low-frequency passband.",
                )
                _state._finder_number_input(
                    "Ripple frequency ceiling (Hz, 0 = off)", min_value=0.0, max_value=500.0,
                    step=5.0, key="finder_max_ripple_freq_hz",
                    help="Ignore response variation above this frequency (e.g. 70-100 Hz for subwoofers). "
                         "Uses sparse sampling above this ceiling for faster search. 0 evaluates the full passband.",
                )
                _state._finder_number_input(
                    "Maximum excursion (× driver Xmax)", min_value=0.0, max_value=3.0,
                    step=0.05, key="finder_excursion_ratio",
                    help="1.0 means cone travel stays within published Xmax; 0 disables the constraint.",
                )
                _state._finder_number_input(
                    "Maximum group delay (ms)", min_value=0.0, max_value=100.0,
                    step=1.0, key="finder_max_gd_ms",
                    help="Maximum allowed low-frequency group delay; 0 disables this constraint.",
                )
            else:
                st.caption(
                    "Advanced constraints are hidden. Enable Advanced mode to set "
                    "F3, MOL, SPL, ripple, excursion and delay limits."
                )
    if _show_advanced_controls():
        with st.expander("Advanced driver filters", expanded=True):
            _state._finder_number_input(
                "Maximum Mms (g, 0 = off)",
                min_value=0.0,
                max_value=2000.0,
                step=1.0,
                key="finder_max_mms_g",
                help="Keep only drivers whose published moving mass Mms is no "
                     "greater than this value. Candidates without Mms are excluded "
                     "while the limit is active; 0 disables.",
            )
            _state._finder_number_input(
                "Maximum Le (mH, 0 = off)",
                min_value=0.0,
                max_value=20.0,
                step=0.01,
                format="%.3f",
                key="finder_max_le_mh",
                help="Keep only drivers whose published nominal/1 kHz voice-coil "
                     "inductance is no greater than this value. Le10k is not "
                     "substituted; candidates without Le are excluded while the "
                     "limit is active. 0 disables.",
            )
            st.checkbox(
                "Fast T/S pre-screening",
                key="finder_fast_prefilter",
                help="Analytically exclude drivers that cannot physically achieve the requested F3 or MOL before running full enclosure simulations, accelerating search speed by up to 10×.",
            )

def _finder_search_blocked(filtered_preset_names: list[str]) -> bool:
    """Return whether the Finder inputs are insufficient for a valid search."""
    _, only_infinite_baffle = _catalog._finder_load_context()
    return (
        not filtered_preset_names
        or float(_state._finder_value("finder_f_max")) <= float(_state._finder_value("finder_f_min"))
        or (
            not only_infinite_baffle
            and float(_state._finder_value("finder_volume_l")) <= 0.0
        )
    )

def _render_find_driver_actions(filtered_preset_names: list[str]) -> None:
    """Render the live Finder summary; the workspace owns the single CTA."""
    finder_load_types, only_infinite_baffle = _catalog._finder_load_context()

    finder_volume_l = float(_state._finder_value("finder_volume_l"))
    display_loads = [
        "Bass reflex (PR)"
        if item == "Bass reflex" and _state._reflex_uses_passive_radiator(finder=True)
        else item
        for item in finder_load_types
    ]
    load_label = " + ".join(display_loads) if len(display_loads) <= 2 else f"{len(display_loads)} loads"
    st.caption(
        f"Scans all {len(filtered_preset_names)} matching presets · {load_label}"
        + ("" if only_infinite_baffle else f" · ≤ {finder_volume_l:.1f} L")
    )
    if _show_advanced_controls():
        st.toggle(
            "Show data coverage",
            key="finder_show_coverage",
            help="Per-field completeness of the filtered catalog. Missing values "
                 "keep conservative fallbacks and appear as em dashes in the "
                 "ranking table.",
        )
        if st.session_state.get("finder_show_coverage"):
            summary = _catalog._driver_coverage_summary(tuple(filtered_preset_names))
            if summary:
                st.caption(
                    f"Optional-parameter coverage · {summary['Drivers']:,} drivers"
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"Field": label, "Present %": value}
                            for label, value in summary.items()
                            if label != "Drivers"
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Present %": st.column_config.ProgressColumn(
                            "Present %", min_value=0, max_value=100, format="%d%%",
                        ),
                    },
                )

def _finder_total_volume_l(row: dict | pd.Series) -> float:
    """Return one comparable enclosure-volume value for a Finder result."""
    load_type = str(row.get("Load", row.get("_load_type", "")))

    def finite_value(name: str) -> float:
        try:
            value = float(row.get(name, np.nan))
        except (TypeError, ValueError):
            return float("nan")
        return value if np.isfinite(value) else float("nan")

    if load_type in {"Bass reflex", "Sealed"}:
        return finite_value("Vb L")
    if load_type == "Bandpass 4th order":
        values = (finite_value("Vs L"), finite_value("Vp L"))
    elif load_type == "Bandpass 6th order":
        values = (finite_value("Vr L"), finite_value("Vp L"))
    elif load_type == "Bandpass 8th order":
        values = (finite_value("V1 L"), finite_value("V2 L"), finite_value("V3 L"))
    elif load_type == "DCCAV":
        values = (finite_value("Vh L"), finite_value("Vl L"))
    else:
        return float("nan")
    return float(sum(values)) if all(np.isfinite(values)) else float("nan")

def _finder_per_load_stats_str(stats: object) -> str:
    """Return the compact per-load seek-time/evaluations breakdown, if recorded."""
    if not isinstance(stats, dict):
        return ""
    try:
        parts = []
        for load_name, load_stat in (stats.get("loads") or {}).items():
            if not isinstance(load_stat, dict):
                continue
            piece = (
                f"{load_name}: {int(load_stat.get('usable', 0))}"
                f"/{int(load_stat.get('attempted', 0))}"
            )
            load_evals = int(load_stat.get("evaluations_per_driver", 0) or 0)
            if load_evals > 0:
                piece += f" · {load_evals} evals/drv"
            load_elapsed = float(load_stat.get("elapsed_s", 0.0) or 0.0)
            if load_elapsed > 0.0:
                piece += f" · {load_elapsed:.2f} s"
            parts.append(piece)
    except (TypeError, ValueError):
        return ""
    return " | ".join(parts)

def _render_finder_run_statistics(container=None) -> None:
    """Keep the last measured Bass Match throughput visible and persistent.

    ``container`` is an ``st.empty()`` placeholder created before a run so the
    completed statistics can be filled in place without a full-page rerun.
    """
    stats = st.session_state.get("finder_last_run_stats")
    if not isinstance(stats, dict) or not stats:
        return
    try:
        elapsed_s = float(stats.get("elapsed_s", 0.0))
        ms_per_sim = float(
            stats.get(
                "milliseconds_per_simulation",
                stats.get("milliseconds_per_driver", 0.0),
            )
        )
        ms_per_driver = float(stats.get("milliseconds_per_driver", 0.0))
        simulations_per_second = float(
            stats.get("simulations_per_second", 0.0)
        )
        unique_drivers = int(stats.get("unique_drivers", 0))
        simulations = int(stats.get("simulations", 0))
        actual_sims = int(stats.get("actual_acoustic_simulations", 0))
        evals_per_drv = int(stats.get("evaluations_per_driver", 60))
        profile_name = str(stats.get("search_profile", "Standard"))
        evaluations_per_load = stats.get("evaluations_per_load") or {}
        load_budgets = sorted({
            int(budget) for budget in evaluations_per_load.values() if int(budget) > 0
        })
    except (TypeError, ValueError):
        return

    if elapsed_s <= 0.0:
        return

    if load_budgets:
        evals_label = (
            f"{load_budgets[0]}"
            if load_budgets[0] == load_budgets[-1]
            else f"{load_budgets[0]}–{load_budgets[-1]}"
        )
    else:
        evals_label = str(evals_per_drv)
    actual_str = f" · 🔬 <strong>{actual_sims:,}</strong> solves ({evals_label} evals/drv · <em>{profile_name}</em>)" if actual_sims > 0 else ""
    per_load_str = _finder_per_load_stats_str(stats)
    load_str = (
        f" · 🧩 <strong>Per load:</strong> {per_load_str}"
        if per_load_str else ""
    )
    credit_mult = _ranking.search_profile_credit_multiplier(profile_name)
    credits_consumed = simulations * credit_mult
    target = container if container is not None else st
    target.markdown(
        "<div style='margin: 8px 0 2px 0; padding: 6px 12px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.28); border-radius: 6px; font-size: 0.82rem; color: #d1d5db;'>"
        f"⏱️ <strong>Seek time:</strong> {elapsed_s:.2f} s total "
        f"<span style='color: #10b981;'>({ms_per_sim:.1f} ms/sim · {simulations_per_second:.0f} sim/s · {ms_per_driver:.1f} ms/driver)</span>"
        f" · 💳 <strong>{credits_consumed:,} credits</strong> ({simulations:,} candidates · {credit_mult}× {profile_name})"
        f"{actual_str}"
        f"{load_str}"
        "</div>",
        unsafe_allow_html=True,
    )

def _render_bass_match_hero(
    filtered_preset_names: list[str],
) -> list[str]:
    """Render the Finder promise, live brief and single primary action."""
    selected_preset_names = _catalog._selected_library_preset_names(
        filtered_preset_names
    )
    match_preset_names = (
        selected_preset_names
        if selected_preset_names
        else filtered_preset_names
    )
    candidate_pools, prefilter_stats = _catalog._finder_prefilter(
        match_preset_names
    )
    prequalified_names = {
        name
        for names in candidate_pools.values()
        for name in names
    }
    constraints = _catalog._finder_brief_constraints(len(selected_preset_names))

    acc = _account._get_current_user_account()
    is_admin = bool(acc.is_admin) if acc else False
    credits_balance = acc.credits_balance if acc else 2500
    credits_quota = acc.credits_monthly_quota if acc else 2500

    finder_search_profile = str(_state._finder_value("finder_search_profile"))
    credit_mult = _ranking.search_profile_credit_multiplier(finder_search_profile)
    run_credits = int(prefilter_stats["eligible_simulations"] * credit_mult)
    # Enforce strict blocking only in SaaS mode for non-admin accounts
    enforce_credits = _runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None and not is_admin
    has_enough_credits = (not enforce_credits) or (credits_balance >= run_credits or run_credits == 0)

    run_requested = False
    with st.container(border=True, key="bass_match_brief"):
        h_col1, h_col2 = st.columns([2.5, 1.5], vertical_alignment="center")
        with h_col1:
            st.markdown("#### Bass Match · Your bass brief")
        with h_col2:
            st.markdown(
                "<div style='text-align: right;'><span class='lf-quota-pill'>"
                f"Credits available: <strong>{credits_balance:,} / {credits_quota:,}</strong>"
                f" · This run: <strong>{run_credits:,} credits</strong>"
                f" <small>({prefilter_stats['eligible_simulations']:,} drv · {credit_mult}× {finder_search_profile})</small>"
                "</span></div>",
                unsafe_allow_html=True,
            )
        b1, b2, b3, b4 = st.columns(
            [1.2, 1.2, 1.2, 1.2],
            vertical_alignment="center",
        )
        b1.metric(
            "Pre-qualified",
            f"{len(prequalified_names):,} / "
            f"{prefilter_stats['unique_drivers']:,}",
            help="Drivers that pass cheap pre-simulation checks for at least "
            "one active load.",
        )
        b2.metric(
            "Ready simulations",
            f"{prefilter_stats['eligible_simulations']:,}",
        )
        b3.metric(
            "Skipped a priori",
            f"{prefilter_stats['rejected_simulations']:,}",
        )
        b4.metric(
            "Duplicates removed",
            f"{prefilter_stats['duplicate_rows']:,}",
        )
        _catalog._render_finder_constraint_grid(constraints)
        finder_stats_slot = st.empty()
        _render_finder_run_statistics(finder_stats_slot)
        if match_preset_names and not prequalified_names:
            st.warning(
                "No driver passes the pre-simulation checks. Lower Minimum "
                "SPL, change the driver configuration or relax the library filters."
            )
        if not has_enough_credits:
            shortfall = max(0, run_credits - credits_balance)
            st.error(
                f"Insufficient credits: this scan requires **{run_credits:,} credits**, but your balance is **{credits_balance:,} credits** "
                f"(shortfall: **{shortfall:,} credits**). "
                "Refine your filters, choose fewer drivers, or purchase credits / upgrade below."
            )
            c_buy1, _ = st.columns([2.2, 2.8])
            with c_buy1:
                _projects._render_credits_purchase_popover(
                    acc,
                    key="bm_buy_credits_err_popover",
                    label=f"🚀 Subscribe / Buy Credits ({shortfall:,} needed)",
                    shortfall=shortfall,
                )
    run_requested = st.button(
        _constants._FINDER_CTA_LABEL,
        type="primary",
        width="stretch",
        disabled=_finder_search_blocked(filtered_preset_names) or not has_enough_credits,
        key="finder_run_search_main",
    )
    if run_requested:
        if acc and run_credits > 0:
            _runtime._ACCOUNT_STORE.deduct_credits(acc.email or acc.uid, run_credits)
            _account._get_current_user_account.cache_clear()
        _run_find_driver_search(
            match_preset_names, filtered_preset_names,
            stats_slot=finder_stats_slot,
        )
    return match_preset_names

@st.fragment
def _render_candidate_pool(filtered_preset_names: list[str]) -> None:
    """Keep raw catalog browsing secondary; opening it reruns only this fragment."""
    selected_count = len(
        _catalog._selected_library_preset_names(filtered_preset_names)
    )
    pool_suffix = (
        f"{selected_count} selected"
        if selected_count
        else f"{len(filtered_preset_names):,} available"
    )
    pool_expander = st.expander(
        f"Candidate pool · {pool_suffix}",
        expanded=not filtered_preset_names,
        key="finder_candidate_pool_expander",
        on_change="rerun",
    )
    # A collapsed expander normally still executes and serializes its entire
    # body. The library can contain 500 visible rows, so only build/send it
    # after the user explicitly opens the pool.
    if pool_expander.open:
        with pool_expander:
            _catalog._render_driver_library(filtered_preset_names)

def _queue_finder_design_selection(
    selected_designs: list[dict],
    voltage_v: float,
) -> None:
    """Queue Finder selection before the rerun so Box Design opens directly."""
    if len(selected_designs) == 1:
        selected = selected_designs[0]
        st.session_state["batch_pending_result"] = {
            "row": selected["row"],
            "load_type": selected["load_type"],
            "voltage_v": float(voltage_v),
        }
    elif selected_designs:
        st.session_state["batch_pending_comparison"] = {
            "designs": selected_designs,
            "voltage_v": float(voltage_v),
        }

def _render_find_driver_workspace(filtered_preset_names: list[str]) -> None:
    """Render Finder results and candidate application, separate from inputs."""
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    _render_bass_match_hero(filtered_preset_names)

    finder_volume_l = float(st.session_state.get("finder_volume_l", 0.0))
    # Old/restored sessions can contain an empty load list even though the
    # Finder falls back to the active design load for both its brief and run.
    # Compare against that same effective load context, or every successful
    # fallback run is immediately hidden as an input change.
    finder_loads = tuple(_catalog._finder_load_context()[0])
    finder_resonator = str(st.session_state.get(
        "finder_reflex_resonator_type", _constants._RESONATOR_PORT))
    batch_rows = st.session_state.get("batch_results", [])
    context = st.session_state.get("batch_result_context", ())
    current_min_spl_db = float(
        st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    current_min_mol_f3_db = float(
        st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0)
    current_max_f3_hz = float(
        st.session_state.get("finder_max_f3_hz", 0.0) or 0.0)
    current_max_mms_g = float(
        st.session_state.get("finder_max_mms_g", 0.0) or 0.0)
    current_max_le_mh = float(
        st.session_state.get("finder_max_le_mh", 0.0) or 0.0)
    current_signature = _catalog._finder_result_context_signature(filtered_preset_names)
    if batch_rows and len(context) >= 11 and (
        len(context) <= 16
        or str(context[16]) != _constants._FINDER_CONTEXT_FILTERED_POOL_VERSION
    ):
        # Replace legacy candidate-selection and short-lived control-only
        # signatures with the stable filtered-pool context. This keeps saved
        # projects and live pre-fix sessions usable across the source reload.
        legacy_context = list(context[:15])
        try:
            legacy_scan_count = max(0, int(legacy_context[2]))
        except (TypeError, ValueError):
            legacy_scan_count = len(batch_rows)
        legacy_stat_defaults = {
            11: legacy_scan_count,
            12: legacy_scan_count,
            13: 0,
            14: 0,
        }
        for index, default in legacy_stat_defaults.items():
            if len(legacy_context) <= index:
                legacy_context.append(default)
                continue
            try:
                legacy_context[index] = int(legacy_context[index])
            except (TypeError, ValueError):
                # Also repairs sessions normalized by the short-lived buggy
                # migration, where the pool signature occupied index 11.
                legacy_context[index] = default
        context = (
            *legacy_context,
            current_signature,
            _constants._FINDER_CONTEXT_FILTERED_POOL_VERSION,
        )
        st.session_state["batch_result_context"] = context
    current_controls_signature = _catalog._finder_controls_signature()
    restored_controls_signature = str(st.session_state.get(
        "_restored_bass_match_controls_signature",
        "",
    ))
    if batch_rows and restored_controls_signature == "pending":
        restored_controls_signature = current_controls_signature
        st.session_state["_restored_bass_match_controls_signature"] = (
            restored_controls_signature
        )
    restored_results_match = bool(batch_rows) and (
        restored_controls_signature == current_controls_signature
    )
    context_matches = not (
        len(context) < 2
        or tuple(context[:2]) != (finder_loads, finder_volume_l)
        or (len(context) > 5 and str(context[5]) != finder_resonator)
        or (len(context) > 6 and float(context[6]) != current_min_spl_db)
        or (len(context) <= 6 and current_min_spl_db > 0.0)
        or (len(context) > 7 and float(context[7]) != current_min_mol_f3_db)
        or (len(context) <= 7 and current_min_mol_f3_db > 0.0)
        or (len(context) > 8 and float(context[8]) != current_max_mms_g)
        or (len(context) <= 8 and current_max_mms_g > 0.0)
        or (len(context) > 9 and float(context[9]) != current_max_le_mh)
        or (len(context) <= 9 and current_max_le_mh > 0.0)
        or len(context) <= 10
        or int(context[10]) != _constants._FINDER_RANKING_VERSION
        or (
            len(context) > 15
            and str(context[15]) != current_signature
            and not restored_results_match
        )
    )
    if not context_matches:
        batch_rows = []
    if not batch_rows:
        if context and not context_matches:
            st.info(
                "Bass Match inputs changed. Run Bass Match again to update "
                "the results."
            )
        if st.session_state.get("batch_search_completed", False) and context_matches:
            st.subheader("No Bass Match result")
            if current_max_f3_hz > 0.0:
                st.warning(
                    f"No candidate reached an F3 at or below "
                    f"{current_max_f3_hz:.1f} Hz with the current enclosure "
                    "and filters. Raise Maximum F3 or relax the other constraints."
                )
            elif current_min_spl_db > 0.0:
                st.warning(
                    f"No candidate reached the minimum SPL of "
                    f"{current_min_spl_db:.1f} dB with the current enclosure, "
                    "voltage and filters. Lower Minimum SPL or raise the comparison voltage."
                )
            elif current_min_mol_f3_db > 0.0:
                st.warning(
                    f"No candidate reached the minimum MOL at F3 of "
                    f"{current_min_mol_f3_db:.1f} dB with the current enclosure, "
                    "voltage and filters. Lower Minimum MOL at F3 or relax the filters."
                )
            else:
                run_stats = st.session_state.get("finder_last_run_stats", {})
                load_stats = run_stats.get("loads", {})
                dccav_stats = load_stats.get("DCCAV", {})
                reflex_stats = load_stats.get("Bass reflex", {})
                load_summary = ", ".join(
                    f"{load}: {stats.get('usable', 0)}/{stats.get('attempted', 0)}"
                    for load, stats in load_stats.items()
                )
                if load_summary and all(
                    stats.get("usable", 0) == 0
                    for stats in load_stats.values()
                ):
                    st.warning(
                        "Nessun carico ha prodotto un risultato utilizzabile "
                        f"({load_summary}). Controlla il driver configuration, "
                        "il volume massimo e i vincoli del progetto."
                    )
                elif (
                    dccav_stats.get("attempted", 0) > 0
                    and dccav_stats.get("usable", 0) == 0
                    and reflex_stats.get("usable", 0) > 0
                ):
                    st.warning(
                        "DCCAV non ha trovato un allineamento costruibile per "
                        f"nessuna delle {dccav_stats['attempted']} candidate entro "
                        f"{finder_volume_l:.0f} L; il Bass reflex invece è fattibile. "
                        "Prova solo Bass reflex, aumenta il volume massimo o rilassa "
                        "i vincoli di ripple/porta."
                    )
                elif dccav_stats.get("attempted", 0) > 0 and dccav_stats.get("usable", 0) == 0:
                    st.warning(
                        "Le candidate DCCAV sono state valutate, ma nessuna ha "
                        f"prodotto un allineamento costruibile entro {finder_volume_l:.0f} L. "
                        "Aumenta il volume massimo o rilassa i vincoli di progetto."
                    )
                elif load_summary:
                    st.warning(
                        "Nessun risultato dopo il filtro prestazionale. "
                        f"Esiti per carico: {load_summary}. "
                        "Riduci i vincoli SPL/MOL/F3 oppure riesegui Bass Match."
                    )
                else:
                    st.warning(
                        "No usable candidate satisfies the current enclosure and constraints."
                    )
        _render_candidate_pool(filtered_preset_names)
        return

    batch_rows = _catalog._refresh_finder_result_catalog_metadata(batch_rows)
    st.session_state["batch_results"] = batch_rows

    selection_cta = st.empty()
    display_finder_loads = [
        "Bass reflex (PR)"
        if item == "Bass reflex" and finder_resonator == _constants._RESONATOR_PR
        else item
        for item in finder_loads
    ]
    load_summary = (
        " + ".join(display_finder_loads)
        if len(display_finder_loads) <= 2
        else f"{len(display_finder_loads)} loads"
    )
    objective = str(context[4]) if len(context) > 4 else str(st.session_state.get("finder_objective", "Max extension"))
    volume_summary = (
        "" if finder_loads == ("Infinite baffle",)
        else f" · ≤ {finder_volume_l:.1f} L"
    )
    run_stats = st.session_state.get("finder_last_run_stats")
    seek_time_str = ""
    if isinstance(run_stats, dict) and run_stats.get("elapsed_s"):
        try:
            el_s = float(run_stats["elapsed_s"])
            ms_sim = float(
                run_stats.get(
                    "milliseconds_per_simulation",
                    run_stats.get("milliseconds_per_driver", 0.0),
                )
            )
            sims_sec = float(run_stats.get("simulations_per_second", 0.0))
            if el_s > 0:
                seek_time_str = f" · ⏱️ Seek time: {el_s:.2f} s ({ms_sim:.1f} ms/sim · {sims_sec:.0f} sim/s)"
        except (TypeError, ValueError):
            seek_time_str = ""
    per_load_summary = _finder_per_load_stats_str(run_stats)
    if per_load_summary:
        per_load_summary = f" · 🧩 Per load: {per_load_summary}"

    st.caption(
        f"{len(batch_rows)} usable candidates · "
        + (
            f"{int(context[11])}/{int(context[12])} simulations after pre-filter · "
            if len(context) > 12
            else f"{context[2]} scanned presets · "
        )
        + f"{load_summary}{volume_summary} · {objective}"
        + f"{seek_time_str}"
        + f"{per_load_summary}"
    )
    full_df = pd.DataFrame(batch_rows)
    if "_load_type" in full_df.columns:
        full_df = full_df.rename(columns={"_load_type": "Load"})
    if "Manufacturer" in full_df.columns:
        manufacturer_counts = (
            full_df["Manufacturer"].astype(str).value_counts().sort_index()
        )
        st.caption(
            "Risultati per marca: "
            + " · ".join(
                f"{manufacturer} {int(count)}"
                for manufacturer, count in manufacturer_counts.items()
            )
        )
    full_df["Vtot L"] = full_df.apply(
        _finder_total_volume_l, axis=1
    )
    for name, default in (
        ("Load", ""), ("Price", np.nan), ("Currency", ""), ("Buy", ""),
        ("Ripple dB", np.nan), ("Response", None), ("Class", ""),
        ("Size in", np.nan), ("Sd cm²", np.nan),
        ("Resonator", ""), ("Mms g", np.nan), ("Le10k mH", np.nan),
        ("MOL @ F3 dB", np.nan), ("Data", ""), ("Data %", np.nan),
    ):
        if name not in full_df.columns:
            full_df[name] = default

    selected_price_currency = str(
        st.session_state.get("preset_price_currency", "EUR")
    )
    if selected_price_currency:
        full_df = _catalog._normalize_price_frame(full_df, selected_price_currency)
    full_df["Class"] = full_df["Class"].map(_catalog._driver_class_label)

    value_currency = _catalog._finder_price_currency(full_df)
    rank_mode = _constants._FINDER_RANK_F3
    if value_currency:
        rank_mode = st.radio(
            "Rank by",
            _constants._FINDER_RANK_MODES,
            horizontal=True,
            key="finder_rank_mode",
            help="Best value re-sorts the scan by F3 × price: the cheapest way "
                 "to reach deep bass ranks first. Use the sidebar price filter "
                 "to cap the budget.",
        )
    if rank_mode == _constants._FINDER_RANK_VALUE and value_currency:
        full_df = _catalog._value_sorted_frame(full_df, value_currency)
        st.caption(
            f"Best value = lowest F3 × price in {value_currency}; candidates "
            f"without a {value_currency} price keep the F3 order at the bottom."
        )
    batch_df = full_df
    identities = batch_df["Driver"].map(_catalog._driver_preset_identity_fields)
    batch_df["Manufacturer"] = identities.map(lambda value: value[0])
    batch_df["Part number"] = identities.map(lambda value: value[1])

    # Keep the compact Finder layout stable: identity/load, enclosure and
    # commercial metadata first, followed by the performance metrics.
    columns = ["Driver", "Manufacturer", "Part number", "Load"]
    if batch_df["Resonator"].fillna("").astype(bool).any():
        columns.append("Resonator")
    if batch_df["Size in"].notna().any():
        columns.append("Size in")
    if batch_df["Vtot L"].notna().any():
        columns.append("Vtot L")
    if batch_df["Price"].notna().any():
        columns.append("Price")
        columns.append("Currency")
        if "Value" in batch_df.columns and batch_df["Value"].notna().any():
            columns.append("Value")
    if batch_df["Buy"].fillna("").astype(bool).any():
        columns.append("Buy")
    columns.extend(["F3 Hz", "MOL @ F3 dB", "Peak dB"])
    if batch_df["Response"].map(lambda v: bool(v) if isinstance(v, list) else False).any():
        columns.append("Response")
    columns.append("Min ohm")
    if batch_df["Mms g"].notna().any():
        columns.append("Mms g")
    if batch_df["Le10k mH"].notna().any():
        columns.append("Le10k mH")
    if "Data" in batch_df.columns and (batch_df["Data"] != "Complete").any():
        batch_df["Data"] = batch_df["Data"].map(
            {"Complete": "✓", "Partial": "⚠", "Incomplete": "⛔"}
        ).fillna("")
        columns.extend(["Data", "Data %"])

    display_df = _state._clean_display_table_frame(batch_df[columns])
    columns = list(display_df.columns)
    table_state = st.dataframe(
        display_df,
        # Use the complete result-pane width; users can still resize columns
        # interactively without leaving an unused strip beside the table.
        width="stretch",
        height=420,
        hide_index=True,
        key=f"batch_results_table_{'value' if 'Value' in columns else 'f3'}",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Driver": None,
            "Manufacturer": st.column_config.TextColumn("Mfr"),
            "Part number": st.column_config.TextColumn("Part #"),
            "F3 Hz": st.column_config.NumberColumn(format="%.1f"),
            "MOL @ F3 dB": st.column_config.NumberColumn(
                "MOL",
                format="%.1f",
                help="Maximum excursion/thermal limited output interpolated at F3.",
            ),
            "Peak dB": st.column_config.NumberColumn(format="%.1f"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Currency": st.column_config.TextColumn("CUR"),
            "Value": st.column_config.NumberColumn(
                "Value (F3 × price)", format="%.0f",
                help="Lower is better: cheapest path to deep bass.",
            ),
            "Min ohm": st.column_config.NumberColumn("Min Z", format="%.2f"),
            "Mms g": st.column_config.NumberColumn(format="%.1f"),
            "Le10k mH": st.column_config.NumberColumn(format="%.3f"),
            "Data": st.column_config.TextColumn(
                "Data",
                help="Optional-parameter coverage: ✓ complete, ⚠ partial, "
                     "⛔ incomplete. Missing values keep their conservative "
                     "fallback and are shown as em dashes.",
            ),
            "Data %": st.column_config.NumberColumn(
                "Data %", format="%.0f%%",
                help="Share of optional engineering/commercial fields present "
                     "for this driver (Xmax, Pe, Le, Mms, Bl, Cms, Le10k, "
                     "nominal size, price).",
            ),
            "Size in": st.column_config.NumberColumn(
                "Size (in)", format="%.1f"
            ),
            "Vtot L": st.column_config.NumberColumn(
                "Vtot (L)", format="%.2f"
            ),
            "Buy": st.column_config.LinkColumn(display_text="Buy"),
            "Response": st.column_config.LineChartColumn(
                "Response (rel dB)", y_min=_acoustics.SPARKLINE_FLOOR_DB, y_max=0.0,
            ),
        },
    )
    csv_columns = [
        name for name in columns if name not in {"Driver", "Response"}
    ]
    st.download_button(
        "Download candidate CSV",
        batch_df[csv_columns].to_csv(index=False).encode("utf-8"),
        "load_forge_candidates.csv",
        "text/csv",
        width="stretch",
    )

    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    selected_indices = [
        int(index)
        for index in selected_rows
        if 0 <= int(index) < len(batch_df)
    ]
    selected_designs = [
        {
            "row": batch_df.iloc[index].to_dict(),
            "load_type": str(
                batch_df.iloc[index].get("Load", load_type)
            ),
        }
        for index in selected_indices
    ]
    comparison_count = len(selected_designs)
    too_many = comparison_count > _constants._MAX_COMPARISON_DESIGNS
    cta_label = (
        f"Compare {comparison_count} designs in Box Design"
        if comparison_count > 1
        else "Open this design in Box Design"
    )
    cta_disabled = (
        not selected_designs
        or too_many
    )
    with selection_cta.container():
        st.button(
            cta_label,
            type="secondary" if not selected_designs else "primary",
            width="stretch",
            key="finder_open_selected_design",
            disabled=cta_disabled,
            on_click=_queue_finder_design_selection,
            args=(selected_designs, float(_state._finder_value("finder_voltage"))),
        )

    if not selected_indices:
        with st.container(key="emerald_info_candidate_selection"):
            st.caption(
                "Select one match to preview it, or select 2–8 matches to "
                "compare them in Box Design."
            )
        _render_candidate_pool(filtered_preset_names)
        return
    if len(selected_indices) > 1:
        with st.container(border=True):
            st.markdown(
                f"#### Design comparison · {comparison_count} selected"
            )
            st.caption(
                "Every selected match becomes an independently editable Box "
                "Design tab. Switch tabs to change its driver, load or box; "
                "all tabs stay overlaid at the same voltage."
            )
            if too_many:
                st.warning(
                    f"Select at most {_constants._MAX_COMPARISON_DESIGNS} designs."
                )
        _render_candidate_pool(filtered_preset_names)
        return

    selected_index = selected_indices[0]
    selected_row = batch_df.iloc[selected_index].to_dict()
    row_load_type = str(selected_row.get("Load", load_type))
    with st.container(border=True):
        st.markdown(
            "#### Match preview · "
            f"{_catalog._driver_preset_display_label(str(selected_row['Driver']))} · "
            f"{row_load_type}"
        )
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("F3", f"{float(selected_row['F3 Hz']):.1f} Hz")
        mol_at_f3 = float(selected_row.get("MOL @ F3 dB", np.nan))
        p2.metric(
            "MOL @ F3",
            f"{mol_at_f3:.1f} dB" if np.isfinite(mol_at_f3) else "—",
        )
        p3.metric("Peak LF SPL", f"{float(selected_row['Peak dB']):.1f} dB")
        p4.metric("Min impedance", f"{float(selected_row['Min ohm']):.2f} Ω")
        total_volume_l = _finder_total_volume_l(selected_row)
        if np.isfinite(total_volume_l):
            st.caption(f"Vtot {total_volume_l:.2f} L")
        elif row_load_type == "Infinite baffle":
            st.caption("Infinite baffle · no enclosure volume")
    _render_candidate_pool(filtered_preset_names)
