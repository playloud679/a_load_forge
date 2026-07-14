"""
Load Forge focused test suite.

The project is an acoustic-load simulator, so this runner covers the active
DCCAV, fourth-order bandpass, bass-reflex, acoustic-suspension and
infinite-baffle paths.
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


# Multiprocessing workers (spawn/forkserver) re-import the parent's __main__
# as "__mp_main__"; the suite must not execute again inside them.
_IS_MP_CHILD = __name__ == "__mp_main__"


def _parse_args():
    parser = argparse.ArgumentParser(description="Run Load Forge tests.")
    parser.add_argument(
        "--match", "-m", action="append", default=[],
        help="Run only tests whose label contains this text. May be repeated.")
    parser.add_argument("--list", action="store_true", help="List matching tests.")
    return parser.parse_args()


ARGS = argparse.Namespace(match=[], list=False) if _IS_MP_CHILD else _parse_args()
MATCHES = [m.casefold() for m in ARGS.match]


def _selected(label: str) -> bool:
    return not MATCHES or any(m in label.casefold() for m in MATCHES)


def test(label, fn):
    global PASS, FAIL, SKIP
    if _IS_MP_CHILD:
        return
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


def _check_sealed_and_infinite_baffle_models():
    import src as package_api

    assert package_api.SealedBox is not None
    assert package_api.simulate_sealed is not None
    assert package_api.simulate_infinite_baffle is not None
    ts = _beyma_ts()
    freq = np.geomspace(10.0, 500.0, 500)
    alignment = _dccav.suggest_sealed_alignment(ts)
    box = _dccav.SealedBox(vb_l=alignment.vb_l)
    fc_hz, qtc = _dccav.sealed_system_metrics(ts, box)
    assert abs(qtc - 0.707) < 1e-9, (fc_hz, qtc)
    assert fc_hz > ts.fs_hz

    sealed = _dccav.simulate_sealed(ts, box, freq)
    infinite = _dccav.simulate_infinite_baffle(ts, freq)
    for result in (sealed, infinite):
        assert np.all(np.isfinite(result.spl_total_db))
        assert np.allclose(result.spl_total_db, result.spl_driver_db)
        assert np.all(result.port_h_velocity == 0.0)
        assert np.all(result.port_l_velocity == 0.0)
        assert np.all(result.port_volume_velocity == 0.0)
        assert len(_dccav.impedance_peak_frequencies(result)) == 1
    ib_peak = _dccav.impedance_peak_frequencies(infinite)[0]
    assert abs(ib_peak - ts.fs_hz) / ts.fs_hz < 0.05, ib_peak


test("Sealed and infinite-baffle models expose unported responses", _check_sealed_and_infinite_baffle_models)


def _check_bandpass4_model_and_starter():
    import src as package_api

    assert package_api.Bandpass4Box is _dccav.Bandpass4Box
    assert package_api.simulate_bandpass4 is _dccav.simulate_bandpass4
    ts = _kef_b110_ts()
    alignment = _dccav.suggest_bandpass4_alignment(ts)
    assert abs(alignment.vp_l - 2.0 * 0.707**2 * ts.vas_l) < 1e-9
    assert abs(alignment.fp_hz - ts.fs_hz * 0.707 / ts.qts) < 1e-9
    assert alignment.vs_l > 0.05
    box = _dccav.Bandpass4Box(
        vs_l=alignment.vs_l, vp_l=alignment.vp_l, fp_hz=alignment.fp_hz)
    freq = np.geomspace(5.0, 1000.0, 2000)
    result = _dccav.simulate_bandpass4(ts, box, freq)
    for name in (
        "spl_total_db", "spl_driver_db", "spl_port_db", "excursion_mm",
        "impedance_ohm", "port_h_velocity", "port_l_velocity", "mil_w", "mol_db",
    ):
        values = getattr(result, name)
        assert values.shape == freq.shape
        assert np.all(np.isfinite(values)), name
    assert np.allclose(result.spl_total_db, result.spl_port_db)
    assert np.all(result.driver_volume_velocity == 0.0)
    assert np.all(result.port_h_velocity == 0.0)
    assert np.any(result.port_l_velocity > 0.0)
    assert len(_dccav.impedance_peak_frequencies(result)) >= 2
    assert not _dccav.bandpass4_diagnostics(ts, box, result)


test("Fourth-order bandpass starter and simulation are coherent", _check_bandpass4_model_and_starter)


def _check_bandpass4_optimizer_atlas_and_ranking():
    ts = _beyma_ts()
    goals = _dccav.OptimizationGoals(max_total_volume_l=40.0)
    optimized = _dccav.optimize_alignment(
        ts, goals, load_type="Bandpass 4th order", max_evaluations=80,
        fixed_total_volume_l=40.0)
    assert isinstance(optimized.box, _dccav.Bandpass4Box)
    assert abs(optimized.box.vs_l + optimized.box.vp_l - 40.0) < 1e-9
    assert np.isfinite(optimized.f3_hz)
    assert np.isfinite(optimized.ripple_db)

    space = _dccav.design_space_map(
        ts, load_type="Bandpass 4th order", resolution=5)
    assert space.f3_hz.shape == (5, 5)
    assert np.any(np.isfinite(space.f3_hz))
    box = _dccav.design_space_box(
        ts, "Bandpass 4th order", float(space.x_values[2]), float(space.y_values[2]))
    assert abs(box.vs_l + box.vp_l - float(space.x_values[2])) < 1e-9

    row = _dccav.rank_preset_row(
        "Beyma 12CMV2", "Bandpass 4th order", 40.0, 2.83, 10.0, 500.0, 240)
    assert row is not None
    assert abs(row["Vs L"] + row["Vp L"] - 40.0) < 1e-9
    assert np.isfinite(row["Fp Hz"])
    assert np.isfinite(row["F3 Hz"])


test("Fourth-order bandpass optimizer, atlas and Finder preserve volume", _check_bandpass4_optimizer_atlas_and_ranking)


def _check_ui_bandpass4_design_and_persistence():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    assert _ui._is_param_key("bandpass4_vs_l")
    payload = {
        "load_type": "Bandpass 4th order",
        "bandpass4_vs_l": 12.0,
        "bandpass4_vp_l": 18.0,
        "bandpass4_fp_hz": 72.0,
    }
    assert _ui._apply_loaded_params(payload) == len(payload)
    saved = _ui._collect_params()
    for key, value in payload.items():
        assert saved[key] == value

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception
    labels = {item.label for item in at.number_input}
    assert {"Vs sealed rear (L)", "Vp ported front (L)", "Fp front tuning (Hz)"} <= labels
    metrics = {metric.label for metric in at.metric}
    assert {"Box volume", "Vs sealed (active)", "Vp ported (active)", "Fp (active)"} <= metrics
    assert any(
        "Fourth-order bandpass total response is the front vent only" in caption.value
        for caption in at.caption
    )


test("UI fourth-order bandpass controls persist and render", _check_ui_bandpass4_design_and_persistence)


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


def _check_group_delay_is_finite_and_exported():
    ts = _beyma_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _dccav.simulate(ts, box, np.geomspace(10.0, 500.0, 600))
    gd = _dccav.group_delay_ms(result)
    assert gd.shape == result.frequency_hz.shape, gd.shape
    assert np.all(np.isfinite(gd)), "group delay must be finite across the sweep"
    assert np.nanmax(np.abs(gd)) > 0.1, "group delay should not be identically zero"

    import ui_app as _ui

    csv_text = _ui._csv_bytes(result).decode("utf-8")
    header = csv_text.splitlines()[0].split(",")
    assert "group_delay_ms" in header, header
    first_row = csv_text.splitlines()[1].split(",")
    gd_value = float(first_row[header.index("group_delay_ms")])
    assert np.isfinite(gd_value), gd_value


test("DCCAV group delay is finite and exported to CSV", _check_group_delay_is_finite_and_exported)


def _parse_export_rows(text: str) -> np.ndarray:
    rows = [line.split("\t") for line in text.splitlines() if not line.startswith("*")]
    return np.array([[float(value) for value in row] for row in rows])


def _check_frd_zma_exports():
    import dataclasses

    ts = _kef_b110_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 240)
    result = _dccav.simulate(ts, box, freq, 2.83)

    frd_text = _dccav.export_frd_text(result)
    assert frd_text.splitlines()[0].startswith("*"), "FRD must open with comment lines"
    frd = _parse_export_rows(frd_text)
    assert frd.shape == (len(freq), 3), frd.shape
    np.testing.assert_allclose(frd[:, 0], freq, atol=5e-4)
    np.testing.assert_allclose(frd[:, 1], result.spl_total_db, atol=5e-4)
    assert np.all(np.abs(frd[:, 2]) <= 180.0 + 1e-9), "FRD phase must be wrapped to ±180"
    assert np.ptp(frd[:, 2]) > 90.0, "response phase must actually rotate over the sweep"

    zma = _parse_export_rows(_dccav.export_zma_text(result))
    assert zma.shape == (len(freq), 3), zma.shape
    np.testing.assert_allclose(zma[:, 0], freq, atol=5e-4)
    np.testing.assert_allclose(zma[:, 1], result.impedance_ohm, atol=5e-4)
    assert np.all(np.abs(zma[:, 2]) <= 90.0 + 1e-9), "passive impedance phase stays within ±90"
    assert np.ptp(zma[:, 2]) > 30.0, "impedance phase must swing across the resonances"

    reflex = _dccav.simulate_reflex(ts, _dccav.ReflexBox(vb_l=ts.vas_l, fb_hz=ts.fs_hz), freq)
    sealed = _dccav.simulate_sealed(ts, _dccav.SealedBox(vb_l=ts.vas_l), freq)
    baffle = _dccav.simulate_infinite_baffle(ts, freq)
    for run in (reflex, sealed, baffle):
        assert run.impedance_phase_deg is not None
        assert np.all(np.isfinite(run.impedance_phase_deg))

    legacy = dataclasses.replace(result, impedance_phase_deg=None)
    legacy_zma = _parse_export_rows(_dccav.export_zma_text(legacy))
    assert np.all(legacy_zma[:, 2] == 0.0), "legacy results must degrade to zero phase"

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.run()
    assert not at.exception, at.exception
    labels = {button.label for button in at.get("download_button")}
    assert {"Download FRD (response)", "Download ZMA (impedance)"} <= labels, labels


test("DCCAV FRD/ZMA exports match the simulated arrays", _check_frd_zma_exports)


def _check_ui_group_delay_chart_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.run()
    assert not at.exception, at.exception
    assert any(sub.value == "Group Delay" for sub in at.subheader), (
        "Group Delay tab subheader missing"
    )


test("UI group-delay tab renders the Group Delay chart", _check_ui_group_delay_chart_renders)


def _check_port_geometry_helpers():
    volume_l, fb_hz, diameter_cm = 50.0, 40.0, 10.0
    length_cm = _dccav.port_length_cm(volume_l, fb_hz, diameter_cm)
    assert 15.0 < length_cm < 35.0, length_cm

    radius_m = diameter_cm / 200.0
    l_eff_m = length_cm / 100.0 + 1.463 * radius_m
    fb_check = (
        _dccav.SPEED_OF_SOUND / (2.0 * np.pi)
        * np.sqrt(np.pi * radius_m**2 / ((volume_l / 1000.0) * l_eff_m))
    )
    assert abs(fb_check - fb_hz) < 1e-9, fb_check

    assert _dccav.port_length_cm(volume_l, fb_hz, 5.0) < length_cm
    assert _dccav.port_length_cm(100.0, 30.0, 1.0) <= 0.0, "tiny port must be flagged impossible"

    max_hz = _dccav.port_max_tuning_hz(16.70, 4.0, 1.7)
    assert 80.0 < max_hz < 83.0, max_hz
    min_d_cm = _dccav.port_min_diameter_cm(16.70, 127.59, 1.7)
    assert 9.5 < min_d_cm < 10.2, min_d_cm
    assert abs(_dccav.port_length_cm(16.70, max_hz, 4.0, 1.7)) < 1e-9
    assert abs(_dccav.port_length_cm(16.70, 127.59, min_d_cm, 1.7)) < 1e-9

    ts = _beyma_ts()
    reflex = _dccav.suggest_reflex_alignment(ts)
    box = _dccav.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    result = _dccav.simulate_reflex(ts, box, np.geomspace(10.0, 500.0, 400))
    area_cm2 = np.pi * (diameter_cm / 2.0) ** 2
    velocity = _dccav.port_air_velocity_ms(result, area_cm2, "lower")
    assert velocity.shape == result.frequency_hz.shape
    assert np.all(np.isfinite(velocity)), "port air speed must be finite"
    assert np.nanmax(velocity) > 0.0
    halved = _dccav.port_air_velocity_ms(result, area_cm2 / 2.0, "lower")
    np.testing.assert_allclose(halved, 2.0 * velocity)
    try:
        _dccav.port_air_velocity_ms(result, area_cm2, "middle")
        raise AssertionError("invalid port name must raise")
    except ValueError:
        pass


test("DCCAV port geometry length round-trips and air speed scales", _check_port_geometry_helpers)


def _check_ui_port_geometry_warns_on_small_vent():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    state = at.session_state
    state["workspace_mode"] = "Design a box"
    state["load_type"] = "Bass reflex"
    state["sim_auto_align"] = False
    state["reflex_vb_l"] = 76.0
    state["reflex_fb_hz"] = 49.0
    state["reflex_port_d_cm"] = 1.0
    at.run()
    assert not at.exception, at.exception
    assert any("chuffing" in warning.value for warning in at.warning), (
        "a 1 cm vent must trigger the air-speed warning"
    )
    assert any("needs a diameter of at least" in warning.value for warning in at.warning), (
        "a 1 cm vent on 76 L @ 49 Hz must report the minimum feasible diameter"
    )

    state["reflex_port_d_cm"] = 0.0
    at.run()
    assert not at.exception, at.exception
    assert not any("chuffing" in warning.value for warning in at.warning)


test("UI port geometry warns about small-vent air speed", _check_ui_port_geometry_warns_on_small_vent)


def _check_driver_reference_metrics():
    ts = _kef_b110_ts()
    drv = _dccav.complete_driver(ts)
    ref = _dccav.driver_reference_metrics(ts)
    assert abs(ref.ebp_hz - ts.fs_hz / drv.qes) < 1e-9, ref.ebp_hz
    assert 0.002 < ref.eta0 < 0.004, ref.eta0
    assert 85.0 < ref.spl_1w_db < 89.0, ref.spl_1w_db
    assert ref.spl_2v83_db > ref.spl_1w_db, "Re < 8 ohm must gain SPL at 2.83 V"
    assert 105.0 < ref.ebp_hz < 120.0, "article driver EBP should suggest a ported load"


test("DCCAV driver reference metrics match classical formulas", _check_driver_reference_metrics)


def _check_ui_reference_metrics_row():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.run()
    assert not at.exception, at.exception
    labels = {metric.label for metric in at.metric}
    for expected in ("Eta0 ref", "SPL 1W/1m", "SPL 2.83V/1m", "EBP"):
        assert expected in labels, f"missing reference metric {expected}"
    assert any("EBP" in caption.value for caption in at.caption), (
        "EBP topology hint caption missing"
    )


test("UI shows reference efficiency, sensitivity and EBP metrics", _check_ui_reference_metrics_row)


def _check_series_resistance_effects():
    ts = _beyma_ts()
    reflex = _dccav.suggest_reflex_alignment(ts)
    box = _dccav.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    freq = np.geomspace(10.0, 500.0, 500)
    base = _dccav.simulate_reflex(ts, box, freq)
    zero_rs = _dccav.simulate_reflex(ts, box, freq, series_r_ohm=0.0)
    np.testing.assert_allclose(zero_rs.spl_total_db, base.spl_total_db)
    np.testing.assert_allclose(zero_rs.impedance_ohm, base.impedance_ohm)

    with_rs = _dccav.simulate_reflex(ts, box, freq, series_r_ohm=2.0)
    z_min_shift = np.min(with_rs.impedance_ohm) - np.min(base.impedance_ohm)
    assert 1.5 < z_min_shift < 2.5, f"source must see ~2 ohm more, got {z_min_shift:.2f}"
    assert np.nanmax(with_rs.spl_total_db) < np.nanmax(base.spl_total_db), (
        "series R must reduce the drive level"
    )
    diff = base.spl_total_db - with_rs.spl_total_db
    assert np.nanmax(diff) - np.nanmin(diff) > 0.5, (
        "series R must change damping, not apply a flat attenuation"
    )
    assert np.nanmax(with_rs.mil_w) <= np.nanmax(base.mil_w) + 1e-9, (
        "driver-side thermal power must not grow with series R"
    )

    a = _dccav.suggest_alignment(ts)
    dccav_box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    for run in (
        _dccav.simulate(ts, dccav_box, freq, 2.83, 2.0),
        _dccav.simulate_sealed(ts, _dccav.SealedBox(vb_l=40.0), freq, 2.83, 2.0),
        _dccav.simulate_infinite_baffle(ts, freq, 2.83, 2.0),
    ):
        assert np.all(np.isfinite(run.spl_total_db)), "series R runs must stay finite"
        assert np.min(run.impedance_ohm) > ts.re_ohm + 1.5, "impedance must include series R"

    try:
        _dccav.simulate_reflex(ts, box, freq, series_r_ohm=-1.0)
        raise AssertionError("negative series resistance must raise")
    except ValueError:
        pass


test("DCCAV series resistance shifts impedance, drive and damping", _check_series_resistance_effects)


def _check_ui_series_resistance_input():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.run()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    z_min_base = float(str(metrics["Min impedance"]).split()[0])

    at.session_state["sim_series_r_ohm"] = 4.0
    at.run()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    z_min_rs = float(str(metrics["Min impedance"]).split()[0])
    assert 3.0 < (z_min_rs - z_min_base) < 5.0, (z_min_base, z_min_rs)


test("UI series resistance raises the minimum impedance metric", _check_ui_series_resistance_input)


def _check_ui_pin_response_overlay():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    assert not at.exception, at.exception

    pin = next(b for b in at.button if b.label == "Pin response")
    pin.click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_response"]
    assert pinned, "pin button must store the current response snapshot"
    assert pinned["label"].startswith("DCCAV"), pinned["label"]
    assert len(pinned["frequency_hz"]) == len(pinned["spl_total_db"]) > 0
    assert any("Pinned (dashed grey)" in caption.value for caption in at.caption)

    at.session_state["load_type"] = "Sealed"
    at.run()
    assert not at.exception, "pinned overlay must survive a load-type change"
    assert at.session_state["pinned_response"]["label"].startswith("DCCAV")

    clear = next(b for b in at.button if b.label == "Clear pin")
    clear.click().run()
    assert not at.exception, at.exception
    assert not at.session_state["pinned_response"], "clear must drop the pinned snapshot"


test("UI pin overlay stores, survives load changes and clears", _check_ui_pin_response_overlay)


def _check_ui_load_comparison_overlay():
    import ui_app as _ui

    ts = _beyma_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 300)
    vtot, series = _ui._topology_comparison_series(ts, "DCCAV", box, freq, 2.83, 0.0)
    assert abs(vtot - (a.vh_l + a.vl_l)) < 1e-9, vtot
    assert set(series) == {
        "DCCAV", "Bandpass 4th order", "Bass reflex", "Sealed", "Infinite baffle",
    }
    for name, values in series.items():
        assert values.shape == freq.shape, name
        assert np.all(np.isfinite(values)), f"{name} comparison response must be finite"

    reflex_box = _dccav.ReflexBox(vb_l=40.0, fb_hz=45.0)
    vtot_r, series_r = _ui._topology_comparison_series(ts, "Bass reflex", reflex_box, freq, 2.83, 0.0)
    assert abs(vtot_r - 40.0) < 1e-9, vtot_r
    direct = _dccav.simulate_reflex(ts, reflex_box, freq, 2.83, 0.0)
    np.testing.assert_allclose(series_r["Bass reflex"], direct.spl_total_db)

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["plot_compare_loads"] = True
    at.run()
    assert not at.exception, at.exception
    assert any(
        "Comparing total response" in caption.value
        for caption in at.caption
    ), "comparison caption missing on the main response chart"


test("UI load comparison simulates all topologies at equal volume", _check_ui_load_comparison_overlay)


def _check_ui_share_link_roundtrip():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.run()
    at.session_state["load_type"] = "Bass reflex"
    at.session_state["driver_fs_hz"] = 33.0
    at.session_state["reflex_vb_l"] = 55.5
    at.session_state["sim_auto_align"] = False
    at.run()
    share = next(b for b in at.button if b.label == "Share via URL")
    share.click().run()
    assert not at.exception, at.exception
    token = at.query_params.get("d")
    if isinstance(token, list):
        token = token[0] if token else None
    assert token, "share button must write the encoded design into the URL"

    decoded = _ui._decode_share_payload(token)
    assert decoded["load_type"] == "Bass reflex"
    assert abs(float(decoded["driver_fs_hz"]) - 33.0) < 1e-9
    assert abs(float(decoded["reflex_vb_l"]) - 55.5) < 1e-9

    at2 = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at2.query_params["d"] = token
    at2.run()
    assert not at2.exception, at2.exception
    assert at2.session_state["load_type"] == "Bass reflex"
    assert abs(float(at2.session_state["driver_fs_hz"]) - 33.0) < 1e-9
    assert abs(float(at2.session_state["reflex_vb_l"]) - 55.5) < 1e-9

    at3 = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at3.query_params["d"] = "not-a-valid-token"
    at3.run()
    assert not at3.exception, at3.exception
    assert any("could not be decoded" in warning.value for warning in at3.warning), (
        "an invalid share token must degrade gracefully with a warning"
    )


test("UI share link round-trips the design through the URL", _check_ui_share_link_roundtrip)


def _check_driver_bandwidth_classifier():
    sub = _dccav.classify_driver_bandwidth(_dccav.get_driver_preset("Dayton Audio RSS315HO-4"))
    assert sub.driver_class == "Subwoofer", sub
    assert sub.f_le_hz is not None and 250.0 < sub.f_le_hz < 330.0, sub.f_le_hz

    mid = _dccav.classify_driver_bandwidth(_beyma_ts())
    assert mid.driver_class == "Midbass-capable", mid
    expected_f_le = 6.0 / (2.0 * np.pi * 0.001)
    assert abs(mid.f_le_hz - expected_f_le) < 1e-6, mid.f_le_hz
    assert mid.reasons, "classification must expose its indicators"

    tiny = _dccav.classify_driver_bandwidth(_dccav.get_driver_preset("Aiyima 4ohm 5w 40mm black"))
    assert tiny.f_le_hz is None, "Le=0 must map to an unknown voice-coil corner"
    assert tiny.driver_class in _dccav.DRIVER_CLASSES, tiny


test("DCCAV bandwidth classifier separates subwoofers from midbass drivers", _check_driver_bandwidth_classifier)


def _check_ui_class_filter():
    import ui_app as _ui

    names = tuple(
        name for name in _dccav.driver_preset_names()
        if not name.startswith("LSDB:")
    )
    subs = _ui._filter_driver_preset_names(
        names, source="All", family="All", size="All", search="", driver_class="Subwoofer")
    assert "Dayton Audio RSS315HO-4" in subs, subs
    assert "Beyma 12CMV2" not in subs, subs
    mids = _ui._filter_driver_preset_names(
        names, source="All", family="All", size="All", search="", driver_class="Midbass-capable")
    assert "Beyma 12CMV2" in mids, mids
    assert "Dayton Audio RSS315HO-4" not in mids, mids

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["preset_class_filter"] = "Midbass-capable"
    at.run()
    assert not at.exception, at.exception
    preset_box = next(s for s in at.selectbox if s.label == "Driver preset")
    assert "Beyma 12CMV2" in preset_box.options, "midbass filter must keep the Beyma 12CMV2"
    assert "Dayton Audio RSS315HO-4" not in preset_box.options, (
        "midbass filter must drop the pure subwoofer"
    )
    labels = {metric.label for metric in at.metric}
    assert {"VC corner", "Class"} <= labels, labels


test("UI class filter separates subwoofers from midbass presets", _check_ui_class_filter)


def _check_ui_reflex_volume_keeps_impedance_peaks():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    state = at.session_state
    state["workspace_mode"] = "Design a box"
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
        spl_port_db=np.array([30.0, 60.0, 180.0]),
        excursion_mm=np.ones(3),
        impedance_ohm=np.ones(3),
        port_h_velocity=np.ones(3),
        port_l_velocity=np.ones(3),
        mil_w=np.ones(3),
        mol_db=np.array([90.0, 90.0, 90.0]),
        driver_volume_velocity=np.ones(3, dtype=complex),
        port_volume_velocity=np.ones(3, dtype=complex),
    )
    domain = _ui._response_y_domain(result, {"Total": result.spl_total_db})
    assert domain == [40.0, 85.0], domain

    # The floor stays anchored to the total at 10 Hz, but the ceiling must
    # follow every displayed trace so none is clipped out of the chart.
    domain = _ui._response_y_domain(result, {"Total": result.spl_total_db, "Vent": result.spl_port_db})
    assert domain == [40.0, 185.0], domain

    zoom_domain = _ui._response_y_domain(
        result, {"Total": result.spl_total_db}, [20.0, 40.0])
    assert zoom_domain == [68.0, 82.0], zoom_domain
    chart = _ui._plot_response(result, [], frequency_window=[20.0, 40.0])
    spec = chart.to_dict()
    assert spec["height"] == 420, spec.get("height")
    assert "'domain': [20.0, 40.0]" in str(spec), spec


test("UI response chart zoom anchors at 10 Hz and keeps displayed traces visible", _check_response_chart_domain_tracks_10hz_and_peak)


def _check_ui_response_zoom_slider_and_reset():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.run()
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception

    zoom = next(
        slider for slider in at.slider
        if slider.label == "Response frequency window (Hz)"
    )
    assert tuple(zoom.value) == (10, 500), zoom.value
    reset = next(button for button in at.button if button.label == "Reset zoom")
    assert reset.disabled

    at.session_state["plot_response_window_hz"] = (20, 200)
    at.run()
    assert not at.exception, at.exception
    zoom = next(
        slider for slider in at.slider
        if slider.label == "Response frequency window (Hz)"
    )
    assert tuple(zoom.value) == (20, 200), zoom.value
    reset = next(button for button in at.button if button.label == "Reset zoom")
    assert not reset.disabled
    reset.click().run()
    assert not at.exception, at.exception
    assert tuple(at.session_state["plot_response_window_hz"]) == (10, 500)


test("UI response zoom has a frequency window and reliable reset", _check_ui_response_zoom_slider_and_reset)


def _check_ui_response_pens_survive_workspace_and_preset_changes():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception

    def pen(label):
        return next(box for box in at.checkbox if box.label == label)

    assert pen("Total").value and pen("Total").disabled
    pen("Cone").set_value(False).run()
    pen("Lower port").set_value(False).run()
    pen("MOL").set_value(True).run()

    workspace = next(
        control for control in at.segmented_control if control.label == "Workspace"
    )
    workspace.set_value("Find a driver").run()
    workspace = next(
        control for control in at.segmented_control if control.label == "Workspace"
    )
    workspace.set_value("Design a box").run()
    assert not at.exception, at.exception

    assert pen("Total").value and pen("Total").disabled
    assert not pen("Cone").value
    assert not pen("Lower port").value
    assert pen("MOL").value

    preset = next(box for box in at.selectbox if box.label == "Driver preset")
    preset.set_value("Beyma 12CMV2").run()
    assert not at.exception, at.exception
    assert pen("Total").value
    assert not pen("Cone").value
    assert not pen("Lower port").value
    assert pen("MOL").value

    # Even stale or externally seeded state cannot remove the baseline pen.
    at.session_state["plot_response_total"] = False
    at.run()
    assert next(box for box in at.checkbox if box.label == "Total").value


test(
    "UI response pens persist across workspace and preset changes",
    _check_ui_response_pens_survive_workspace_and_preset_changes,
)


def _check_response_chart_drops_non_finite_points_and_keeps_label_scale_clean():
    import ui_app as _ui

    result = _dccav.SimulationResult(
        frequency_hz=np.array([10.0, 20.0, 40.0]),
        spl_total_db=np.array([40.0, np.nan, 80.0]),
        spl_driver_db=np.array([39.0, 69.0, np.inf]),
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
    frame = _ui._series_frame(result, {"Total": result.spl_total_db, "Cone": result.spl_driver_db})
    assert len(frame) == 4, frame
    assert np.isfinite(frame["value"]).all()

    rows = [_ui._cursor_row(result, "F3", 10.0, "auto")]
    chart = _ui._plot_response(result, rows)
    spec = chart.to_dict()
    spec_text = str(spec)
    assert "label_y_px" not in spec_text
    assert "label_y_db" in spec_text


test("UI response chart filters invalid points and keeps cursor labels on the dB scale", _check_response_chart_drops_non_finite_points_and_keeps_label_scale_clean)


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


def _check_ui_driver_preset_price_filter_uses_optional_metadata():
    import ui_app as _ui

    original = _ui._driver_preset_price
    original_currency = _ui._driver_preset_currency
    try:
        prices = {"cheap": 50.0, "cheap_gbp": 40.0, "expensive": 500.0, "unknown": None}
        currencies = {"cheap": "EUR", "cheap_gbp": "GBP", "expensive": "EUR", "unknown": ""}
        _ui._driver_preset_price = lambda name: prices[name]
        _ui._driver_preset_currency = lambda name: currencies[name]
        filtered = _ui._filter_driver_preset_names(
            ["cheap", "cheap_gbp", "expensive", "unknown"],
            source="All",
            family="All",
            size="All",
            search="",
            max_price=100.0,
            max_price_currency="EUR",
        )
        assert filtered == ["cheap"], filtered
    finally:
        _ui._driver_preset_price = original
        _ui._driver_preset_currency = original_currency

    info = _dccav.DriverPresetInfo(
        name="priced",
        source="test",
        brand="brand",
        model="model",
        price=123.45,
        currency="EUR",
    )
    assert info.price == 123.45
    assert info.currency == "EUR"


test("UI driver preset price filter uses optional metadata", _check_ui_driver_preset_price_filter_uses_optional_metadata)


def _check_dccav_loads_external_price_records(tmp_path=None):
    price_path = _dccav.DRIVER_PRICES_PATH
    original_exists = price_path.exists()
    original_text = price_path.read_text(encoding="utf-8") if original_exists else None
    try:
        price_path.parent.mkdir(parents=True, exist_ok=True)
        price_path.write_text(
            '{\n'
            '  "prices": {\n'
            '    "Beyma 12CMV2": {"price": 321.5, "currency": "EUR", "url": "https://example.test/beyma"},\n'
            '    "Beyma 12G40": {"price": 0.29, "currency": "EUR", "matched_name": "Beyma 12G40 woofer", "matched_brand": "Beyma", "matched_mpn": "12G40", "url": "https://example.test/beyma-12g40"},\n'
            '    "Beyma 12BR70": {"price": 0.29, "currency": "EUR", "matched_name": "Intertechnik Distance holders", "matched_brand": "Intertechnik", "matched_mpn": "DHLP/100", "url": "https://example.test/bad"},\n'
            '    "Beyma 12MCS500": {"price": 29.0, "currency": "GBP", "matched_name": "2-way crossover for Beyma 12MCS500", "matched_brand": "Beyma", "matched_mpn": "XO12MCS500", "url": "https://example.test/crossover"}\n'
            '  }\n'
            '}\n',
            encoding="utf-8",
        )
        _dccav._load_driver_price_records.cache_clear()
        _dccav._load_loudspeaker_database_presets.cache_clear()
        info = _dccav.driver_preset_info("Beyma 12CMV2")
        assert info.price == 321.5
        assert info.currency == "EUR"
        assert info.url == "https://example.test/beyma"
        assert _dccav.driver_preset_info("Beyma 12G40").price == 0.29
        assert _dccav.driver_preset_info("Beyma 12BR70").price is None
        assert _dccav.driver_preset_info("Beyma 12MCS500").price is None
    finally:
        if original_exists:
            price_path.write_text(original_text or "", encoding="utf-8")
        else:
            try:
                price_path.unlink()
            except FileNotFoundError:
                pass
        _dccav._load_driver_price_records.cache_clear()
        _dccav._load_loudspeaker_database_presets.cache_clear()


test("DCCAV loads external price records", _check_dccav_loads_external_price_records)


def _check_lsdb_importer_preserves_website_fields_and_prices():
    from tools import import_loudspeaker_database as importer

    card = {
        "id": "demo-1",
        "title": "Demo Brand W12",
        "brand": "Demo Brand",
        "model": "W12",
        "size_type": '12" Woofer',
        "text": "Demo Brand W12 12 inch woofer",
        "links": [
            {
                "href": "https://parts-express.com/demo-w12",
                "text": "Buy now $129.99",
                "title": "Parts Express",
                "class": "shop_link",
            }
        ],
        "images": [{"src": "/demo.jpg", "alt": "Demo woofer"}],
        "html_attrs": {"data-woofer-id": "demo-1"},
        "raw": {
            "fs": 30,
            "qts": 0.4,
            "re": 5.8,
            "sd": 530,
            "mmd": 100,
            "rms": 2,
            "cms": 250,
            "bl": 14,
            "le": 1.2,
            "xmax": 8,
            "pmax": 250,
            "spl1w": 90,
            "z": 8,
            "frmin": 30,
            "frmax": 3000,
        },
    }
    preset = importer.make_preset(card)
    assert preset is not None
    assert preset["price"] == 129.99
    assert preset["currency"] == "USD"
    assert preset["website_fields"]["raw"]["spl1w"] == 90
    assert "spl1w" in preset["website_fields"]["raw_keys"]
    assert preset["website_fields"]["commerce_links"][0]["href"] == "https://parts-express.com/demo-w12"
    assert preset["website_fields"]["images"][0]["src"] == "https://loudspeakerdatabase.com/demo.jpg"


test("LSDB importer preserves website fields and prices", _check_lsdb_importer_preserves_website_fields_and_prices)


def _check_price_enricher_extracts_jsonld_product_offer():
    from tools import enrich_driver_prices as enricher

    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Dayton Audio Reference RSS315HO-4 12&quot; Subwoofer",
      "brand": {"@type": "Brand", "name": "Dayton Audio"},
      "mpn": "RSS315HO-4",
      "sku": "RSS315HO-4",
      "offers": {
        "@type": "Offer",
        "price": "359.95",
        "priceCurrency": "EUR",
        "availability": "https://schema.org/InStock",
        "url": "/en/dayton-audio-rss315ho-4.html"
      }
    }
    </script>
    """
    products = enricher.product_records_from_html(html, "https://www.soundimports.eu/en/search/rss315ho-4/")
    assert len(products) == 1
    product = products[0]
    assert product["price"] == 359.95
    assert product["currency"] == "EUR"
    assert product["url"] == "https://www.soundimports.eu/en/dayton-audio-rss315ho-4.html"
    candidate = enricher.PresetCandidate(
        name="Dayton Audio RSS315HO-4",
        brand="Dayton Audio",
        model="RSS315HO-4",
        query="RSS315HO-4",
    )
    assert enricher.match_score(candidate, product) >= 0.85


test("Price enricher extracts JSON-LD product offers", _check_price_enricher_extracts_jsonld_product_offer)


def _check_price_enricher_falls_back_on_dirty_jsonld_product_text():
    from tools import enrich_driver_prices as enricher

    html = """
      "@type": "Product",
      "name": "Scan-Speak Revelator 15W/4531G00 5.5&quot; Woofer",
      "url": "https://www.soundimports.eu/en/scan-speak-15w-4531g00.html",
      "brand": { "@type": "Brand", "name": "Scan-Speak" },
      "mpn": "15W/4531G00",
      "sku": "15W/4531G00",
      "offers": {
        "@type": "Offer",
        "price": "199.95",
        "url": "https://www.soundimports.eu/en/scan-speak-15w-4531g00.html",
        "priceValidUntil": "2027-07-12",
        "priceCurrency": "EUR",
        "availability": "https://schema.org/InStock"
      },
      "review": [{"description": "dirty
      newline"}]
    """
    products = enricher.product_records_from_html(html, "https://www.soundimports.eu/en/")
    assert products[0]["price"] == 199.95
    assert products[0]["mpn"] == "15W/4531G00"
    assert products[0]["name"].endswith('5.5" Woofer')


test("Price enricher falls back on dirty JSON-LD product text", _check_price_enricher_falls_back_on_dirty_jsonld_product_text)


def _check_price_enricher_sitemap_and_catalog_matching():
    from tools import enrich_driver_prices as enricher

    sitemap = """
    <urlset>
      <url><loc>https://www.soundimports.eu/en/dayton-audio-rss315ho-4.html</loc></url>
      <url><loc>https://www.soundimports.eu/en/service/about/</loc></url>
      <url><loc>https://www.soundimports.eu/en/brands/dayton-audio/</loc></url>
    </urlset>
    """
    urls = enricher.soundimports_product_urls(sitemap)
    assert urls == ["https://www.soundimports.eu/en/dayton-audio-rss315ho-4.html"]

    candidate = enricher.PresetCandidate(
        name="Dayton Audio RSS315HO-4",
        brand="Dayton Audio",
        model="RSS315HO-4",
        query="RSS315HO-4",
    )
    product = {
        "name": "Dayton Audio Reference RSS315HO-4 Subwoofer",
        "brand": "Dayton Audio",
        "mpn": "RSS315HO-4",
        "sku": "RSS315HO-4",
        "url": urls[0],
        "price": 359.95,
        "currency": "EUR",
    }
    payload = {"prices": {}, "catalog": {}}
    matched = enricher.ingest_product(product, [candidate], payload, "SoundImports", 0.8)
    assert matched is True
    assert payload["prices"]["Dayton Audio RSS315HO-4"]["price"] == 359.95
    assert urls[0] in payload["catalog"]["SoundImports"]


test("Price enricher supports sitemap catalog matching", _check_price_enricher_sitemap_and_catalog_matching)


def _check_price_enricher_rejects_weak_substring_matches():
    from tools import enrich_driver_prices as enricher

    candidate = enricher.PresetCandidate(
        name="LSDB: Pride LP 10",
        brand="Pride",
        model="LP 10",
        query="LP 10",
    )
    false_product = {
        "name": "Intertechnik Distance holders for printed circuit boards",
        "brand": "Intertechnik",
        "mpn": "DHLP/100",
        "sku": "DHLP/100",
        "url": "https://www.soundimports.eu/en/intertechnik-dhlp100.html",
        "price": 0.29,
        "currency": "EUR",
    }
    assert enricher.match_score(candidate, false_product) < 0.8

    true_product = {
        "name": "Pride LP 10 Subwoofer",
        "brand": "Pride",
        "mpn": "LP 10",
        "sku": "LP 10",
        "url": "https://example.test/pride-lp-10",
        "price": 5.95,
        "currency": "EUR",
    }
    assert enricher.match_score(candidate, true_product) >= 0.8
    spare_part = {
        "name": "Pride Surround for LP 10",
        "brand": "Pride",
        "mpn": "LP 10",
        "sku": "LP 10",
        "url": "https://example.test/pride-lp-10-surround",
        "price": 4.95,
        "currency": "EUR",
    }
    assert enricher.match_score(candidate, spare_part) == 0.0

    payload = {
        "prices": {
            "LSDB: Pride LP 10": enricher.price_record(candidate, false_product, "SoundImports", 0.8),
            "LP 10": enricher.price_record(candidate, true_product, "SoundImports", 1.0),
        }
    }
    removed = enricher.prune_price_matches([candidate], payload, 0.8, 0.0)
    assert removed == 1
    assert payload["prices"]["LP 10"]["price"] == 5.95


test("Price enricher rejects weak substring matches", _check_price_enricher_rejects_weak_substring_matches)


def _check_price_enricher_extracts_category_itemlist_offers():
    from tools import enrich_driver_prices as enricher

    html = """
    <link rel="next" href="https://www.soundimports.eu/en/audio-components/woofers/page2.html"/>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "itemListElement": [
        {
          "@type": "ListItem",
          "item": {
            "@type": "Product",
            "name": "RSS315HO-4 Subwoofer",
            "offers": {"@type": "AggregateOffer", "lowPrice": 359.95, "priceCurrency": "EUR"},
            "url": "dayton-audio-rss315ho-4.html"
          }
        },
        {
          "@type": "ListItem",
          "item": {
            "@type": "Product",
            "name": "15W/4531G00 Woofer",
            "offers": {"@type": "AggregateOffer", "lowPrice": 199.95, "priceCurrency": "EUR"},
            "url": "scan-speak-15w-4531g00.html"
          }
        }
      ]
    }
    </script>
    """
    products = enricher.product_records_from_html(html, "https://www.soundimports.eu/en/audio-components/woofers/")
    assert len(products) == 2
    assert products[0]["price"] == 359.95
    assert products[0]["url"] == "https://www.soundimports.eu/en/dayton-audio-rss315ho-4.html"
    assert enricher.rel_next_url(html, "https://www.soundimports.eu/en/audio-components/woofers/").endswith("page2.html")


test("Price enricher extracts category ItemList offers", _check_price_enricher_extracts_category_itemlist_offers)


def _check_price_enricher_supports_bluearan_provider():
    from tools import enrich_driver_prices as enricher

    provider = enricher.PROVIDERS["bluearan"]
    sitemap = """
    <urlset>
      <url><loc>https://www.bluearan.co.uk/index.php?id=BCP15NDL76</loc></url>
      <url><loc>https://www.bluearan.co.uk/index.php?manselect=Eminence</loc></url>
      <url><loc>https://www.bluearan.co.uk/</loc></url>
    </urlset>
    """
    urls = enricher.provider_product_urls(provider, sitemap)
    assert urls == ["https://www.bluearan.co.uk/index.php?id=BCP15NDL76"]

    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "B&amp;C 15NDL76 - 15\\" 450W 8 Ohm",
      "sku": "BCP15NDL76",
      "offers": {
        "@type": "Offer",
        "url": "https://www.bluearan.co.uk/index.php?id=BCP15NDL76",
        "price": "159.99",
        "priceCurrency": "GBP",
        "availability": "https://schema.org/InStock"
      }
    }
    </script>
    """
    products = enricher.product_records_from_html(html, urls[0])
    assert len(products) == 1
    product = products[0]
    assert product["price"] == 159.99
    assert product["currency"] == "GBP"
    assert product["url"] == "https://www.bluearan.co.uk/index.php?id=BCP15NDL76"
    candidate = enricher.PresetCandidate(
        name="LSDB: B&C Speaker 15NDL76",
        brand="B&C Speaker",
        model="15NDL76",
        query="15NDL76",
    )
    assert enricher.match_score(candidate, product) >= 0.8
    payload = {"prices": {}, "catalog": {}}
    assert enricher.ingest_product(product, [candidate], payload, provider.seller, 0.8) is True
    assert payload["prices"]["LSDB: B&C Speaker 15NDL76"]["currency"] == "GBP"
    assert product["url"] in payload["catalog"]["BlueAran"]


test("Price enricher supports the Blue Aran provider", _check_price_enricher_supports_bluearan_provider)


def _check_price_enricher_supports_madisound_provider():
    from tools import enrich_driver_prices as enricher

    provider = enricher.PROVIDERS["madisound"]
    sitemap = """
    <urlset>
      <url><loc>https://www.madisoundspeakerstore.com/</loc></url>
      <url><loc>https://www.madisoundspeakerstore.com/index.php?p=site_map</loc></url>
      <url><loc>https://www.madisoundspeakerstore.com/about-us</loc></url>
      <url><loc>https://www.madisoundspeakerstore.com/approx-8-woofers/</loc></url>
      <url><loc>https://www.madisoundspeakerstore.com/approx-8-woofers/</loc></url>
    </urlset>
    """
    urls = enricher.provider_product_urls(provider, sitemap)
    assert urls == ["https://www.madisoundspeakerstore.com/approx-8-woofers/"], urls

    html = """
    <a href="https://www.madisoundspeakerstore.com/approx-8-woofers/?sort_by=priority&amp;page=2">2</a>
    <script type="application/ld+json">
    {
      "@context": "http://schema.org",
      "@type": "CollectionPage",
      "about": [
        {
          "@type": "Product",
          "name": "SB Acoustics SB20PFCR30-8 8\\" Paper Cone Woofer- 8 ohm",
          "mpn": "SB20PFCR30-8",
          "sku": "",
          "url": "https://www.madisoundspeakerstore.com/approx-8-woofers/sb20pfcr30-8/",
          "offers": {
            "@type": "Offer",
            "price": "57.10000",
            "priceCurrency": "USD",
            "availability": "http://schema.org/InStock"
          }
        }
      ]
    }
    </script>
    """
    page_url = urls[0]
    products = enricher.product_records_from_html(html, page_url)
    assert len(products) == 1
    assert products[0]["price"] == 57.1
    assert products[0]["currency"] == "USD"
    candidate = enricher.PresetCandidate(
        name="LSDB: SB Acoustics SB20PFCR30-8",
        brand="SB Acoustics",
        model="SB20PFCR30-8",
        query="SB20PFCR30-8",
    )
    assert enricher.match_score(candidate, products[0]) >= 0.8

    assert enricher.provider_next_url(provider, html, page_url) == f"{page_url}?page=2"
    assert enricher.madisound_next_url(html, f"{page_url}?page=2") == ""

    kit = {
        "name": "Seas A26 Kit (Pair) with A26RE4 woofers",
        "brand": "",
        "mpn": "A26",
        "sku": "A26",
        "url": "https://www.madisoundspeakerstore.com/speaker-kits/seas-a26/",
        "price": 480.0,
        "currency": "USD",
    }
    assert enricher.product_looks_like_driver(kit) is False


test("Price enricher supports the Madisound provider", _check_price_enricher_supports_madisound_provider)


def _check_price_enricher_supports_partsexpress_provider():
    from tools import enrich_driver_prices as enricher

    provider = enricher.PROVIDERS["partsexpress"]
    sitemap = """
    <urlset>
      <url><loc>https://www.parts-express.com/Tang-Band-W5-1138SMF-5-1-4-Paper-Cone-Subwoofer-Speaker-264-917</loc></url>
      <url><loc>https://www.parts-express.com/Tang-Band-W5-1138SMF-5-1-4-Paper-Cone-Subwoofer-Speaker-264-917</loc></url>
      <url><loc>https://www.parts-express.com/speaker-components</loc></url>
    </urlset>
    """
    urls = enricher.provider_product_urls(provider, sitemap)
    assert urls == [
        "https://www.parts-express.com/Tang-Band-W5-1138SMF-5-1-4-Paper-Cone-Subwoofer-Speaker-264-917"
    ], urls

    api_payload = {
        "items": [
            {
                "itemid": "264-917",
                "displayname": 'Tang Band W5-1138SMF 5-1/4" Paper Cone Subwoofer Speaker',
                "manufacturer": "Tang Band",
                "onlinecustomerprice": 43.98,
                "pricelevel1": 43.98,
                "isinstock": True,
            }
        ]
    }
    products = enricher.partsexpress_records_from_api(api_payload, urls[0])
    assert len(products) == 1
    product = products[0]
    assert product["price"] == 43.98
    assert product["currency"] == "USD"
    assert product["brand"] == "Tang Band"
    candidate = enricher.PresetCandidate(
        name="LSDB: Tang Band W5-1138SMF",
        brand="Tang Band",
        model="W5-1138SMF",
        query="W5-1138SMF",
    )
    assert enricher.match_score(candidate, product) >= 0.8
    payload = {"prices": {}, "catalog": {}}
    assert enricher.ingest_product(product, [candidate], payload, provider.seller, 0.8) is True
    assert payload["prices"]["LSDB: Tang Band W5-1138SMF"]["price"] == 43.98


test("Price enricher supports the Parts Express provider", _check_price_enricher_supports_partsexpress_provider)


def _check_price_enricher_brand_aliases_and_model_variants():
    from tools import enrich_driver_prices as enricher

    eighteen = enricher.PresetCandidate(
        name="LSDB: Eighteen Sound 10NW650",
        brand="Eighteen Sound",
        model="10NW650",
        query="10NW650",
    )
    product = {
        "name": '18 Sound 10NW650 - 10" 400W 8 Ohm',
        "brand": "",
        "mpn": "",
        "sku": "EIG10NW650",
        "url": "https://www.bluearan.co.uk/index.php?id=EIG10NW650",
        "price": 189.99,
        "currency": "GBP",
    }
    assert enricher.match_score(eighteen, product) >= 0.8

    faital = enricher.PresetCandidate(
        name="LSDB: FaitalPRO 21XL3000 4Ω",
        brand="FaitalPRO",
        model="21XL3000 4Ω",
        query="21XL3000 4Ω",
    )
    product = {
        "name": 'FaitalPRO 21XL3000 - 21" 3000W',
        "brand": "",
        "mpn": "",
        "sku": "FTP21XL3000",
        "url": "https://www.bluearan.co.uk/index.php?id=FTP21XL3000",
        "price": 599.0,
        "currency": "GBP",
    }
    assert enricher.match_score(faital, product) >= 0.8


test("Price enricher matches brand aliases and model variants", _check_price_enricher_brand_aliases_and_model_variants)


def _check_price_enricher_keeps_existing_record_across_currencies():
    from tools import enrich_driver_prices as enricher

    candidate = enricher.PresetCandidate(
        name="LSDB: Eminence Delta 12A",
        brand="Eminence",
        model="Delta 12A",
        query="Delta 12A",
    )
    eur_product = {
        "name": "Eminence Delta 12A Woofer",
        "brand": "Eminence",
        "mpn": "Delta 12A",
        "sku": "Delta 12A",
        "url": "https://www.soundimports.eu/en/eminence-delta-12a.html",
        "price": 119.95,
        "currency": "EUR",
    }
    gbp_product = {
        "name": 'Eminence Delta 12A - 12" 400W 8 Ohm',
        "brand": "",
        "mpn": "",
        "sku": "EMIDEL12A",
        "url": "https://www.bluearan.co.uk/index.php?id=EMIDEL12A",
        "price": 103.99,
        "currency": "GBP",
    }
    payload = {"prices": {}, "catalog": {}}
    assert enricher.ingest_product(eur_product, [candidate], payload, "SoundImports", 0.8) is True
    assert enricher.ingest_product(gbp_product, [candidate], payload, "BlueAran", 0.8) is True
    record = payload["prices"][candidate.name]
    assert record["currency"] == "EUR"
    assert record["price"] == 119.95
    cheaper_eur = dict(eur_product, price=99.95)
    assert enricher.ingest_product(cheaper_eur, [candidate], payload, "SoundImports", 0.8) is True
    assert payload["prices"][candidate.name]["price"] == 99.95


test("Price enricher keeps existing records across currencies", _check_price_enricher_keeps_existing_record_across_currencies)


def _check_ui_batch_finder_ranks_presets_in_requested_volume():
    import ui_app as _ui

    names = ("KEF B110B article example", "Beyma 12CMV2", "Scan-Speak 15W/4531G00")
    rows = _ui._batch_rank_presets(
        names,
        "DCCAV",
        20.0,
        2.83,
        10.0,
        300.0,
        120,
        len(names),
    )
    assert rows, rows
    f3_values = [_ui._rank_value(row["F3 Hz"]) for row in rows]
    assert f3_values == sorted(f3_values), f3_values
    first = rows[0]
    assert abs(first["Vh L"] + first["Vl L"] - 20.0) < 1e-6, first
    assert np.isfinite(first["Peak dB"]), first
    spark = first.get("Response")
    assert isinstance(spark, list) and len(spark) > 10, "rows must carry a response sparkline"
    assert max(spark) <= 1e-9 and min(spark) >= -30.0 - 1e-9, (min(spark), max(spark))
    assert any(value < -1.0 for value in spark), "sparkline must show the LF roll-off"


test("UI batch finder ranks drivers in a requested DCCAV volume", _check_ui_batch_finder_ranks_presets_in_requested_volume)


def _check_ui_batch_finder_supports_reflex_volume():
    import ui_app as _ui

    rows = _ui._batch_rank_presets(
        ("KEF B110B article example", "Beyma 12CMV2"),
        "Bass reflex",
        30.0,
        2.83,
        10.0,
        300.0,
        120,
        2,
    )
    assert rows, rows
    assert all(abs(row["Vb L"] - 30.0) < 1e-9 for row in rows), rows
    assert all(np.isfinite(row["Fb Hz"]) for row in rows), rows
    sealed_rows = _ui._batch_rank_presets(
        ("KEF B110B article example", "Beyma 12CMV2"),
        "Sealed", 25.0, 2.83, 10.0, 300.0, 120, 2,
    )
    assert sealed_rows
    assert all(abs(row["Vb L"] - 25.0) < 1e-9 for row in sealed_rows)
    assert all(np.isfinite(row["Fc Hz"]) and np.isfinite(row["Qtc"]) for row in sealed_rows)
    ib_rows = _ui._batch_rank_presets(
        ("KEF B110B article example", "Beyma 12CMV2"),
        "Infinite baffle", 25.0, 2.83, 10.0, 300.0, 120, 2,
    )
    assert ib_rows
    assert all(np.isnan(row["Vb L"]) for row in ib_rows)
    assert all(np.isfinite(row["Fc Hz"]) and np.isfinite(row["Qtc"]) for row in ib_rows)


test("UI batch finder supports reflex, sealed and infinite-baffle loads", _check_ui_batch_finder_supports_reflex_volume)


def _check_ui_batch_finder_optimizes_each_driver():
    import ui_app as _ui

    names = ("KEF B110B article example", "Beyma 12CMV2")
    goals = _dccav.OptimizationGoals(objective="extension")
    heuristic = {
        row["Driver"]: row
        for row in _ui._batch_rank_presets(names, "DCCAV", 30.0, 2.83, 10.0, 300.0, 120, len(names))
    }
    optimized = _ui._batch_rank_presets(
        names, "DCCAV", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert len(optimized) == len(names), optimized
    for row in optimized:
        assert abs(row["Vh L"] + row["Vl L"] - 30.0) < 1e-6, row
        assert np.isfinite(row["Ripple dB"]), row
        baseline = heuristic[row["Driver"]]["F3 Hz"]
        assert row["F3 Hz"] <= baseline * 1.02, (row["Driver"], row["F3 Hz"], baseline)

    reflex_rows = _ui._batch_rank_presets(
        names, "Bass reflex", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert reflex_rows
    for row in reflex_rows:
        assert abs(row["Vb L"] - 30.0) < 1e-9, row

    sealed_rows = _ui._batch_rank_presets(
        names, "Sealed", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert sealed_rows
    for row in sealed_rows:
        assert abs(row["Vb L"] - 30.0) < 1e-9, row


test("UI batch finder optimizes each driver with goals", _check_ui_batch_finder_optimizes_each_driver)


def _check_ui_batch_result_applies_selected_driver_and_box():
    import streamlit as st

    import ui_app as _ui

    row = {
        "Driver": "KEF B110B article example",
        "Vh L": 7.0,
        "fh Hz": 100.0,
        "Vl L": 13.0,
        "fl Hz": 45.0,
    }
    _ui._apply_batch_result(row, "DCCAV")
    assert st.session_state["load_type"] == "DCCAV"
    assert st.session_state["driver_preset_name"] == "KEF B110B article example"
    assert st.session_state["sim_auto_align"] is False
    assert st.session_state["box_strategy"] == "Manual"
    assert st.session_state["workspace_mode"] == "Design a box"
    assert st.session_state["box_vh_l"] == 7.0
    assert st.session_state["box_fh_hz"] == 100.0
    assert st.session_state["box_vl_l"] == 13.0
    assert st.session_state["box_fl_hz"] == 45.0
    assert abs(st.session_state["driver_fs_hz"] - 48.14) < 1e-9

    reflex_row = {
        "Driver": "Beyma 12CMV2",
        "Vb L": 42.0,
        "Fb Hz": 51.0,
    }
    _ui._apply_batch_result(reflex_row, "Bass reflex")
    assert st.session_state["load_type"] == "Bass reflex"
    assert st.session_state["driver_preset_name"] == "Beyma 12CMV2"
    assert st.session_state["reflex_vb_l"] == 42.0
    assert st.session_state["reflex_fb_hz"] == 51.0
    assert abs(st.session_state["driver_fs_hz"] - 49.0) < 1e-9
    sealed_row = {"Driver": "KEF B110B article example", "Vb L": 16.0}
    _ui._apply_batch_result(sealed_row, "Sealed")
    assert st.session_state["load_type"] == "Sealed"
    assert st.session_state["sealed_vb_l"] == 16.0
    _ui._apply_batch_result({"Driver": "Beyma 12CMV2"}, "Infinite baffle")
    assert st.session_state["load_type"] == "Infinite baffle"


test("UI candidate apply opens a manual design", _check_ui_batch_result_applies_selected_driver_and_box)


def _check_ui_batch_pending_result_applies_before_widgets():
    import streamlit as st

    import ui_app as _ui

    st.session_state["batch_pending_result"] = {
        "load_type": "Bass reflex",
        "row": {
            "Driver": "KEF B110B article example",
            "Vb L": 18.0,
            "Fb Hz": 55.0,
        },
    }
    _ui._apply_pending_batch_result()
    assert "batch_pending_result" not in st.session_state
    assert st.session_state["load_type"] == "Bass reflex"
    assert st.session_state["driver_preset_name"] == "KEF B110B article example"
    assert st.session_state["reflex_vb_l"] == 18.0
    assert st.session_state["reflex_fb_hz"] == 55.0


test("UI batch pending result applies before widget instantiation", _check_ui_batch_pending_result_applies_before_widgets)


def _check_optimizer_respects_volume_cap():
    ts = _dccav.get_driver_preset("Beyma 12CMV2")
    goals = _dccav.OptimizationGoals(objective="extension", max_total_volume_l=60.0)
    opt = _dccav.optimize_alignment(ts, goals)
    assert isinstance(opt.box, _dccav.DccavBox)
    assert opt.total_volume_l <= 60.0 * 1.001, opt.total_volume_l
    assert np.isfinite(opt.f3_hz), opt
    assert np.isfinite(opt.group_delay_ms), opt
    assert opt.box.fh_hz > opt.box.fl_hz, opt.box
    assert opt.evaluations > 10
    low_cap = _dccav.optimize_alignment(
        _dccav.get_driver_preset("Beyma 12BR70"),
        _dccav.OptimizationGoals(objective="extension", max_total_volume_l=1.0),
    )
    assert low_cap.total_volume_l <= 1.0 + 1e-9, low_cap.total_volume_l


test("DCCAV optimizer respects a total volume cap", _check_optimizer_respects_volume_cap)


def _check_optimizer_extension_beats_empirical():
    ts = _dccav.get_driver_preset("Beyma 12CMV2")
    align = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=align.vh_l, fh_hz=align.fh_hz, vl_l=align.vl_l, fl_hz=align.fl_hz)
    baseline = _dccav.response_threshold_frequencies(_dccav.simulate(ts, box))[3]
    opt = _dccav.optimize_alignment(ts, _dccav.OptimizationGoals(objective="extension"))
    assert opt.f3_hz <= baseline + 0.5, (opt.f3_hz, baseline)


test("DCCAV optimizer extension goal reaches at least the empirical F3", _check_optimizer_extension_beats_empirical)


def _check_optimizer_target_f3_prefers_compact_box():
    ts = _dccav.get_driver_preset("Beyma 12CMV2")
    opt = _dccav.optimize_alignment(
        ts, _dccav.OptimizationGoals(objective="balanced", target_f3_hz=55.0)
    )
    assert opt.f3_hz <= 55.0 * 1.05, opt.f3_hz
    unconstrained = _dccav.optimize_alignment(ts, _dccav.OptimizationGoals(objective="balanced"))
    assert opt.total_volume_l < unconstrained.total_volume_l, (
        opt.total_volume_l, unconstrained.total_volume_l
    )


test("DCCAV optimizer target F3 prefers the compact box", _check_optimizer_target_f3_prefers_compact_box)


def _check_optimizer_supports_bass_reflex():
    ts = _dccav.get_driver_preset("Beyma 12CMV2")
    opt = _dccav.optimize_alignment(
        ts,
        _dccav.OptimizationGoals(objective="balanced", max_total_volume_l=80.0),
        load_type="Bass reflex",
    )
    assert isinstance(opt.box, _dccav.ReflexBox)
    assert opt.total_volume_l <= 80.0 * 1.001, opt.total_volume_l
    assert np.isfinite(opt.f3_hz), opt
    sealed = _dccav.optimize_alignment(
        ts,
        _dccav.OptimizationGoals(objective="balanced", max_total_volume_l=50.0),
        load_type="Sealed",
    )
    assert isinstance(sealed.box, _dccav.SealedBox)
    assert sealed.total_volume_l <= 50.0 + 1e-9, sealed.total_volume_l
    assert np.isfinite(sealed.f3_hz), sealed

    for load_type, volume_l in (
        ("DCCAV", 40.0),
        ("Bass reflex", 45.0),
        ("Sealed", 50.0),
    ):
        fixed = _dccav.optimize_alignment(
            ts,
            _dccav.OptimizationGoals(objective="balanced", max_total_volume_l=volume_l),
            load_type=load_type,
            fixed_total_volume_l=volume_l,
        )
        assert abs(fixed.total_volume_l - volume_l) < 1e-9, fixed


test("Reflex and sealed optimizers respect capped and fixed volumes", _check_optimizer_supports_bass_reflex)


def _check_ui_supports_sealed_and_infinite_baffle():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui
    assert _ui._apply_loaded_params({"load_type": "Suspension pneumatic"}) == 1
    assert _ui.st.session_state["load_type"] == "Sealed"
    assert _ui._apply_loaded_params({"load_type": "Acoustic suspension"}) == 1
    assert _ui.st.session_state["load_type"] == "Sealed"

    for load_type, expected_metric in (
        ("Sealed", "Vb sealed (active)"),
        ("Infinite baffle", "Infinite baffle Fs"),
    ):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
        at.session_state["workspace_mode"] = "Design a box"
        at.session_state["load_type"] = load_type
        at.run()
        assert not at.exception, at.exception
        metrics = {metric.label: metric.value for metric in at.metric}
        assert expected_metric in metrics, (load_type, metrics)
        assert not any(control.label == "Box volume (L)" for control in at.number_input)
        if load_type == "Infinite baffle":
            assert not any(button.label == "Run optimizer and apply" for button in at.button)

        at.session_state["workspace_mode"] = "Find a driver"
        at.run()
        assert not at.exception, at.exception
        assert not at.tabs, "driver ranking must be a separate workspace, not a design tab"
        assert not any(box.label == "Driver preset" for box in at.selectbox)
        rank_button = next(button for button in at.sidebar.button if button.label == "Find drivers")
        assert not rank_button.disabled
        if load_type == "Infinite baffle":
            volume = next(n for n in at.number_input if n.label == "Comparison volume (L)")
            assert volume.disabled


test("UI separates design and driver-finder workflows", _check_ui_supports_sealed_and_infinite_baffle)


def _check_ui_finder_starts_from_practical_defaults():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception

    # Pre-workspace Batch widgets could leave their implicit minima in a live
    # Streamlit session. The redesigned Finder uses independent widget keys.
    for key, value in (
        ("batch_volume_l", 0.1),
        ("batch_voltage", 0.01),
        ("batch_candidate_limit", 1),
        ("batch_result_count", 1),
        ("batch_points", 80),
        ("batch_f_min", 1.0),
        ("batch_f_max", 10.0),
    ):
        at.session_state[key] = value
    at.session_state["workspace_mode"] = "Find a driver"
    at.run()
    assert not at.exception, at.exception

    numbers = {control.label: control.value for control in at.number_input}
    assert numbers["Comparison volume (L)"] == 40.0, numbers
    assert numbers["Comparison voltage (V)"] == 2.83, numbers
    assert numbers["Desired bass extension F3 (Hz, 0 = deepest)"] == 0.0, numbers
    assert numbers["Allowed response ripple (dB)"] == 3.0, numbers
    assert numbers["Maximum excursion (× driver Xmax)"] == 1.0, numbers
    assert numbers["Maximum group delay (ms)"] == 30.0, numbers
    assert numbers["Evaluation range start (Hz)"] == 10.0, numbers
    assert numbers["Evaluation range end (Hz)"] == 300.0, numbers
    assert numbers["Drivers to evaluate"] == 500, numbers
    assert numbers["Top results to show"] == 20, numbers
    assert numbers["Simulation resolution (points)"] == 240, numbers
    goal = next(box for box in at.selectbox if box.label == "Optimization goal")
    assert goal.value == "Balanced", goal.value
    optimize = next(
        box for box in at.checkbox
        if box.label == "Optimize enclosure per candidate"
    )
    assert optimize.value is False


test("UI Finder starts from practical independent defaults", _check_ui_finder_starts_from_practical_defaults)


def _check_ui_finder_parameters_are_all_in_sidebar():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Find a driver"
    at.run()
    assert not at.exception, at.exception

    number_labels = {
        "Comparison volume (L)",
        "Comparison voltage (V)",
        "Desired bass extension F3 (Hz, 0 = deepest)",
        "Allowed response ripple (dB)",
        "Maximum excursion (× driver Xmax)",
        "Maximum group delay (ms)",
        "Evaluation range start (Hz)",
        "Evaluation range end (Hz)",
        "Drivers to evaluate",
        "Top results to show",
        "Simulation resolution (points)",
    }
    sidebar_numbers = {control.label for control in at.sidebar.number_input}
    main_numbers = {control.label for control in at.main.number_input}
    assert number_labels <= sidebar_numbers, number_labels - sidebar_numbers
    assert number_labels.isdisjoint(main_numbers), number_labels & main_numbers
    assert any(box.label == "Optimization goal" for box in at.sidebar.selectbox)
    assert any(
        box.label == "Optimize enclosure per candidate"
        for box in at.sidebar.checkbox
    )
    assert any(button.label == "Reset Finder defaults" for button in at.sidebar.button)
    assert any(button.label == "Find drivers" for button in at.sidebar.button)
    assert not any(button.label == "Find drivers" for button in at.main.button)

    at.session_state["batch_results"] = [{
        "Driver": "Priced test driver", "Brand": "Test", "Size in": 8.0,
        "F3 Hz": 40.0, "F6 Hz": 32.0, "F10 Hz": 25.0,
        "Peak dB": 90.0, "Max excursion mm": 1.0, "Min ohm": 6.0,
        "Vb L": 40.0, "Fc Hz": 50.0, "Qtc": 0.707,
        "Price": 100.0, "Currency": "EUR", "Buy": "",
        "Ripple dB": 1.0, "Response": [], "Class": "Woofer",
    }]
    at.session_state["batch_result_context"] = (
        "Sealed", 40.0, 1, False, "Balanced",
    )
    at.run()
    assert not at.exception, at.exception
    assert any(radio.label == "Rank by" for radio in at.sidebar.radio)
    assert not any(radio.label == "Rank by" for radio in at.main.radio)


test("UI keeps every Finder parameter in the sidebar", _check_ui_finder_parameters_are_all_in_sidebar)


def _check_ui_finder_sidebar_action_runs_search():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    at.session_state["workspace_mode"] = "Find a driver"
    at.session_state["preset_search"] = "KEF B110B article example"
    at.session_state["finder_candidate_limit"] = 1
    at.session_state["finder_result_count"] = 1
    at.session_state["finder_points"] = 80
    at.run()
    assert not at.exception, at.exception

    find_button = next(
        button for button in at.sidebar.button if button.label == "Find drivers"
    )
    find_button.click().run()
    assert not at.exception, at.exception
    assert at.session_state["batch_results"], "sidebar action must produce ranked rows"
    assert at.dataframe, "ranked rows must appear in the main workspace"


test("UI Finder sidebar action runs the driver search", _check_ui_finder_sidebar_action_runs_search)


def _check_ui_purchase_links():
    import ui_app as _ui

    info = _dccav.DriverPresetInfo(
        name="LSDB: Eminence DELTA-12A",
        source="Loudspeaker Database",
        brand="Eminence",
        model="DELTA-12A",
        price=103.99,
        currency="GBP",
        url="https://www.bluearan.co.uk/index.php?id=EMIDEL12A",
    )
    line = _ui._purchase_markdown(info)
    assert line == (
        "[Buy · 103.99 GBP · bluearan.co.uk]"
        "(https://www.bluearan.co.uk/index.php?id=EMIDEL12A)"
    ), line

    no_price = _dccav.DriverPresetInfo(
        name="X", source="Built-in", brand="X", model="X",
        url="https://example.test/product",
    )
    assert _ui._purchase_markdown(no_price) == "[Buy · example.test](https://example.test/product)"

    no_url = _dccav.DriverPresetInfo(name="X", source="Built-in", brand="X", model="X", price=9.0)
    assert _ui._purchase_markdown(no_url) is None

    rows = _ui._batch_rank_presets(
        ("Beyma 12CMV2",), "DCCAV", 40.0, 2.83, 10.0, 300.0, 120, 1
    )
    assert rows and "Buy" in rows[0], rows


test("UI shows purchase links for enriched presets", _check_ui_purchase_links)


def _check_ui_optimized_alignment_mode():
    import streamlit as st

    import ui_app as _ui

    driver = _dccav.get_driver_preset("KEF B110B article example")
    _ui._apply_driver_preset(driver)
    for key, value in (
        ("load_type", "DCCAV"),
        ("box_vh_l", 3.0), ("box_fh_hz", 160.0), ("box_vl_l", 6.0), ("box_fl_hz", 60.0),
        ("loss_q_abs_h", 15.0), ("loss_q_abs_l", 15.0),
        ("loss_q_leak_h", 1000.0), ("loss_q_leak_l", 1000.0),
        ("loss_q_port_h", 15.0), ("loss_q_port_l", 15.0),
        ("sim_voltage", 2.83),
        ("opt_align_mode", "Optimized (goals)"),
        ("opt_objective", "Balanced"),
        ("opt_max_volume_l", 6.0),
        ("opt_target_f3_hz", 0.0),
        ("opt_max_ripple_db", 3.0),
        ("opt_excursion_ratio", 1.0),
        ("opt_max_gd_ms", 0.0),
    ):
        st.session_state[key] = value

    goals = _ui._optimizer_goals_from_state()
    assert goals.objective == "balanced"
    assert goals.max_total_volume_l == 6.0
    assert goals.target_f3_hz is None

    _ui._apply_suggested_box_for(driver)
    vtot = float(st.session_state["box_vh_l"]) + float(st.session_state["box_vl_l"])
    assert vtot <= 6.0 * 1.001, vtot
    assert str(st.session_state["opt_last_summary"]).startswith("Optimized"), (
        st.session_state.get("opt_last_summary")
    )
    assert _ui._current_optimizer_summary(driver) == st.session_state["opt_last_summary"]
    st.session_state["box_vl_l"] = float(st.session_state["box_vl_l"]) + 1.0
    assert _ui._current_optimizer_summary(driver) is None

    st.session_state["opt_align_mode"] = "Empirical (article)"
    _ui._apply_suggested_box_for(driver)
    expected = _dccav.suggest_alignment(driver)
    assert abs(float(st.session_state["box_vh_l"]) - expected.vh_l) < 1e-9


test("UI optimized alignment mode applies goal-driven boxes", _check_ui_optimized_alignment_mode)


def _check_ui_apply_button_respects_optimizer_mode():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Design a box"
    at.run()
    assert not at.exception, at.exception
    at.session_state["sim_auto_align"] = False
    at.session_state["load_type"] = "Bass reflex"
    at.session_state["box_strategy"] = "Optimized"
    at.session_state["opt_align_mode"] = "Optimized (goals)"
    at.session_state["opt_objective"] = "Max extension"
    at.run()
    assert not at.exception, at.exception
    vas_l = float(at.session_state["driver_vas_l"])
    button = next(b for b in at.button if b.label == "Run optimizer and apply")
    button.click()
    at.run()
    assert not at.exception, at.exception
    vb_l = float(at.session_state["reflex_vb_l"])
    assert vb_l > vas_l * 1.15, (vb_l, vas_l)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Vb (active)") == f"{vb_l:.2f} L", metrics
    at.session_state["load_type"] = "Sealed"
    at.session_state["box_strategy"] = "Optimized"
    at.session_state["opt_align_mode"] = "Optimized (goals)"
    at.session_state["opt_max_volume_l"] = 40.0
    at.run()
    assert not at.exception, at.exception
    sealed_button = next(b for b in at.button if b.label == "Run optimizer and apply")
    sealed_button.click()
    at.run()
    assert not at.exception, at.exception
    sealed_vb_l = float(at.session_state["sealed_vb_l"])
    assert sealed_vb_l <= 40.0 + 1e-9, sealed_vb_l
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Vb sealed (active)") == f"{sealed_vb_l:.2f} L", metrics


test("UI optimized strategy applies goal-driven boxes", _check_ui_apply_button_respects_optimizer_mode)


def _check_ui_progressive_disclosure():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    # New sessions land on the Finder workspace with the sealed load.
    assert at.session_state["workspace_mode"] == "Find a driver"
    assert at.session_state["load_type"] == "Sealed"
    assert not at.tabs, "the Finder landing must not show the design tabs"
    assert any(b.label == "Find drivers" for b in at.sidebar.button)
    assert at.session_state["driver_preset_name"] == "KEF B110B article example"

    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    assert not at.exception, at.exception
    assert [tab.label for tab in at.tabs] == [
        "Response", "Excursion", "Impedance", "Ports", "Group Delay", "Atlas",
    ]
    assert not any(n.label in {"M1 (Hz)", "M2 (Hz)"} for n in at.number_input)
    assert not any(n.label == "Series R (Ω)" for n in at.number_input)
    vh = next(n for n in at.number_input if n.label == "Vh upper (L)")
    assert vh.disabled, "suggested strategy must protect automatically managed box values"

    at.session_state["cursor_manual_enabled"] = True
    at.session_state["ui_show_advanced"] = True
    at.session_state["box_strategy"] = "Manual"
    at.session_state["sim_auto_align"] = False
    at.run()
    assert not at.exception, at.exception
    labels = {n.label for n in at.number_input}
    assert {"M1 (Hz)", "M2 (Hz)", "Series R (Ω)"} <= labels
    vh = next(n for n in at.number_input if n.label == "Vh upper (L)")
    assert not vh.disabled, "manual strategy must expose editable box values"


test("UI progressively reveals manual and advanced controls", _check_ui_progressive_disclosure)


def _check_ui_nudge_buttons_clamp_to_widget_bounds():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    at.session_state["box_strategy"] = "Manual"
    at.session_state["sim_auto_align"] = False
    at.session_state["box_vh_l"] = 999.0
    at.run()
    assert not at.exception, at.exception
    plus = next(b for b in at.sidebar.button if b.key == "box_vh_l_plus_3")
    plus.click().run()
    assert not at.exception, at.exception
    assert float(at.session_state["box_vh_l"]) == 1000.0, (
        "a nudge past the widget maximum must clamp there, not reset the input",
        at.session_state["box_vh_l"],
    )

    at.session_state["box_vh_l"] = 0.05
    at.run()
    minus = next(b for b in at.sidebar.button if b.key == "box_vh_l_minus_3")
    minus.click().run()
    assert not at.exception, at.exception
    assert float(at.session_state["box_vh_l"]) == 0.05, at.session_state["box_vh_l"]


test("UI nudge buttons clamp to the widget bounds", _check_ui_nudge_buttons_clamp_to_widget_bounds)


def _check_ui_response_window_includes_mol_trace():
    import ui_app as _ui

    ts = _kef_b110_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 300)
    result = _dccav.simulate(ts, box, freq, 2.83)
    mol = np.asarray(result.mol_db, dtype=float)
    mol_top = float(np.max(mol[np.isfinite(mol)]))

    series = {"Total": result.spl_total_db, "MOL": result.mol_db}
    domain = _ui._response_y_domain(result, series)
    assert domain is not None
    assert domain[1] >= mol_top, ("MOL must stay inside the y window", domain, mol_top)

    total_only = _ui._response_y_domain(result, {"Total": result.spl_total_db})
    assert total_only is not None
    assert domain[1] > total_only[1], "MOL must widen the window beyond the total trace"


test("UI response window widens to keep the MOL trace visible", _check_ui_response_window_includes_mol_trace)


def _check_ui_finder_goal_inputs_follow_optimizer_toggle():
    from streamlit.testing.v1 import AppTest

    goal_labels = (
        "Desired bass extension F3 (Hz, 0 = deepest)",
        "Allowed response ripple (dB)",
        "Maximum excursion (× driver Xmax)",
        "Maximum group delay (ms)",
    )
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Find a driver"
    at.run()
    assert not at.exception, at.exception
    inputs = {n.label: n for n in at.number_input}
    for label in goal_labels:
        assert inputs[label].disabled, (
            "goal constraints must read as inactive without the optimizer", label)
    goal = next(box for box in at.selectbox if box.label == "Optimization goal")
    assert goal.disabled, "the optimization goal must be inactive during a quick scan"
    assert not inputs["Evaluation range start (Hz)"].disabled
    assert not inputs["Evaluation range end (Hz)"].disabled

    at.session_state["finder_use_optimizer"] = True
    at.run()
    assert not at.exception, at.exception
    inputs = {n.label: n for n in at.number_input}
    for label in goal_labels:
        assert not inputs[label].disabled, (
            "goal constraints must unlock with the optimizer", label)
    goal = next(box for box in at.selectbox if box.label == "Optimization goal")
    assert not goal.disabled, "the optimization goal must unlock with the optimizer"


test("UI Finder goal constraints follow the optimizer toggle", _check_ui_finder_goal_inputs_follow_optimizer_toggle)


def _check_design_space_map():
    ts = _kef_b110_ts()
    space = _dccav.design_space_map(ts, "Bass reflex", resolution=7)
    assert space.f3_hz.shape == (7, 7) and space.ripple_db.shape == (7, 7)
    assert space.x_values[0] < space.x_values[-1]
    assert np.isfinite(space.f3_hz).mean() > 0.6, (
        "most of the reflex plane must produce a valid F3")

    start = _dccav.suggest_reflex_alignment(ts)
    freq = np.geomspace(min(10.0, ts.fs_hz / 4.0), max(400.0, 4.0 * ts.fs_hz), 160)
    base = _dccav.simulate_reflex(
        ts, _dccav.ReflexBox(vb_l=start.vb_l, fb_hz=start.fb_hz), freq)
    start_f3 = _dccav.response_threshold_frequencies(base)[3]
    assert np.nanmin(space.f3_hz) <= start_f3 + 0.5, (
        "the atlas must reach at least the starter's extension")

    ix, iy = 3, 2
    box = _dccav.design_space_box(
        ts, "Bass reflex", float(space.x_values[ix]), float(space.y_values[iy]))
    cell = _dccav.response_threshold_frequencies(
        _dccav.simulate_reflex(ts, box, freq))[3]
    got = float(space.f3_hz[iy, ix])
    assert (np.isnan(got) and np.isnan(cell)) or abs(got - cell) < 1e-6, (got, cell)

    sealed = _dccav.design_space_map(ts, "Sealed", resolution=9)
    assert sealed.y_values.shape == (1,)
    assert sealed.f3_hz[0, -1] < sealed.f3_hz[0, 0], (
        "a bigger sealed box must reach deeper bass")

    dccav_map = _dccav.design_space_map(ts, "DCCAV", resolution=5)
    assert dccav_map.f3_hz.shape == (5, 5)
    assert np.isfinite(dccav_map.f3_hz).any()

    try:
        _dccav.design_space_map(ts, "Infinite baffle")
    except ValueError as exc:
        assert "no box" in str(exc)
    else:
        raise AssertionError("infinite baffle must be rejected")
    try:
        _dccav.design_space_map(ts, "Bass reflex", resolution=2)
    except ValueError as exc:
        assert "resolution" in str(exc).casefold()
    else:
        raise AssertionError("a 2-point grid must be rejected")


test("DCCAV design-space atlas maps F3 and ripple over the box plane", _check_design_space_map)


def _check_ui_atlas_tab():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "Bass reflex"
    at.run()
    assert not at.exception, at.exception
    assert [tab.label for tab in at.tabs] == [
        "Response", "Excursion", "Impedance", "Ports", "Group Delay", "Atlas",
    ]
    assert any("Enable to map" in caption.value for caption in at.caption), (
        "atlas computation must stay gated behind the toggle")

    at.session_state["atlas_enabled"] = True
    at.run()
    assert not at.exception, at.exception
    assert any(
        "grid around the empirical starter" in caption.value
        for caption in at.caption
    ), "the enabled atlas must describe its grid"
    assert any(r.label == "Color by" for r in at.radio)

    state = _ui.st.session_state
    state["load_type"] = "Bass reflex"
    state["atlas_pending_point"] = {"load_type": "Bass reflex", "x": 25.0, "y": 40.0}
    _ui._apply_pending_atlas_point()
    assert float(state["reflex_vb_l"]) == 25.0
    assert float(state["reflex_fb_hz"]) == 40.0
    assert state["box_strategy"] == "Manual", "an applied atlas point must unlock the box"


test("UI Atlas tab gates the design-space map and applies clicked points", _check_ui_atlas_tab)


def _check_driver_configurations():
    ts = _kef_b110_ts()
    assert _dccav.apply_driver_configuration(ts, "Single driver") == ts

    par = _dccav.apply_driver_configuration(ts, "2 × parallel")
    assert par.sd_cm2 == ts.sd_cm2 * 2 and par.vas_l == ts.vas_l * 2
    assert par.re_ohm == ts.re_ohm / 2 and par.le_mh == ts.le_mh / 2
    assert par.pe_w == ts.pe_w * 2 and par.xmax_mm == ts.xmax_mm
    assert (par.fs_hz, par.qts, par.qms) == (ts.fs_hz, ts.qts, ts.qms)

    ser = _dccav.apply_driver_configuration(ts, "2 × series")
    assert ser.re_ohm == ts.re_ohm * 2 and ser.le_mh == ts.le_mh * 2
    assert ser.sd_cm2 == ts.sd_cm2 * 2 and ser.vas_l == ts.vas_l * 2

    iso = _dccav.apply_driver_configuration(ts, "Isobaric pair (parallel)")
    assert iso.sd_cm2 == ts.sd_cm2 and iso.vas_l == ts.vas_l / 2
    assert iso.re_ohm == ts.re_ohm / 2 and iso.pe_w == ts.pe_w * 2
    iso_s = _dccav.apply_driver_configuration(ts, "Isobaric pair (series)")
    assert iso_s.re_ohm == ts.re_ohm * 2 and iso_s.vas_l == ts.vas_l / 2

    measured = _dccav.DriverTS(
        fs_hz=40.0, vas_l=50.0, qts=0.4, qms=4.0, re_ohm=6.0, sd_cm2=200.0,
        mms_g=25.0, cms_mm_per_n=1.0, bl_tm=10.0)
    composite = _dccav.apply_driver_configuration(measured, "2 × parallel")
    assert composite.mms_g is None
    assert composite.cms_mm_per_n is None
    assert composite.bl_tm is None

    base_eta = _dccav.driver_reference_metrics(ts).eta0
    assert abs(_dccav.driver_reference_metrics(par).eta0 / base_eta - 2.0) < 0.05, (
        "a parallel pair must gain the classical +3 dB reference efficiency")
    assert abs(_dccav.driver_reference_metrics(iso).eta0 / base_eta - 0.5) < 0.05, (
        "an isobaric pair must trade -3 dB efficiency for half the box")

    try:
        _dccav.apply_driver_configuration(ts, "3 × weird")
    except ValueError as exc:
        assert "configuration" in str(exc)
    else:
        raise AssertionError("unknown configuration was accepted")


test("DCCAV driver configurations scale the composite T/S set", _check_driver_configurations)


def _check_ui_driver_configuration_selector():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    z_single = float(str(metrics["Min impedance"]).split()[0])
    vtot_single = float(str(metrics["Box volume"]).split()[0])

    config = next(s for s in at.selectbox if s.label == "Driver configuration")
    config.select("2 × parallel").run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    z_par = float(str(metrics["Min impedance"]).split()[0])
    vtot_par = float(str(metrics["Box volume"]).split()[0])
    assert z_par < 0.6 * z_single, (z_single, z_par)
    assert vtot_par > 1.5 * vtot_single, (vtot_single, vtot_par)
    assert any("Composite: Sd" in caption.value for caption in at.caption), (
        "the sidebar must summarize the composite driver"
    )


test("UI driver configuration re-aligns the box to the composite", _check_ui_driver_configuration_selector)


def _check_monte_carlo_tolerance_band():
    ts = _kef_b110_ts()
    a = _dccav.suggest_alignment(ts)
    box = _dccav.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 120)

    band = _dccav.monte_carlo_response_band(ts, "DCCAV", box, freq, runs=40, seed=7)
    assert band.frequency_hz.shape == freq.shape
    assert band.runs == 40
    assert np.all(band.lower_db <= band.upper_db + 1e-9)
    nominal = _dccav.simulate(ts, box, freq).spl_total_db
    inside = (nominal >= band.lower_db - 1e-6) & (nominal <= band.upper_db + 1e-6)
    assert inside.mean() > 0.9, "nominal response must sit inside the band"

    again = _dccav.monte_carlo_response_band(ts, "DCCAV", box, freq, runs=40, seed=7)
    np.testing.assert_allclose(band.lower_db, again.lower_db)
    np.testing.assert_allclose(band.upper_db, again.upper_db)

    collapsed = _dccav.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.0, runs=8)
    np.testing.assert_allclose(collapsed.lower_db, nominal, atol=1e-9)
    np.testing.assert_allclose(collapsed.upper_db, nominal, atol=1e-9)

    narrow = _dccav.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.05, runs=40, seed=7)
    wide = _dccav.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.20, runs=40, seed=7)
    assert (
        np.mean(wide.upper_db - wide.lower_db)
        > np.mean(narrow.upper_db - narrow.lower_db)
    ), "the band must widen with the tolerance"

    sealed = _dccav.monte_carlo_response_band(
        ts, "Sealed", _dccav.SealedBox(vb_l=ts.vas_l), freq, runs=12, seed=3)
    baffle = _dccav.monte_carlo_response_band(
        ts, "Infinite baffle", None, freq, runs=12, seed=3)
    for run in (sealed, baffle):
        assert np.all(np.isfinite(run.lower_db)) and np.all(np.isfinite(run.upper_db))

    try:
        _dccav.monte_carlo_response_band(ts, "DCCAV", box, freq, tolerance=1.5)
    except ValueError as exc:
        assert "Tolerance" in str(exc)
    else:
        raise AssertionError("tolerance >= 1 must be rejected")


test("DCCAV Monte Carlo band brackets the nominal response", _check_monte_carlo_tolerance_band)


def _check_ui_tolerance_band_toggle():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Design a box"
    at.session_state["load_type"] = "DCCAV"
    at.session_state["plot_tolerance_band"] = True
    at.run()
    assert not at.exception, at.exception
    assert any(
        "Monte Carlo on Fs/Vas/Qts/Qms" in caption.value for caption in at.caption
    ), "the band caption must describe the perturbation"
    tol = next(n for n in at.number_input if n.label == "T/S tolerance (%)")
    assert float(tol.value) == 15.0


test("UI tolerance band toggle renders the Monte Carlo caption", _check_ui_tolerance_band_toggle)


def _check_price_extension_score():
    assert _dccav.price_extension_score(30.0, 100.0) == 3000.0
    cheap_deep = _dccav.price_extension_score(40.0, 80.0)
    pricey_deeper = _dccav.price_extension_score(30.0, 400.0)
    assert cheap_deep < pricey_deeper, "the cheap driver must win on value"
    for bad in (float("nan"), 0.0, -5.0):
        assert _dccav.price_extension_score(bad, 100.0) == float("inf")
        assert _dccav.price_extension_score(30.0, bad) == float("inf")


test("DCCAV price-extension score prefers cheap deep drivers", _check_price_extension_score)


def _check_ui_finder_value_ranking():
    import ui_app as _ui

    rows = [
        {"Driver": "deep pricey", "F3 Hz": 30.0, "Price": 400.0, "Currency": "EUR"},
        {"Driver": "value pick", "F3 Hz": 40.0, "Price": 80.0, "Currency": "EUR"},
        {"Driver": "wrong currency", "F3 Hz": 25.0, "Price": 10.0, "Currency": "USD"},
        {"Driver": "unpriced", "F3 Hz": 20.0, "Price": float("nan"), "Currency": ""},
    ]
    df = _ui.pd.DataFrame(rows)
    out = _ui._value_sorted_frame(df, "EUR")
    assert list(out["Driver"]) == [
        "value pick", "deep pricey", "unpriced", "wrong currency",
    ], list(out["Driver"])
    assert float(out["Value"].iloc[0]) == 3200.0
    assert _ui.np.isnan(float(out["Value"].iloc[2])), "no-price rows must not show a score"

    _ui.st.session_state["preset_price_currency"] = "USD"
    assert _ui._finder_price_currency(df) == "USD"
    _ui.st.session_state["preset_price_currency"] = ""
    assert _ui._finder_price_currency(df) == "EUR", "fallback must pick the modal currency"

    from streamlit.testing.v1 import AppTest

    box_values = {"Vb L": 40.0, "Fc Hz": 55.0, "Qtc": 0.7}
    seeded = [
        {
            "Driver": name, "Source": "Built-in", "Brand": "Other", "Class": "Woofer",
            "Size in": 12.0, "Price": price, "Currency": "EUR", "Buy": "",
            "F3 Hz": f3, "F6 Hz": f3 - 5.0, "F10 Hz": f3 - 10.0,
            "Peak dB": 90.0, "Ripple dB": 1.0, "Max excursion mm": 3.0,
            "Min ohm": 6.0, "Response": [0.0, -3.0], **box_values,
        }
        for name, f3, price in (("A deep", 30.0, 400.0), ("B value", 40.0, 80.0))
    ]
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=30)
    at.session_state["workspace_mode"] = "Find a driver"
    # Match the live defaults version so the seeded results survive migration.
    at.session_state["_finder_defaults_version"] = _ui._FINDER_DEFAULTS_VERSION
    at.session_state["batch_results"] = seeded
    at.session_state["batch_result_context"] = ("Sealed", 40.0, 2, False, "Balanced")
    at.run()
    assert not at.exception, at.exception
    rank = next(r for r in at.radio if r.label == "Rank by")
    rank.set_value("Best value (F3 × price)").run()
    assert not at.exception, at.exception
    assert any(
        "Best value = lowest F3 × price in EUR" in caption.value
        for caption in at.caption
    ), "value mode must explain the currency-consistent score"


test("UI Finder ranks candidates by price-performance value", _check_ui_finder_value_ranking)


def _check_ui_parallel_ranking_matches_serial():
    import ui_app as _ui

    assert _ui._dccav.rank_preset_row("no such driver", "Sealed", 30.0, 2.83,
                                      10.0, 300.0, 120) is None

    names = ("KEF B110B article example", "Beyma 12CMV2", "Dayton Audio RSS315HO-4")
    goals = _ui._dccav.OptimizationGoals(objective="balanced")
    serial = _ui._batch_rank_presets(
        names, "Sealed", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals)
    parallel = _ui._batch_rank_presets_parallel(
        names, "Sealed", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals)
    assert [row["Driver"] for row in parallel] == [row["Driver"] for row in serial]
    for s_row, p_row in zip(serial, parallel, strict=True):
        assert abs(float(s_row["F3 Hz"]) - float(p_row["F3 Hz"])) < 1e-9
        assert abs(float(s_row["Vb L"]) - float(p_row["Vb L"])) < 1e-9
        assert s_row["Response"] == p_row["Response"]


test("UI parallel optimizer ranking matches the serial path", _check_ui_parallel_ranking_matches_serial)


def _check_ui_parallel_ranking_falls_back_when_processes_are_denied():
    import ui_app as _ui

    names = ("KEF B110B article example", "Beyma 12CMV2")
    goals = _ui._dccav.OptimizationGoals(objective="balanced")
    expected = _ui._batch_rank_presets(
        names, "Sealed", 30.0, 2.83, 10.0, 300.0, 80, len(names), goals=goals)
    original_executor = _ui.ProcessPoolExecutor

    class DeniedProcessPool:
        def __init__(self, *args, **kwargs):
            raise PermissionError("process semaphores denied")

    try:
        _ui.ProcessPoolExecutor = DeniedProcessPool
        actual = _ui._batch_rank_presets_parallel(
            names, "Sealed", 30.0, 2.83, 10.0, 300.0, 80, len(names), goals)
    finally:
        _ui.ProcessPoolExecutor = original_executor

    assert [row["Driver"] for row in actual] == [row["Driver"] for row in expected]
    for expected_row, actual_row in zip(expected, actual, strict=True):
        assert abs(float(expected_row["F3 Hz"]) - float(actual_row["F3 Hz"])) < 1e-9
        assert abs(float(expected_row["Vb L"]) - float(actual_row["Vb L"])) < 1e-9
        assert expected_row["Response"] == actual_row["Response"]


test("UI parallel Finder falls back when worker processes are denied", _check_ui_parallel_ranking_falls_back_when_processes_are_denied)


def _check_module_split_facade():
    import ast

    from src import engine, presets, pricing

    assert _dccav.DriverTS is engine.DriverTS
    assert _dccav.SimulationResult is engine.SimulationResult
    assert _dccav.simulate is engine.simulate
    assert _dccav.optimize_alignment is engine.optimize_alignment
    assert _dccav.design_space_map is engine.design_space_map
    assert _dccav.get_driver_preset is presets.get_driver_preset
    assert _dccav.driver_preset_info is presets.driver_preset_info
    assert _dccav.DRIVER_PRESETS is presets.DRIVER_PRESETS
    assert _dccav.price_extension_score is pricing.price_extension_score
    assert _dccav.DRIVER_PRICES_PATH is pricing.DRIVER_PRICES_PATH
    assert _dccav._load_driver_price_records is pricing._load_driver_price_records
    assert (
        _dccav._load_loudspeaker_database_presets
        is presets._load_loudspeaker_database_presets
    )

    # The engine must stay free of catalog and pricing knowledge.
    tree = ast.parse((ROOT / "src" / "engine.py").read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported |= {
        alias.name
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden = {"presets", "pricing", "src.presets", "src.pricing"}
    assert not forbidden & imported, imported


test("Module split keeps dccav a faithful facade", _check_module_split_facade)


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


if not _IS_MP_CHILD:
    print(f"\n{'=' * 40}")
    print(f"  PASS: {PASS}   FAIL: {FAIL}   SKIP: {SKIP}")
    print(f"{'=' * 40}")
    if MATCHES and PASS == 0 and FAIL == 0:
        print("No tests matched --match filter")
        sys.exit(2)
    sys.exit(0 if FAIL == 0 else 1)
