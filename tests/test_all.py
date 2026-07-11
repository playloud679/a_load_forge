"""
Load Forge focused test suite.

The project is now a DCCAV simulator, so this runner intentionally covers only
the active audio-domain engine and its small public surface.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import dccav as _dccav


PASS = 0
FAIL = 0
SKIP = 0


def _parse_args():
    parser = argparse.ArgumentParser(description="Run Load Forge tests.")
    parser.add_argument(
        "--match", "-m", action="append", default=[],
        help="Run only tests whose label contains this text. May be repeated.")
    parser.add_argument("--list", action="store_true", help="List matching tests.")
    return parser.parse_args()


ARGS = _parse_args()
MATCHES = [m.casefold() for m in ARGS.match]


def _selected(label: str) -> bool:
    return not MATCHES or any(m in label.casefold() for m in MATCHES)


def test(label, fn):
    global PASS, FAIL, SKIP
    if not _selected(label):
        SKIP += 1
        return
    if ARGS.list:
        print(f"  - {label}")
        PASS += 1
        return
    try:
        fn()
        print(f"  OK {label}")
        PASS += 1
    except Exception:
        print(f"  FAIL {label}")
        traceback.print_exc()
        FAIL += 1


def _kef_b110_ts():
    return _dccav.get_driver_preset("KEF B110B article example")


def _beyma_ts():
    return _dccav.get_driver_preset("Beyma 12CMV2")


print("\n=== Acoustic-load core ===")


def _check_sd_from_diameter():
    sd = _dccav.sd_from_diameter(104.0)
    assert abs(sd - 84.95) < 0.05, f"Sd={sd:.2f} cm2"


test("DCCAV Sd helper converts diameter to area", _check_sd_from_diameter)


def _check_presets_are_available():
    names = _dccav.driver_preset_names()
    expected = {
        "KEF B110B article example",
        "Beyma 12CMV2",
        "Beyma 12G40",
        "Beyma 12LX60V2",
        "Beyma 12BR70",
        "Beyma 12MC500",
        "Beyma 12MCS500",
        "Beyma 12WRS400",
        "Beyma 12P80Nd/V2",
        "Beyma 12P1000/Nd",
        "Beyma 12LEX1000Fe",
        "Beyma 12LEX1300Nd",
        "Beyma 12CMV3",
        "Turbosound TS-12W350/8W",
        "Turbosound TS-15W300/8A",
        "Scan-Speak 30W/4558T00",
        "Scan-Speak 15W/4531G00",
        "Dayton Audio RSS315HO-4",
        "SB Audience BIANCO-12OB150-01",
        "LaVoce WSF122.02",
        "LaVoce WSF122.50",
        "Aiyima 4ohm 5w 40mm black",
        "Aiyima 6ohm 8w 56mm",
        "Aiyima 4ohm 20w 58mm",
        "Aiyima 4ohm 20w 1.75in",
        "Aiyima 4ohm 5w 40mm zinc",
        "Aiyima 4ohm 10w 40mm",
        "Aiyima 8ohm 15w 3in flat",
        "Aiyima 8ohm 4w 1in for harman",
        "Aiyima 4ohm 12w 2in",
        "Aiyima 8ohm 3w 40mm",
        "Aiyima 4ohm 3w 1in",
        "Aiyima 4ohm 3w 36mm",
        "Aiyima 4ohm 10w 53mm",
        "Aiyima 10ohm 10w 50mm",
        "Aiyima 4ohm 10w 53mm LY1124-2",
        "Aiyima 4ohm 2w 33mm",
        "Aiyima 8ohm 1w 25mm altavoz portatil",
        "Aiyima 8ohm 3w 30mm altavoz portatil",
        "Aiyima 4ohm 5w 1.5in",
        "MarkAudio CHR-70",
    }
    assert expected.issubset(names), set(names)
    assert _dccav.get_driver_preset("Beyma 12G40").sd_cm2 == 530.0
    assert _dccav.get_driver_preset("Beyma 12BR70").fs_hz == 31.0
    assert _dccav.get_driver_preset("Beyma 12MCS500").le_mh == 1.1
    assert _dccav.get_driver_preset("Beyma 12WRS400").qts == 0.29
    assert _dccav.get_driver_preset("Beyma 12LEX1300Nd").xmax_mm == 11.0
    assert _dccav.get_driver_preset("Turbosound TS-12W350/8W").fs_hz == 61.0
    assert _dccav.get_driver_preset("Turbosound TS-12W350/8W").vas_l == 19.26
    assert _dccav.get_driver_preset("Turbosound TS-12W350/8W").pe_w == 350.0
    assert _dccav.get_driver_preset("Turbosound TS-15W300/8A").vas_l == 130.2
    assert _dccav.get_driver_preset("Turbosound TS-15W300/8A").sd_cm2 == 865.7
    assert _dccav.get_driver_preset("Turbosound TS-15W300/8A").pe_w == 300.0
    assert _dccav.get_driver_preset("Scan-Speak 30W/4558T00").fs_hz == 17.0
    assert _dccav.get_driver_preset("Scan-Speak 30W/4558T00").vas_l == 197.0
    assert _dccav.get_driver_preset("Scan-Speak 30W/4558T00").xmax_mm == 12.5
    assert _dccav.get_driver_preset("Scan-Speak 15W/4531G00").fs_hz == 40.0
    assert _dccav.get_driver_preset("Scan-Speak 15W/4531G00").sd_cm2 == 95.0
    assert _dccav.get_driver_preset("Scan-Speak 15W/4531G00").pe_w == 60.0
    assert _dccav.get_driver_preset("Dayton Audio RSS315HO-4").re_ohm == 3.2
    assert _dccav.get_driver_preset("Dayton Audio RSS315HO-4").pe_w == 700.0
    assert _dccav.get_driver_preset("SB Audience BIANCO-12OB150-01").qts == 0.63
    assert _dccav.get_driver_preset("SB Audience BIANCO-12OB150-01").sd_cm2 == 539.1
    assert _dccav.get_driver_preset("LaVoce WSF122.02").re_ohm == 5.2
    assert _dccav.get_driver_preset("LaVoce WSF122.50").bl_tm == 17.1
    assert _dccav.get_driver_preset("Aiyima 4ohm 5w 40mm black").fs_hz == 153.6
    assert abs(_dccav.get_driver_preset("Aiyima 4ohm 5w 40mm black").sd_cm2 - 7.40229915) < 1e-9
    assert _dccav.get_driver_preset("Aiyima 4ohm 10w 53mm LY1124-2").vas_l == 0.22
    assert _dccav.get_driver_preset("Aiyima 4ohm 5w 1.5in").bl_tm == 2.937
    assert _dccav.get_driver_preset("MarkAudio CHR-70").sd_cm2 == 50.2
    assert _dccav.get_driver_preset("MarkAudio CHR-70").cms_mm_per_n == 1.44
    assert _dccav.get_driver_preset("MarkAudio CHR-70").pe_w == 20.0
    beyma_info = _dccav.driver_preset_info("Beyma 12CMV2")
    assert beyma_info.source == "Built-in"
    assert beyma_info.brand == "Beyma"
    lsdb_names = [name for name in names if name.startswith("LSDB: ")]
    if lsdb_names:
        lsdb_info = _dccav.driver_preset_info(lsdb_names[0])
        assert lsdb_info.source == "Loudspeaker Database"
        assert lsdb_info.brand
        _dccav.complete_driver(_dccav.get_driver_preset(lsdb_names[0]))
    try:
        _dccav.get_driver_preset("missing")
    except ValueError as exc:
        assert "Unknown driver preset" in str(exc)
    else:
        raise AssertionError("unknown preset was accepted")


test("DCCAV driver presets are named and validated", _check_presets_are_available)


def _check_article_alignment():
    a = _dccav.suggest_alignment(_kef_b110_ts())
    assert abs(a.vh_l - 3.09) < 0.03, f"Vh={a.vh_l:.2f} L"
    assert abs(a.vl_l - 6.23) < 0.05, f"Vl={a.vl_l:.2f} L"
    assert abs(a.fh_hz - 162.2) < 0.2, f"fh={a.fh_hz:.2f} Hz"
    assert abs(a.fl_hz - 62.0) < 0.2, f"fl={a.fl_hz:.2f} Hz"
    assert abs(a.f3_hz - 51.5) < 0.2, f"f3={a.f3_hz:.2f} Hz"


test("DCCAV article alignment regression", _check_article_alignment)


def _check_beyma_preset_alignment():
    ts = _beyma_ts()
    assert ts.sd_cm2 == 530.0
    assert ts.mms_g == 54.0
    assert ts.cms_mm_per_n == 0.193
    assert ts.bl_tm == 13.7
    a = _dccav.suggest_alignment(ts)
    assert abs(a.vh_l - 34.42) < 0.03, f"Vh={a.vh_l:.2f} L"
    assert abs(a.vl_l - 69.34) < 0.05, f"Vl={a.vl_l:.2f} L"
    assert abs(a.fh_hz - 127.2) < 0.2, f"fh={a.fh_hz:.2f} Hz"
    assert abs(a.fl_hz - 48.6) < 0.2, f"fl={a.fl_hz:.2f} Hz"


test("DCCAV Beyma 12CMV2 preset alignment", _check_beyma_preset_alignment)


def _check_derived_driver_from_minimal_ts():
    d = _dccav.complete_driver(_kef_b110_ts())
    assert 0.008 < d.sd_m2 < 0.009
    assert d.qes > 0
    assert d.bl_tm > 0
    assert d.cas > 0 and d.mas > 0 and d.rat > 0


test("DCCAV derives driver components from minimal T/S", _check_derived_driver_from_minimal_ts)


def _check_measured_driver_values_are_used():
    d = _dccav.complete_driver(_beyma_ts())
    assert abs(d.mms_kg - 0.054) < 1e-9
    assert abs(d.cms_m_per_n - 0.000193) < 1e-12
    assert abs(d.bl_tm - 13.7) < 1e-12


test("DCCAV uses measured optional driver values", _check_measured_driver_values_are_used)


def _check_rejects_invalid_q_values():
    try:
        _dccav.complete_driver(_dccav.DriverTS(
            fs_hz=50.0, vas_l=20.0, qts=0.5, qms=0.4,
            re_ohm=6.0, sd_cm2=220.0))
    except ValueError as exc:
        assert "Qms" in str(exc)
    else:
        raise AssertionError("invalid Qms <= Qts was accepted")


test("DCCAV rejects invalid Qms/Qts pair", _check_rejects_invalid_q_values)


def _check_simulation_arrays_are_finite():
    ts = _beyma_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _dccav.simulate(ts, box, np.geomspace(15.0, 350.0, 180), voltage_v=2.83)
    for name in (
        "spl_total_db", "spl_driver_db", "spl_port_db", "excursion_mm",
        "impedance_ohm", "port_h_velocity", "port_l_velocity",
        "mil_w", "mol_db",
    ):
        arr = getattr(result, name)
        assert arr.shape == result.frequency_hz.shape, f"{name}: shape mismatch"
        assert np.all(np.isfinite(arr)), f"{name}: non-finite values"
    assert np.nanmax(result.mol_db) > np.nanmax(result.spl_total_db)
    assert np.nanmin(result.mil_w) > 0

    reflex = _dccav.suggest_reflex_alignment(ts)
    reflex_box = _dccav.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    reflex_result = _dccav.simulate_reflex(ts, reflex_box, np.geomspace(15.0, 350.0, 180), voltage_v=2.83)
    for name in (
        "spl_total_db", "spl_driver_db", "spl_port_db", "excursion_mm",
        "impedance_ohm", "port_h_velocity", "port_l_velocity",
        "mil_w", "mol_db",
    ):
        arr = getattr(reflex_result, name)
        assert arr.shape == reflex_result.frequency_hz.shape, f"reflex {name}: shape mismatch"
        assert np.all(np.isfinite(arr)), f"reflex {name}: non-finite values"
    assert np.all(reflex_result.port_h_velocity == 0)
    assert np.nanmin(reflex_result.mil_w) > 0


test("Acoustic-load simulation returns finite response arrays", _check_simulation_arrays_are_finite)


def _check_response_metrics_are_sane():
    ts = _beyma_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _dccav.simulate(ts, box, np.geomspace(5.0, 1000.0, 2000))
    metrics = _dccav.response_metrics(result)
    thresholds = _dccav.response_threshold_frequencies(result)
    assert metrics["max_spl_db"] > 0
    assert metrics["f3_hz"] == thresholds[3]
    assert 0 < thresholds[10] < thresholds[6] < thresholds[3]
    assert metrics["max_excursion_mm"] > 0
    assert metrics["min_impedance_ohm"] > 0
    peak_freqs = _dccav.impedance_peak_frequencies(result)
    assert len(peak_freqs) >= 3, f"expected 3 DCCAV impedance peaks, got {peak_freqs}"

    ts = _dccav.get_driver_preset("Beyma 12LEX1300Nd")
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _dccav.simulate(ts, box, np.geomspace(5.0, 1000.0, 2000))
    thresholds = _dccav.response_threshold_frequencies(result)
    assert abs(thresholds[3] - a.f3_hz) < 2.0, (thresholds[3], a.f3_hz)
    assert 0 < thresholds[10] < thresholds[6] < thresholds[3]
    assert not _dccav.response_sanity_warnings(ts, box, thresholds)

    impossible = _dccav.response_sanity_warnings(ts, box, {3: 30.0})
    assert impossible, "impossible low F3 was not flagged"

    flat = result.__class__(
        frequency_hz=np.geomspace(20.0, 200.0, 200),
        spl_total_db=np.full(200, 90.0),
        spl_driver_db=np.full(200, 90.0),
        spl_port_db=np.full(200, 80.0),
        excursion_mm=np.ones(200),
        impedance_ohm=np.full(200, 6.0),
        port_h_velocity=np.ones(200),
        port_l_velocity=np.ones(200),
        mil_w=np.full(200, 1.0),
        mol_db=np.full(200, 90.0),
        driver_volume_velocity=np.ones(200, dtype=complex),
        port_volume_velocity=np.ones(200, dtype=complex),
    )
    flat_thresholds = _dccav.response_threshold_frequencies(flat)
    assert np.isnan(flat_thresholds[3]), flat_thresholds

    chr70 = _dccav.get_driver_preset("MarkAudio CHR-70")
    a = _dccav.suggest_alignment(chr70)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _dccav.simulate(chr70, box, np.geomspace(10.0, 500.0, 600))
    assert np.nanmax(result.mil_w) == chr70.pe_w
    assert np.nanmin(result.mil_w) > 0

    reflex = _dccav.suggest_reflex_alignment(_beyma_ts())
    box = _dccav.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    result = _dccav.simulate_reflex(_beyma_ts(), box, np.geomspace(5.0, 1000.0, 2000))
    peak_freqs = _dccav.impedance_peak_frequencies(result)
    assert len(peak_freqs) >= 2, f"expected two bass-reflex impedance peaks, got {peak_freqs}"


test("DCCAV response metrics are positive", _check_response_metrics_are_sane)


def _check_ui_reflex_volume_keeps_impedance_peaks():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    state = at.session_state
    state["load_type"] = "Bass reflex"
    state["driver_preset_name"] = "Beyma 12LX60V2"
    state["driver_fs_hz"] = 49.0
    state["driver_vas_l"] = 43.0
    state["driver_qts"] = 0.38
    state["driver_qms"] = 15.3
    state["driver_re_ohm"] = 5.1
    state["driver_sd_mode"] = "Sd"
    state["driver_sd_cm2"] = 550.0
    state["driver_le_mh"] = 2.1
    state["driver_xmax_mm"] = 9.0
    state["driver_pe_w"] = 700.0
    state["driver_mms_g"] = 102.0
    state["driver_cms_mm_n"] = 0.099
    state["driver_bl_tm"] = 20.0
    state["reflex_vb_l"] = 35.82
    state["reflex_fb_hz"] = 49.0
    state["reflex_q_abs"] = 15.0
    state["reflex_q_leak"] = 1000.0
    state["reflex_q_port"] = 15.0
    state["reflex_custom_losses"] = False
    state["sim_auto_align"] = False
    at.run()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Z peaks"] == "29, 84", metrics["Z peaks"]
    assert not any("Bass reflex should show two impedance peaks" in warning.value for warning in at.warning)

    state["reflex_q_abs"] = 1.0
    state["reflex_q_port"] = 1.0
    at.run()
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Z peaks"] == "29, 84", metrics["Z peaks"]
    assert not any("Bass reflex should show two impedance peaks" in warning.value for warning in at.warning)

    state["reflex_custom_losses"] = True
    at.run()
    assert any("Qabs=1.0, Qport=1.0" in warning.value for warning in at.warning)


test("UI bass-reflex volume edits preserve resonance diagnostics", _check_ui_reflex_volume_keeps_impedance_peaks)


def _check_response_chart_domain_tracks_10hz_and_peak():
    import ui_app as _ui

    result = _dccav.SimulationResult(
        frequency_hz=np.array([10.0, 20.0, 40.0]),
        spl_total_db=np.array([40.0, 70.0, 80.0]),
        spl_driver_db=np.array([39.0, 69.0, 78.0]),
        spl_port_db=np.array([30.0, 60.0, 83.0]),
        excursion_mm=np.ones(3),
        impedance_ohm=np.ones(3),
        port_h_velocity=np.ones(3),
        port_l_velocity=np.ones(3),
        mil_w=np.ones(3),
        mol_db=np.array([90.0, 90.0, 90.0]),
        driver_volume_velocity=np.ones(3, dtype=complex),
        port_volume_velocity=np.ones(3, dtype=complex),
    )
    domain = _ui._response_y_domain(result, {"Total": result.spl_total_db, "Vent": result.spl_port_db})
    assert domain == [40.0, 88.0], domain


test("UI response chart zoom uses 10 Hz floor and peak headroom", _check_response_chart_domain_tracks_10hz_and_peak)


def _check_response_chart_has_click_marker():
    import ui_app as _ui

    result = _dccav.SimulationResult(
        frequency_hz=np.array([10.0, 20.0, 40.0]),
        spl_total_db=np.array([40.0, 70.0, 80.0]),
        spl_driver_db=np.array([39.0, 69.0, 78.0]),
        spl_port_db=np.array([30.0, 60.0, 83.0]),
        excursion_mm=np.ones(3),
        impedance_ohm=np.ones(3),
        port_h_velocity=np.ones(3),
        port_l_velocity=np.ones(3),
        mil_w=np.ones(3),
        mol_db=np.array([90.0, 90.0, 90.0]),
        driver_volume_velocity=np.ones(3, dtype=complex),
        port_volume_velocity=np.ones(3, dtype=complex),
    )
    chart = _ui._plot_response(result, [])
    spec = chart.to_dict()
    params = spec.get("params", [])
    click_params = [param for param in params if param.get("name") == "click_marker"]
    assert click_params, params
    select = click_params[0]["select"]
    assert select["type"] == "point", select
    assert select["on"] == "click", select
    assert select["nearest"] is True, select
    assert click_params[0]["views"], click_params[0]


test("UI response chart has a clickable moving marker", _check_response_chart_has_click_marker)


def _check_ui_driver_preset_filters_reduce_list():
    import ui_app as _ui

    names = _dccav.driver_preset_names()
    filtered = _ui._filter_driver_preset_names(
        names,
        source="Built-in",
        family="Aiyima",
        size="Mini <= 2 in",
        search="53mm",
    )
    assert "Aiyima 4ohm 10w 53mm" in filtered, filtered
    assert "Aiyima 4ohm 10w 53mm LY1124-2" in filtered, filtered
    assert not any(name.startswith("Beyma") for name in filtered), filtered

    kept_selected = _ui._filter_driver_preset_names(
        names,
        source="Built-in",
        family="Beyma",
        size="12 in",
        search="",
        selected="Aiyima 4ohm 10w 53mm",
    )
    assert kept_selected[0] == "Aiyima 4ohm 10w 53mm", kept_selected[:3]
    assert "Beyma 12LX60V2" in kept_selected, kept_selected

    if any(name.startswith("LSDB: ") for name in names):
        lsdb = _ui._filter_driver_preset_names(
            names,
            source="Loudspeaker Database",
            family="GRS",
            size="12 in",
            search="12SW",
        )
        assert all(name.startswith("LSDB: GRS") for name in lsdb), lsdb[:5]
        assert any("12SW" in name for name in lsdb), lsdb[:5]


test("UI driver preset filters reduce long speaker lists", _check_ui_driver_preset_filters_reduce_list)


def _check_simulation_rejects_bad_frequency_grid():
    ts = _kef_b110_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    try:
        _dccav.simulate(ts, box, np.array([10.0, 0.0, 100.0]))
    except ValueError as exc:
        assert "Frequencies" in str(exc)
    else:
        raise AssertionError("non-positive frequency was accepted")


test("DCCAV rejects invalid frequency grid", _check_simulation_rejects_bad_frequency_grid)


print(f"\n{'=' * 40}")
print(f"  PASS: {PASS}   FAIL: {FAIL}   SKIP: {SKIP}")
print(f"{'=' * 40}")
if MATCHES and PASS == 0 and FAIL == 0:
    print("No tests matched --match filter")
    sys.exit(2)
sys.exit(0 if FAIL == 0 else 1)
