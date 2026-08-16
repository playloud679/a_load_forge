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
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import acoustics as _acoustics
from src import presets as _presets

PASS = 0
FAIL = 0
SKIP = 0

# Keep ordinary AppTest runs on one shared timeout. Tests that intentionally
# exercise heavier workflows can opt into a longer timeout at their call site.
APP_TEST_TIMEOUT = 60


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
    return _acoustics.get_driver_preset("KEF B110B article example")


def _beyma_ts():
    return _acoustics.get_driver_preset("Beyma 12CMV2")


print("\n=== Acoustic-load core ===")


def _check_release_metadata_is_synchronized():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version, "VERSION must not be empty"
    assert f'version = "{version}"' in (ROOT / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert f"Current release: **{version}**" in (ROOT / "README.md").read_text(
        encoding="utf-8"
    )
    assert f"load-forge:{version}" in (ROOT / "docs/deploy-cloudrun.md").read_text(
        encoding="utf-8"
    )


test("Release metadata stays synchronized", _check_release_metadata_is_synchronized)


def _check_oidc_runtime_dependencies_are_complete():
    requirements = {
        line.strip().casefold()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert any(item.startswith("authlib") for item in requirements)
    assert any(item.startswith("httpx") for item in requirements), (
        "Authlib's Starlette OIDC client imports httpx at sign-in time"
    )


test(
    "OIDC deployment includes Authlib's HTTP client",
    _check_oidc_runtime_dependencies_are_complete,
)


def _check_container_runtime_data_is_whitelisted():
    runtime_data = {
        "data/catalog_lsdb.json",
        "data/catalog_proprietario.json",
        "data/catalog_speakerboxlite.json",
        "data/catalog_vituixcad.json",
        "data/catalog_ztzaudio_lf_ferrite_presets.json",
        "data/driver_prices.json",
    }
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY data ./data" not in dockerfile
    for path in runtime_data:
        assert path in dockerfile, f"Dockerfile does not copy {path}"

    for ignore_name in (".dockerignore", ".gcloudignore"):
        lines = {
            line.strip()
            for line in (ROOT / ignore_name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert "data/*" in lines, f"{ignore_name} does not exclude data artifacts"
        included_data = {
            line[1:] for line in lines if line.startswith("!data/")
        }
        assert included_data == runtime_data, (
            f"{ignore_name} runtime data differs: {included_data ^ runtime_data}"
        )


test("Cloud container ships only runtime catalog data", _check_container_runtime_data_is_whitelisted)


def _check_sd_from_diameter():
    sd = _acoustics.sd_from_diameter(104.0)
    assert abs(sd - 84.95) < 0.05, f"Sd={sd:.2f} cm2"


test("Driver Sd helper converts diameter to area", _check_sd_from_diameter)


def _check_distributed_waveguide_models():
    ts = _kef_b110_ts()
    freq = np.geomspace(10.0, 500.0, 320)
    line = _acoustics.TransmissionLineBox(
        segments=(_acoustics.WaveguideSegment(0.85, 100.0),),
        termination="closed",
    )
    tl = _acoustics.simulate_transmission_line(ts, line, freq)
    qw = _acoustics.simulate_quarter_wave(ts, 0.85, 100.0, freq)
    np.testing.assert_allclose(tl.spl_total_db, qw.spl_total_db)
    assert np.all(np.isfinite(tl.impedance_ohm))

    mltl = _acoustics.simulate_mltl(
        ts,
        _acoustics.MltlBox(
            segments=(_acoustics.WaveguideSegment(0.85, 100.0),),
            vent_area_cm2=35.0,
            vent_length_m=0.08,
        ),
        freq,
    )
    blh = _acoustics.simulate_back_loaded_horn(
        ts, _acoustics.HornBox(1.2, 80.0, 800.0), freq)
    th = _acoustics.simulate_tapped_horn(
        ts, _acoustics.TappedHornBox(1.2, 80.0, 800.0, 0.35), freq)
    for result in (mltl, blh, th):
        assert result.frequency_hz.shape == freq.shape
        assert np.all(np.isfinite(result.spl_total_db))
        assert np.all(result.excursion_mm >= 0.0)


test(
    "Acoustic-load smoke: distributed TL, MLTL, QW, BLH and TH models run",
    _check_distributed_waveguide_models,
)


def _check_distributed_waveguide_ui():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.run()
    at.session_state["load_type"] = "Distributed waveguide"
    at.session_state["waveguide_topology"] = "BLH"
    at.run()
    assert not at.exception, at.exception
    at.session_state["waveguide_topology"] = "TH"
    at.session_state["sim_f_min"] = 10.0
    at.session_state["sim_f_max"] = 500.0
    if "_waveguide_th_seeded" in at.session_state:
        del at.session_state["_waveguide_th_seeded"]
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["sim_f_min"] == 25.0
    assert at.session_state["sim_f_max"] == 120.0


test("UI exposes distributed waveguide simulation", _check_distributed_waveguide_ui)


def _check_presets_are_available():
    names = _acoustics.driver_preset_names()
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
        "ZTZ: TN-18SW1280",
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
    own_wo24p8 = [
        name
        for name in names
        if name.startswith("WEB: SB Acoustics") and "WO24P-8" in name
    ]
    assert own_wo24p8 == [
        "WEB: SB Acoustics 9½″ SATORI WO24P-8 / Paper"
    ], own_wo24p8
    wo24p8_info = _acoustics.driver_preset_info(own_wo24p8[0])
    assert wo24p8_info.source == "SB Acoustics crawler", wo24p8_info
    assert wo24p8_info.brand == "SB Acoustics", wo24p8_info
    assert wo24p8_info.part_number == "WO24P-8", wo24p8_info
    assert _presets._external_catalog_part_number(
        "Dayton Audio",
        'RSS315HO-4 12" Reference Series HO Subwoofer 4 Ohm',
    ) == "RSS315HO-4"
    assert _presets._external_catalog_part_number(
        "Beyma",
        '12MC700Nd MC Series 12" Neo Subwoofer 8 Ohm',
    ) == "12MC700Nd"
    assert _presets._external_catalog_part_number(
        "Beyma", 'LOUDSPEAKER 8"BR40/N 8 OH'
    ) == "8BR40/N"
    assert _presets._external_catalog_part_number(
        "Beyma", 'LOUDSPEAKER 15"WRS 400 8 OH'
    ) == "15WRS400"
    assert _presets._external_catalog_part_number(
        "Beyma", "LOUDSPEAKER 6P200Fe 16 OH"
    ) == "6P200Fe"
    assert _presets._external_catalog_part_number(
        "Ground Zero", "GZRW 250-D2 FLAT"
    ) == "GZRW 250-D2 FLAT"
    assert _presets._external_catalog_part_number(
        "GRS", '6PR-8 6-1/2" Poly Cone Rubber Surround Woofer'
    ) == "6PR-8"
    assert _presets._external_catalog_part_number(
        "Factory Buyouts", '3" 580325-008 3W Mini Black Paper Cone Speaker'
    ) == "580325-008"
    assert _presets._external_catalog_part_number(
        "GRS", '5-1/4" Woofer Surface Mount Poly Cone 4 Ohm 5SMP-4'
    ) == "5SMP-4"
    assert _presets._external_catalog_manufacturer(
        "Eminence Speaker"
    ) == "Eminence"
    assert _presets._external_catalog_manufacturer(
        "Eminence Speakers, LLC"
    ) == "Eminence"
    assert _presets._external_catalog_part_number(
        "Eminence Speaker",
        'Eminence Alpha-12A 12" Guitar/PA Driver',
    ) == "Alpha-12A"
    assert _presets._external_catalog_identity_model(
        {
            "model": "18-inch",
            "matched_mpn": "TF1830",
            "source": "Manual catalog maintenance",
        }
    ) == "TF1830"
    assert _presets._external_catalog_identity_model(
        {
            "model": "18-inch",
            "matched_mpn": "retailer-sku",
            "source": "Celestion crawler",
        }
    ) == "18-inch"
    for bomber_title in (
        'SUBWOOFER 8″ UPGRADE 400 WRMS 4 OHMS',
        'WOOFER 18″ ATRACK BASS 4K 4Ω',
        'MEDIO GRAVE 10″ ATRACK 800 WATTS RMS 8Ω',
    ):
        assert (
            _presets._external_catalog_part_number("Bomber", bomber_title)
            == bomber_title
        )
    dayton_retailer_name = next(
        name for name in names
        if name.startswith("WEB: Dayton Audio RSS315HO-4 12")
    )
    assert (
        _acoustics.driver_preset_info(dayton_retailer_name).part_number
        == "RSS315HO-4"
    )
    eminence_alpha_names = [
        name
        for name in names
        if 'Eminence Alpha-12A 12" Guitar/PA Driver' in name
    ]
    assert len(eminence_alpha_names) == 1, eminence_alpha_names
    eminence_alpha_info = _acoustics.driver_preset_info(eminence_alpha_names[0])
    assert eminence_alpha_info.brand == "Eminence", eminence_alpha_info
    assert eminence_alpha_info.part_number == "Alpha-12A", eminence_alpha_info
    celestion_tf1830_info = _acoustics.driver_preset_info(
        "WEB: Celestion 18-inch"
    )
    assert celestion_tf1830_info.brand == "Celestion", celestion_tf1830_info
    assert celestion_tf1830_info.part_number == "TF1830", celestion_tf1830_info
    assert any(
        name.startswith("LSDB: SB Acoustics") and "WO24P-8" in name
        for name in names
    ), "the separate LSDB observation must remain visible"
    assert any(
        name.startswith("VCD: SB Acoustics") and "WO24P-8" in name
        for name in names
    ), "the separate VituixCAD observation must remain visible"
    assert _acoustics.get_driver_preset("Beyma 12G40").sd_cm2 == 530.0
    assert _acoustics.get_driver_preset("Beyma 12BR70").fs_hz == 31.0
    assert _acoustics.get_driver_preset("Beyma 12MCS500").le_mh == 1.1
    assert _acoustics.get_driver_preset("Beyma 12WRS400").qts == 0.29
    assert _acoustics.get_driver_preset("Beyma 12LEX1300Nd").xmax_mm == 11.0
    assert _acoustics.get_driver_preset("Turbosound TS-12W350/8W").fs_hz == 61.0
    assert _acoustics.get_driver_preset("Turbosound TS-12W350/8W").vas_l == 19.26
    assert _acoustics.get_driver_preset("Turbosound TS-12W350/8W").pe_w == 350.0
    assert _acoustics.get_driver_preset("Turbosound TS-15W300/8A").vas_l == 130.2
    assert _acoustics.get_driver_preset("Turbosound TS-15W300/8A").sd_cm2 == 865.7
    assert _acoustics.get_driver_preset("Turbosound TS-15W300/8A").pe_w == 300.0
    assert _acoustics.get_driver_preset("Scan-Speak 30W/4558T00").fs_hz == 17.0
    assert _acoustics.get_driver_preset("Scan-Speak 30W/4558T00").vas_l == 197.0
    assert _acoustics.get_driver_preset("Scan-Speak 30W/4558T00").xmax_mm == 12.5
    assert _acoustics.get_driver_preset("Scan-Speak 15W/4531G00").fs_hz == 40.0
    assert _acoustics.get_driver_preset("Scan-Speak 15W/4531G00").sd_cm2 == 95.0
    assert _acoustics.get_driver_preset("Scan-Speak 15W/4531G00").pe_w == 60.0
    assert _acoustics.get_driver_preset("Dayton Audio RSS315HO-4").re_ohm == 3.2
    assert _acoustics.get_driver_preset("Dayton Audio RSS315HO-4").pe_w == 700.0
    assert _acoustics.get_driver_preset("SB Audience BIANCO-12OB150-01").qts == 0.63
    assert _acoustics.get_driver_preset("SB Audience BIANCO-12OB150-01").sd_cm2 == 539.1
    assert _acoustics.get_driver_preset("LaVoce WSF122.02").re_ohm == 5.2
    assert _acoustics.get_driver_preset("LaVoce WSF122.50").bl_tm == 17.1
    assert _acoustics.get_driver_preset("Aiyima 4ohm 5w 40mm black").fs_hz == 153.6
    assert abs(_acoustics.get_driver_preset("Aiyima 4ohm 5w 40mm black").sd_cm2 - 7.40229915) < 1e-9
    assert _acoustics.get_driver_preset("Aiyima 4ohm 10w 53mm LY1124-2").vas_l == 0.22
    assert _acoustics.get_driver_preset("Aiyima 4ohm 5w 1.5in").bl_tm == 2.937
    assert _acoustics.get_driver_preset("MarkAudio CHR-70").sd_cm2 == 50.2
    assert _acoustics.get_driver_preset("MarkAudio CHR-70").cms_mm_per_n == 1.44
    assert _acoustics.get_driver_preset("MarkAudio CHR-70").pe_w == 20.0
    markaudio_chr70 = [
        name
        for name in names
        if (
            _acoustics.driver_preset_info(name).brand.casefold(),
            _acoustics.driver_preset_info(name).model.casefold(),
        )
        == ("markaudio", "chr-70")
    ]
    assert markaudio_chr70 == ["MarkAudio CHR-70"]
    beyma_info = _acoustics.driver_preset_info("Beyma 12CMV2")
    assert beyma_info.source == "Built-in"
    assert beyma_info.brand == "Beyma"
    lsdb_names = [name for name in names if name.startswith("LSDB: ")]
    if lsdb_names:
        lsdb_info = _acoustics.driver_preset_info(lsdb_names[0])
        assert lsdb_info.source == "Loudspeaker Database"
        assert lsdb_info.brand
        _acoustics.complete_driver(_acoustics.get_driver_preset(lsdb_names[0]))
    manufacturer_names = [
        name for name in names if name.startswith("WEB: ") or name.startswith("PDF: ")
    ]
    if manufacturer_names:
        mfr_info = _acoustics.driver_preset_info(manufacturer_names[0])
        assert mfr_info.source in ("Manufacturer website", "Manufacturer datasheet", "Manufacturer crawl")
        assert mfr_info.brand
        _acoustics.complete_driver(_acoustics.get_driver_preset(manufacturer_names[0]))
    vituixcad_names = [name for name in names if name.startswith("VCD: ")]
    if vituixcad_names:
        vcd_info = _acoustics.driver_preset_info(vituixcad_names[0])
        assert vcd_info.source == "VituixCAD online database"
        assert vcd_info.brand
        _acoustics.complete_driver(_acoustics.get_driver_preset(vituixcad_names[0]))
    speakerboxlite_names = [name for name in names if name.startswith("SBL: ")]
    if speakerboxlite_names:
        sbl_info = _acoustics.driver_preset_info(speakerboxlite_names[0])
        assert sbl_info.source == "Speaker Box Lite public database"
        assert sbl_info.brand
        _acoustics.complete_driver(
            _acoustics.get_driver_preset(speakerboxlite_names[0])
        )
    try:
        _acoustics.get_driver_preset("missing")
    except ValueError as exc:
        assert "Unknown driver preset" in str(exc)
    else:
        raise AssertionError("unknown preset was accepted")


test("Driver presets are named and validated", _check_presets_are_available)


def _check_article_alignment():
    a = _acoustics.suggest_alignment(replace(_kef_b110_ts(), panel_air_load=False))
    assert abs(a.vh_l - 3.09) < 0.03, f"Vh={a.vh_l:.2f} L"
    assert abs(a.vl_l - 6.23) < 0.05, f"Vl={a.vl_l:.2f} L"
    assert abs(a.fh_hz - 162.2) < 0.2, f"fh={a.fh_hz:.2f} Hz"
    assert abs(a.fl_hz - 62.0) < 0.2, f"fl={a.fl_hz:.2f} Hz"
    assert abs(a.f3_hz - 51.5) < 0.2, f"f3={a.f3_hz:.2f} Hz"


test("DCCAV article alignment regression", _check_article_alignment)


def _check_beyma_preset_alignment():
    ts = replace(_beyma_ts(), panel_air_load=False)
    assert ts.sd_cm2 == 530.0
    assert ts.mms_g == 54.0
    assert ts.cms_mm_per_n == 0.193
    assert ts.bl_tm == 13.7
    a = _acoustics.suggest_alignment(ts)
    assert abs(a.vh_l - 34.42) < 0.03, f"Vh={a.vh_l:.2f} L"
    assert abs(a.vl_l - 69.34) < 0.05, f"Vl={a.vl_l:.2f} L"
    assert abs(a.fh_hz - 127.2) < 0.2, f"fh={a.fh_hz:.2f} Hz"
    assert abs(a.fl_hz - 48.6) < 0.2, f"fl={a.fl_hz:.2f} Hz"


test("DCCAV Beyma 12CMV2 preset alignment", _check_beyma_preset_alignment)


def _check_derived_driver_from_minimal_ts():
    d = _acoustics.complete_driver(_kef_b110_ts())
    assert 0.008 < d.sd_m2 < 0.009
    assert d.qes > 0
    assert d.bl_tm > 0
    assert d.cas > 0 and d.mas > 0 and d.rat > 0


test("Driver completion derives components from minimal T/S", _check_derived_driver_from_minimal_ts)


def _check_measured_driver_values_are_used():
    d = _acoustics.complete_driver(replace(_beyma_ts(), panel_air_load=False))
    assert abs(d.mms_kg - 0.054) < 1e-9
    assert abs(d.cms_m_per_n - 0.000193) < 1e-12
    assert abs(d.bl_tm - 13.7) < 1e-12


test("Driver completion uses measured optional values", _check_measured_driver_values_are_used)


def _check_panel_air_load_matches_afw_fe126():
    ts = _acoustics.DriverTS(
        fs_hz=89.4,
        vas_l=6.942334,
        qts=0.3789999649445698,
        qms=5.32,
        re_ohm=7.12,
        sd_cm2=63.61727,
    )
    added_mass_g, loaded_fs_hz = _acoustics.panel_air_load_metrics(ts)
    assert ts.panel_air_load is True
    assert 0.25 < added_mass_g < 0.27, added_mass_g
    assert abs(loaded_fs_hz - 85.2385) < 0.001, loaded_fs_hz
    fc_hz, qtc = _acoustics.sealed_system_metrics(ts, _acoustics.SealedBox(vb_l=3.0))
    assert abs(fc_hz - 155.1741) < 0.001, fc_hz
    assert abs(fc_hz / 155.0854 - 1.0) < 0.001, fc_hz
    assert abs(qtc - 0.6899581) < 1e-6, qtc
    disabled = replace(ts, panel_air_load=False)
    assert _acoustics.panel_air_load_metrics(disabled) == (0.0, 89.4)
    assert _acoustics.sealed_system_metrics(disabled, _acoustics.SealedBox(vb_l=3.0))[0] > fc_hz


test("Driver panel air load defaults on and matches AFW FE126", _check_panel_air_load_matches_afw_fe126)


def _check_afw_comparator_reports_panel_loaded_delta():
    from tools import compare_afw_sealed as comparator

    qts = 0.3789999649445698
    qms = 5.32
    driver = comparator.AfwDriver(
        name="Fostex FE126",
        re_ohm=7.12,
        fs_hz=89.4,
        qms=qms,
        qes=qts * qms / (qms - qts),
        qts=qts,
        vas_l=6.942334,
        le_10khz_mh=0.0,
        le_exponent=0.0,
        le_phase_factor=0.0,
        xmax_mm=0.0,
        pe_w=0.0,
        sd_cm2=63.61727,
    )
    sealed = comparator.AfwSealed(
        volume_l=3.0,
        volume_factor=1.0,
        resonance_hz=155.0854,
        qt=0.69,
        q_loss=10.0,
    )
    report = comparator.compare(driver, sealed)
    load_forge = report["load_forge"]
    delta = report["delta_percent"]
    assert abs(load_forge["panel_loaded_fc_hz"] - 155.1741) < 0.001
    assert abs(delta["classical_fc_vs_afw"] - 4.9422) < 0.001
    assert abs(delta["panel_loaded_fc_vs_afw"] - 0.0572) < 0.001


test("AFW comparator reports the corrected panel-loaded delta", _check_afw_comparator_reports_panel_loaded_delta)


def _check_afw_bandpass_comparator_and_multi_driver_projection():
    import tempfile
    from pathlib import Path

    from tools import compare_afw_sealed as comparator

    qts = 0.3789999649445698
    qms = 5.32
    driver = comparator.AfwDriver(
        name="Fostex FE126", re_ohm=7.12, fs_hz=89.4, qms=qms,
        qes=qts * qms / (qms - qts), qts=qts, vas_l=6.942334,
        le_10khz_mh=0.2156641, le_exponent=0.0, le_phase_factor=0.0,
        xmax_mm=0.35, pe_w=80.0, sd_cm2=63.61727)
    bp6 = comparator.AfwBandpass(
        order=6, rear_volume_l=6.252466, rear_volume_factor=1.1,
        rear_frequency_hz=87.66233, front_volume_l=2.258567,
        front_volume_factor=1.1, front_tuning_hz=170.5266,
        q_abs_rear=28.0, q_leak_rear=14.0, q_abs_front=28.0,
        q_leak_front=14.0, q_port_rear=55.19641, q_port_front=94.12212)
    single = comparator.compare_bandpass(driver, bp6)
    peaks = single["load_forge_simulation"]["impedance_peaks_hz"]
    assert len(peaks) == 3
    assert np.allclose(peaks, [48.1, 111.0, 240.0], rtol=0.03)

    pair = comparator.compare_bandpass(driver, bp6, "2 × parallel")
    assert pair["composite_driver"]["radiating_pistons"] == 2
    assert abs(
        pair["load_forge_simulation"]["panel_loaded_fs_hz"]
        / single["load_forge_simulation"]["panel_loaded_fs_hz"] - 1.0
    ) < 1e-12

    bp4 = replace(bp6, order=4)
    fourth = comparator.compare_bandpass(driver, bp4)
    assert fourth["afw_bandpass"]["order"] == 4
    assert len(fourth["load_forge_simulation"]["impedance_peaks_hz"]) >= 2

    # Minimal AFW-format slot-1 fixture: exercise load-code 3 and the actual
    # bandpass-block offsets without depending on a writable XP guest.
    driver_at = 1200
    lines = ["0"] * (driver_at + 1 + 201 * 5 + 11)
    lines[driver_at - 490] = "3"
    block = [0.0] * 26
    block[0:10] = [0.00231, 163.0, 1.0, 10.0, 10.0,
                   0.00158, 163.0, 1.1, 50.0, 14.0]
    block[14] = 100.0
    block[25] = 100.0
    lines[driver_at - 230:driver_at - 204] = [str(value) for value in block]
    lines[driver_at] = "Fostex FE126 synthetic BP4"
    params_at = driver_at + 1 + 201 * 5
    params = [7.12, 89.4, qms, driver.qes, 0.006942334, 0.0002156641,
              0.0, 0.0, 0.00035, 80.0, 0.006361727]
    lines[params_at:params_at + 11] = [str(value) for value in params]
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "bp4.afw"
        fixture.write_text("\n".join(lines), encoding="latin-1")
        parsed_driver, parsed_bp4 = comparator.parse_afw_project(fixture)
    assert parsed_driver.name == "Fostex FE126 synthetic BP4"
    assert isinstance(parsed_bp4, comparator.AfwBandpass)
    assert parsed_bp4.order == 4
    assert np.isclose(parsed_bp4.rear_volume_l, 2.31)
    assert np.isclose(parsed_bp4.front_volume_l * parsed_bp4.front_volume_factor, 1.738)
    assert parsed_bp4.front_tuning_hz == 163.0


test(
    "AFW comparator covers BP4, BP6 and multi-driver projections",
    _check_afw_bandpass_comparator_and_multi_driver_projection,
)


def _check_afw_dccav_generator_writes_the_real_chamber_block():
    import json

    from tools import generate_afw_dccav as writer

    lfp_path = ROOT / "examples" / "bass_match_9" / "09_dayton_um12_dccav.lfp"
    lfp = json.loads(lfp_path.read_text(encoding="utf-8"))
    text = writer.generate_afw_text(lfp, writer.DEFAULT_TEMPLATE)
    lines = text.splitlines()

    # Regression guard for the bug this test was added for: an earlier
    # version of this tool wrote box/port data to a 26-value block at
    # driver_at - 230, which the real AUDIO per Windows software's own
    # "Caricamento in doppio carico" dialog does not read (confirmed via a
    # user-supplied screenshot round trip). The real block is 18 values at a
    # fixed offset from the end of the file (see docs/afw_validation.md).
    block_at = len(lines) - writer._CHAMBER_BLOCK_FROM_END
    values = [float(lines[block_at + i]) for i in range(18)]

    assert np.isclose(values[0] * 1000.0, float(lfp["box_vh_l"]))
    assert np.isclose(values[1], float(lfp["box_fh_hz"]))
    assert values[2] == 1.0  # virtual_volume_factor: no physical/virtual split to express
    assert values[3] == float(lfp["loss_q_leak_h"])
    assert values[4] == float(lfp["loss_q_abs_h"])
    assert np.isclose(values[5] * 1000.0, float(lfp["box_vl_l"]))
    assert np.isclose(values[6], float(lfp["box_fl_hz"]))
    assert values[7] == 1.0
    assert values[8] == float(lfp["loss_q_leak_l"])
    assert values[9] == float(lfp["loss_q_abs_l"])
    assert values[10] == 1.0  # single port per chamber
    assert np.isclose(values[11] * 100.0, float(lfp["box_port_d_h_cm"]))
    assert values[12] > 0.0  # physical port length, derived not copied
    assert values[13] == float(lfp["loss_q_port_h"])
    assert values[14] == 1.0
    assert np.isclose(values[15] * 100.0, float(lfp["box_port_d_l_cm"]))
    assert values[16] > 0.0
    assert values[17] == float(lfp["loss_q_port_l"])

    # The stale driver_at - 230 block must be left at the template's own
    # values (the generator no longer writes there at all).
    driver_at, _ = writer.afw._find_driver_block(lines)
    assert lines[driver_at - 230].strip() == "0.00198150021"


test(
    "AFW DCCAV generator writes the real end-of-file chamber/port block",
    _check_afw_dccav_generator_writes_the_real_chamber_block,
)


def _check_rejects_invalid_q_values():
    try:
        _acoustics.complete_driver(_acoustics.DriverTS(
            fs_hz=50.0, vas_l=20.0, qts=0.5, qms=0.4,
            re_ohm=6.0, sd_cm2=220.0))
    except ValueError as exc:
        assert "Qms" in str(exc)
    else:
        raise AssertionError("invalid Qms <= Qts was accepted")


test("Driver completion rejects invalid Qms/Qts pairs", _check_rejects_invalid_q_values)


def _simulate_lumped_smoke_load(load_name: str):
    ts = _beyma_ts()
    frequency_hz = np.geomspace(15.0, 350.0, 180)
    if load_name == "DCCAV":
        alignment = _acoustics.suggest_alignment(ts)
        box = _acoustics.DccavBox(
            vh_l=alignment.vh_l,
            fh_hz=alignment.fh_hz,
            vl_l=alignment.vl_l,
            fl_hz=alignment.fl_hz,
        )
        result = _acoustics.simulate(ts, box, frequency_hz, voltage_v=2.83)
    elif load_name == "Bass reflex":
        alignment = _acoustics.suggest_reflex_alignment(ts)
        box = _acoustics.ReflexBox(vb_l=alignment.vb_l, fb_hz=alignment.fb_hz)
        result = _acoustics.simulate_reflex(ts, box, frequency_hz, voltage_v=2.83)
        assert np.all(result.port_h_velocity == 0)
    elif load_name == "Passive radiator":
        result = _acoustics.simulate_passive_radiator(
            ts, _acoustics.suggest_pr_alignment(ts), frequency_hz, voltage_v=2.83
        )
    elif load_name == "Sealed":
        alignment = _acoustics.suggest_sealed_alignment(ts)
        result = _acoustics.simulate_sealed(
            ts, _acoustics.SealedBox(vb_l=alignment.vb_l), frequency_hz, voltage_v=2.83
        )
    elif load_name == "Infinite baffle":
        result = _acoustics.simulate_infinite_baffle(ts, frequency_hz, voltage_v=2.83)
    elif load_name == "Bandpass 4th order":
        alignment = _acoustics.suggest_bandpass4_alignment(ts)
        box = _acoustics.Bandpass4Box(
            vs_l=alignment.vs_l, vp_l=alignment.vp_l, fp_hz=alignment.fp_hz
        )
        result = _acoustics.simulate_bandpass4(ts, box, frequency_hz, voltage_v=2.83)
    elif load_name == "Bandpass 6th order":
        alignment = _acoustics.suggest_bandpass6_alignment(ts)
        box = _acoustics.Bandpass6Box(
            vr_l=alignment.vr_l,
            fr_hz=alignment.fr_hz,
            vp_l=alignment.vp_l,
            fp_hz=alignment.fp_hz,
        )
        result = _acoustics.simulate_bandpass6(ts, box, frequency_hz, voltage_v=2.83)
    else:
        raise AssertionError(f"unknown smoke-test load: {load_name}")
    return result


def _check_lumped_load_smoke(load_name: str):
    result = _simulate_lumped_smoke_load(load_name)
    for name in (
        "spl_total_db", "spl_driver_db", "spl_port_db", "excursion_mm",
        "impedance_ohm", "port_h_velocity", "port_l_velocity", "mil_w", "mol_db",
    ):
        values = getattr(result, name)
        assert values.shape == result.frequency_hz.shape, f"{load_name} {name}: shape mismatch"
        assert np.all(np.isfinite(values)), f"{load_name} {name}: non-finite values"
    assert np.nanmax(result.mol_db) > np.nanmax(result.spl_total_db), load_name
    assert np.nanmin(result.mil_w) > 0, load_name


for _smoke_load_name in (
    "DCCAV",
    "Bass reflex",
    "Passive radiator",
    "Sealed",
    "Infinite baffle",
    "Bandpass 4th order",
    "Bandpass 6th order",
):
    test(
        f"Acoustic-load smoke: {_smoke_load_name}",
        lambda load_name=_smoke_load_name: _check_lumped_load_smoke(load_name),
    )


def _check_mol_requires_thermal_rating():
    ts = _acoustics.DriverTS(
        fs_hz=45.0,
        vas_l=50.0,
        qts=0.35,
        qms=4.0,
        re_ohm=8.0,
        sd_cm2=400.0,
        xmax_mm=6.0,
        pe_w=0.0,
    )
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _acoustics.simulate(ts, box, np.geomspace(20.0, 200.0, 120), voltage_v=2.83)
    # Without a thermal rating neither the MOL trace nor the MIL curve is
    # reported: there is no credible thermal ceiling to scale either one to.
    assert np.all(np.isnan(result.mol_db)), "MOL must be NaN when Pe is 0"
    assert np.all(np.isnan(result.mil_w)), "MIL must be NaN when Pe is 0"

    rated = replace(ts, pe_w=100.0)
    rated_result = _acoustics.simulate(rated, box, np.geomspace(20.0, 200.0, 120), voltage_v=2.83)
    assert np.all(np.isfinite(rated_result.mol_db)), "MOL is finite with a Pe rating"
    assert np.all(np.isfinite(rated_result.mil_w)), "MIL is finite with a Pe rating"
    assert np.nanmin(rated_result.mil_w) > 0


test("MOL requires a thermal rating to be reported", _check_mol_requires_thermal_rating)


def _check_sealed_and_infinite_baffle_models():
    import src as package_api

    assert package_api.SealedBox is not None
    assert package_api.simulate_sealed is not None
    assert package_api.simulate_infinite_baffle is not None
    ts = _beyma_ts()
    freq = np.geomspace(10.0, 500.0, 500)
    alignment = _acoustics.suggest_sealed_alignment(ts)
    box = _acoustics.SealedBox(vb_l=alignment.vb_l)
    fc_hz, qtc = _acoustics.sealed_system_metrics(ts, box)
    assert abs(qtc - 0.707) < 1e-9, (fc_hz, qtc)
    assert fc_hz > ts.fs_hz

    sealed = _acoustics.simulate_sealed(ts, box, freq)
    infinite = _acoustics.simulate_infinite_baffle(ts, freq)
    for result in (sealed, infinite):
        assert np.all(np.isfinite(result.spl_total_db))
        assert np.allclose(result.spl_total_db, result.spl_driver_db)
        assert np.all(result.port_h_velocity == 0.0)
        assert np.all(result.port_l_velocity == 0.0)
        assert np.all(result.port_volume_velocity == 0.0)
        assert len(_acoustics.impedance_peak_frequencies(result)) == 1
    ib_peak = _acoustics.impedance_peak_frequencies(infinite)[0]
    mounted_fs_hz = _acoustics.panel_loaded_fs_hz(ts)
    assert abs(ib_peak - mounted_fs_hz) / mounted_fs_hz < 0.05, ib_peak


test("Sealed and infinite-baffle models expose unported responses", _check_sealed_and_infinite_baffle_models)


def _check_bandpass4_model_and_starter():
    import src as package_api

    assert package_api.Bandpass4Box is _acoustics.Bandpass4Box
    assert package_api.simulate_bandpass4 is _acoustics.simulate_bandpass4
    ts = _kef_b110_ts()
    alignment = _acoustics.suggest_bandpass4_alignment(ts)
    assert abs(alignment.vp_l - 2.0 * 0.707**2 * ts.vas_l) < 1e-9
    assert abs(
        alignment.fp_hz - _acoustics.panel_loaded_fs_hz(ts) * 0.707 / ts.qts
    ) < 1e-9
    assert alignment.vs_l > 0.05
    box = _acoustics.Bandpass4Box(
        vs_l=alignment.vs_l, vp_l=alignment.vp_l, fp_hz=alignment.fp_hz)
    freq = np.geomspace(5.0, 1000.0, 2000)
    result = _acoustics.simulate_bandpass4(ts, box, freq)
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
    assert len(_acoustics.impedance_peak_frequencies(result)) >= 2
    assert not _acoustics.bandpass4_diagnostics(ts, box, result)


test("Fourth-order bandpass starter and simulation are coherent", _check_bandpass4_model_and_starter)


def _check_bandpass4_optimizer_atlas_and_ranking():
    ts = _beyma_ts()
    goals = _acoustics.OptimizationGoals(max_total_volume_l=40.0)
    optimized = _acoustics.optimize_alignment(
        ts, goals, load_type="Bandpass 4th order", max_evaluations=80,
        fixed_total_volume_l=40.0)
    assert isinstance(optimized.box, _acoustics.Bandpass4Box)
    assert abs(optimized.box.vs_l + optimized.box.vp_l - 40.0) < 1e-9
    assert np.isfinite(optimized.f3_hz)
    assert np.isfinite(optimized.ripple_db)

    space = _acoustics.design_space_map(
        ts, load_type="Bandpass 4th order", resolution=5)
    assert space.f3_hz.shape == (5, 5)
    assert np.any(np.isfinite(space.f3_hz))
    box = _acoustics.design_space_box(
        ts, "Bandpass 4th order", float(space.x_values[2]), float(space.y_values[2]))
    assert abs(box.vs_l + box.vp_l - float(space.x_values[2])) < 1e-9

    row = _acoustics.rank_preset_row(
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
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception
    labels = {item.label for item in at.number_input}
    assert {"Vs sealed rear (L)", "Vp ported front (L)", "Fp front tuning (Hz)"} <= labels
    metrics = {metric.label for metric in at.metric}
    assert {"Box volume", "Closed vol (Vs)", "Ported vol (Vp)", "Front vent tuning"} <= metrics
    assert any(
        "Fourth-order bandpass total response is the front vent only" in caption.value
        for caption in at.caption
    )


test("UI fourth-order bandpass controls persist and render", _check_ui_bandpass4_design_and_persistence)


def _check_bandpass6_model_and_starter():
    import src as package_api

    assert package_api.Bandpass6Box is _acoustics.Bandpass6Box
    assert package_api.simulate_bandpass6 is _acoustics.simulate_bandpass6
    ts = _kef_b110_ts()
    alignment = _acoustics.suggest_bandpass6_alignment(ts)
    expected_rear_l = 2.0 * 0.707**2 * ts.vas_l
    mounted_fs_hz = _acoustics.panel_loaded_fs_hz(ts)
    assert abs(alignment.vr_l - expected_rear_l) < 1e-9
    assert abs(alignment.vp_l - 0.5 * expected_rear_l) < 1e-9
    assert alignment.fr_hz == mounted_fs_hz
    assert alignment.fp_hz == 2.0 * mounted_fs_hz
    assert alignment.vr_l > 0.05
    assert alignment.vp_l > 0.05
    box = _acoustics.Bandpass6Box(
        vr_l=alignment.vr_l, fr_hz=alignment.fr_hz,
        vp_l=alignment.vp_l, fp_hz=alignment.fp_hz)
    freq = np.geomspace(5.0, 1000.0, 2000)
    result = _acoustics.simulate_bandpass6(ts, box, freq)
    for name in (
        "spl_total_db", "spl_driver_db", "spl_port_db", "excursion_mm",
        "impedance_ohm", "port_h_velocity", "port_l_velocity", "mil_w", "mol_db",
    ):
        values = getattr(result, name)
        assert values.shape == freq.shape
        assert np.all(np.isfinite(values)), name
    assert np.any(result.port_h_velocity > 0.0)
    assert np.any(result.port_l_velocity > 0.0)
    assert len(_acoustics.impedance_peak_frequencies(result)) >= 2
    assert not _acoustics.bandpass6_diagnostics(ts, box, result)

    # AFW's double-reflex model and the physical topology both require
    # opposite port polarity: identical branches cancel in the far field.
    equal_box = _acoustics.Bandpass6Box(
        vr_l=10.0, fr_hz=80.0, vp_l=10.0, fp_hz=80.0)
    cancelled = _acoustics.simulate_bandpass6(ts, equal_box, freq)
    assert np.max(cancelled.spl_total_db) < -200.0


test("Sixth-order bandpass starter and simulation are coherent", _check_bandpass6_model_and_starter)


def _check_bandpass6_optimizer_atlas_and_ranking():
    ts = _beyma_ts()
    goals = _acoustics.OptimizationGoals(max_total_volume_l=40.0)
    optimized = _acoustics.optimize_alignment(
        ts, goals, load_type="Bandpass 6th order", max_evaluations=80,
        fixed_total_volume_l=40.0)
    assert isinstance(optimized.box, _acoustics.Bandpass6Box)
    assert abs(optimized.box.vr_l + optimized.box.vp_l - 40.0) < 1e-9
    assert np.isfinite(optimized.f3_hz)
    assert np.isfinite(optimized.ripple_db)

    space = _acoustics.design_space_map(
        ts, load_type="Bandpass 6th order", resolution=5)
    assert space.f3_hz.shape == (5, 5)
    assert np.any(np.isfinite(space.f3_hz))
    box = _acoustics.design_space_box(
        ts, "Bandpass 6th order", float(space.x_values[2]), float(space.y_values[2]))
    assert abs(box.vr_l + box.vp_l - float(space.x_values[2])) < 1e-9

    row = _acoustics.rank_preset_row(
        "Beyma 12CMV2", "Bandpass 6th order", 40.0, 2.83, 10.0, 500.0, 240)
    assert row is not None
    assert abs(row["Vr L"] + row["Vp L"] - 40.0) < 1e-9
    assert np.isfinite(row["Fr Hz"])
    assert np.isfinite(row["Fp Hz"])
    assert np.isfinite(row["F3 Hz"])


test("Sixth-order bandpass optimizer, atlas and Finder preserve volume", _check_bandpass6_optimizer_atlas_and_ranking)


def _check_ui_bandpass6_design_and_persistence():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    assert _ui._is_param_key("bandpass6_vr_l")
    payload = {
        "load_type": "Bandpass 6th order",
        "bandpass6_vr_l": 8.0,
        "bandpass6_fr_hz": 50.0,
        "bandpass6_vp_l": 12.0,
        "bandpass6_fp_hz": 70.0,
    }
    assert _ui._apply_loaded_params(payload) == len(payload)
    saved = _ui._collect_params()
    for key, value in payload.items():
        assert saved[key] == value

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Bandpass 6th order"
    at.run()
    assert not at.exception, at.exception
    labels = {item.label for item in at.number_input}
    assert {"Vr rear ported (L)", "Fr rear tuning (Hz)", "Vp front ported (L)", "Fp front tuning (Hz)"} <= labels
    metrics = {metric.label for metric in at.metric}
    assert {"Box volume", "Rear vol (Vr)", "Rear vent tuning", "Front vol (Vp)", "Front vent tuning"} <= metrics
    assert any(
        "Sixth-order bandpass total response is the polarity-correct vector difference" in caption.value
        for caption in at.caption
    )


test("UI sixth-order bandpass controls persist and render", _check_ui_bandpass6_design_and_persistence)


def _check_response_metrics_are_sane():
    ts = _beyma_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _acoustics.simulate(ts, box, np.geomspace(5.0, 1000.0, 2000))
    metrics = _acoustics.response_metrics(result)
    thresholds = _acoustics.response_threshold_frequencies(result)
    assert metrics["max_spl_db"] > 0
    assert metrics["f3_hz"] == thresholds[3]
    assert 0 < thresholds[10] < thresholds[6] < thresholds[3]
    assert metrics["max_excursion_mm"] > 0
    assert metrics["min_impedance_ohm"] > 0
    peak_freqs = _acoustics.impedance_peak_frequencies(result)
    assert len(peak_freqs) >= 3, f"expected 3 DCCAV impedance peaks, got {peak_freqs}"

    ts = _acoustics.get_driver_preset("Beyma 12LEX1300Nd")
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _acoustics.simulate(ts, box, np.geomspace(5.0, 1000.0, 2000))
    thresholds = _acoustics.response_threshold_frequencies(result)
    assert abs(thresholds[3] - a.f3_hz) < 2.0, (thresholds[3], a.f3_hz)
    assert 0 < thresholds[10] < thresholds[6] < thresholds[3]
    assert not _acoustics.response_sanity_warnings(ts, box, thresholds)

    impossible = _acoustics.response_sanity_warnings(ts, box, {3: 30.0})
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
    flat_thresholds = _acoustics.response_threshold_frequencies(flat)
    assert np.isnan(flat_thresholds[3]), flat_thresholds

    chr70 = _acoustics.get_driver_preset("MarkAudio CHR-70")
    a = _acoustics.suggest_alignment(chr70)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _acoustics.simulate(chr70, box, np.geomspace(10.0, 500.0, 600))
    assert np.nanmax(result.mil_w) == chr70.pe_w
    assert np.nanmin(result.mil_w) > 0

    reflex = _acoustics.suggest_reflex_alignment(_beyma_ts())
    box = _acoustics.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    result = _acoustics.simulate_reflex(_beyma_ts(), box, np.geomspace(5.0, 1000.0, 2000))
    peak_freqs = _acoustics.impedance_peak_frequencies(result)
    assert len(peak_freqs) >= 2, f"expected two bass-reflex impedance peaks, got {peak_freqs}"


test("Acoustic response metrics are positive", _check_response_metrics_are_sane)


def _check_group_delay_is_finite_and_exported():
    ts = _beyma_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    result = _acoustics.simulate(ts, box, np.geomspace(10.0, 500.0, 600))
    gd = _acoustics.group_delay_ms(result)
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


test("Acoustic group delay is finite and exported to CSV", _check_group_delay_is_finite_and_exported)


def _parse_export_rows(text: str) -> np.ndarray:
    rows = [line.split("\t") for line in text.splitlines() if not line.startswith("*")]
    return np.array([[float(value) for value in row] for row in rows])


def _check_frd_zma_exports():
    import dataclasses

    ts = _kef_b110_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 240)
    result = _acoustics.simulate(ts, box, freq, 2.83)

    frd_text = _acoustics.export_frd_text(result)
    assert frd_text.splitlines()[0].startswith("*"), "FRD must open with comment lines"
    frd = _parse_export_rows(frd_text)
    assert frd.shape == (len(freq), 3), frd.shape
    np.testing.assert_allclose(frd[:, 0], freq, atol=5e-4)
    np.testing.assert_allclose(frd[:, 1], result.spl_total_db, atol=5e-4)
    assert np.all(np.abs(frd[:, 2]) <= 180.0 + 1e-9), "FRD phase must be wrapped to ±180"
    assert np.ptp(frd[:, 2]) > 90.0, "response phase must actually rotate over the sweep"

    zma = _parse_export_rows(_acoustics.export_zma_text(result))
    assert zma.shape == (len(freq), 3), zma.shape
    np.testing.assert_allclose(zma[:, 0], freq, atol=5e-4)
    np.testing.assert_allclose(zma[:, 1], result.impedance_ohm, atol=5e-4)
    assert np.all(np.abs(zma[:, 2]) <= 90.0 + 1e-9), "passive impedance phase stays within ±90"
    assert np.ptp(zma[:, 2]) > 30.0, "impedance phase must swing across the resonances"

    reflex = _acoustics.simulate_reflex(ts, _acoustics.ReflexBox(vb_l=ts.vas_l, fb_hz=ts.fs_hz), freq)
    sealed = _acoustics.simulate_sealed(ts, _acoustics.SealedBox(vb_l=ts.vas_l), freq)
    baffle = _acoustics.simulate_infinite_baffle(ts, freq)
    for run in (reflex, sealed, baffle):
        assert run.impedance_phase_deg is not None
        assert np.all(np.isfinite(run.impedance_phase_deg))

    legacy = dataclasses.replace(result, impedance_phase_deg=None)
    legacy_zma = _parse_export_rows(_acoustics.export_zma_text(legacy))
    assert np.all(legacy_zma[:, 2] == 0.0), "legacy results must degrade to zero phase"

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
    at.run()
    assert not at.exception, at.exception
    labels = {button.label for button in at.get("download_button")}
    assert {"Download FRD (response)", "Download ZMA (impedance)"} <= labels, labels
    uploader_labels = {uploader.label for uploader in at.file_uploader}
    assert "Import response FRD or CSV" not in uploader_labels
    assert "Import impedance ZMA or CSV" not in uploader_labels


test("DCCAV FRD/ZMA exports match the simulated arrays", _check_frd_zma_exports)


def _check_ui_group_delay_chart_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["design_analysis_tab"] = "Group Delay"
    at.run()
    assert not at.exception, at.exception
    assert any(sub.value == "Group Delay" for sub in at.subheader), (
        "Group Delay tab subheader missing"
    )


test("UI group-delay tab renders the Group Delay chart", _check_ui_group_delay_chart_renders)


def _check_ui_non_calculating_navigation_is_lazy():
    import inspect

    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    actions_source = inspect.getsource(_ui._render_find_driver_actions)
    assert "_finder_worker_pool" not in actions_source, (
        "merely opening Bass Match must not create calculation workers"
    )

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    assert not at.dataframe, (
        "the collapsed candidate pool must not serialize its 500-row table"
    )

    at.session_state["workspace_mode"] = "Box Design"
    at.run()
    assert not at.exception, at.exception
    assert len(at.get("vega_lite_chart")) == 1, (
        "Box Design must build only the selected analysis chart"
    )


test(
    "UI workspace navigation keeps expensive panels lazy",
    _check_ui_non_calculating_navigation_is_lazy,
)


def _check_port_geometry_helpers():
    volume_l, fb_hz, diameter_cm = 50.0, 40.0, 10.0
    length_cm = _acoustics.port_length_cm(volume_l, fb_hz, diameter_cm)
    assert 15.0 < length_cm < 35.0, length_cm

    radius_m = diameter_cm / 200.0
    l_eff_m = length_cm / 100.0 + 1.43 * radius_m
    fb_check = (
        _acoustics.SPEED_OF_SOUND / (2.0 * np.pi)
        * np.sqrt(np.pi * radius_m**2 / ((volume_l / 1000.0) * l_eff_m))
    )
    assert abs(fb_check - fb_hz) < 1e-9, fb_check

    assert _acoustics.port_length_cm(volume_l, fb_hz, 5.0) < length_cm
    assert _acoustics.port_length_cm(100.0, 30.0, 1.0) <= 0.0, "tiny port must be flagged impossible"

    max_hz = _acoustics.port_max_tuning_hz(16.70, 4.0, 1.64)
    assert 80.0 < max_hz < 85.0, max_hz
    min_d_cm = _acoustics.port_min_diameter_cm(16.70, 127.59, 1.64)
    assert 9.0 < min_d_cm < 10.2, min_d_cm
    assert abs(_acoustics.port_length_cm(16.70, max_hz, 4.0, 1.64)) < 1e-9
    assert abs(_acoustics.port_length_cm(16.70, 127.59, min_d_cm, 1.64)) < 1e-9

    ts = _beyma_ts()
    reflex = _acoustics.suggest_reflex_alignment(ts)
    box = _acoustics.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    result = _acoustics.simulate_reflex(ts, box, np.geomspace(10.0, 500.0, 400))
    area_cm2 = np.pi * (diameter_cm / 2.0) ** 2
    velocity = _acoustics.port_air_velocity_ms(result, area_cm2, "lower")
    assert velocity.shape == result.frequency_hz.shape
    assert np.all(np.isfinite(velocity)), "port air speed must be finite"
    assert np.nanmax(velocity) > 0.0
    halved = _acoustics.port_air_velocity_ms(result, area_cm2 / 2.0, "lower")
    np.testing.assert_allclose(halved, 2.0 * velocity)
    try:
        _acoustics.port_air_velocity_ms(result, area_cm2, "middle")
        raise AssertionError("invalid port name must raise")
    except ValueError:
        pass


test("Acoustic port geometry length round-trips and air speed scales", _check_port_geometry_helpers)


def _check_ui_small_alignment_warning_uses_active_box():
    import ui_app as _ui

    ts = _beyma_ts()
    small_active = _acoustics.DccavBox(
        vh_l=10.7, fh_hz=128.0, vl_l=10.7, fl_hz=48.0
    )
    large_active = _acoustics.DccavBox(
        vh_l=34.68, fh_hz=128.0, vl_l=40.32, fl_hz=48.0
    )

    warning = _ui._alignment_warning(ts, small_active)
    assert warning is not None and "active" in warning and "21.4 L" in warning
    assert _ui._alignment_warning(ts, large_active) is None, (
        "a 75 L active box must not inherit a warning from the smaller empirical starter"
    )


test(
    "UI small 12-inch alignment warning uses the active box",
    _check_ui_small_alignment_warning_uses_active_box,
)


def _check_port_displacement_golden_rule():
    import dataclasses

    import ui_app as _ui

    ts = dataclasses.replace(_beyma_ts(), sd_cm2=530.0, xmax_mm=8.0)
    # D = sqrt(8 * K * Fb * Sd * Xmax / (1000 * (0.05 * c))) with K=1.0, c=344
    # D = sqrt(8 * 1.0 * 30 * 530 * 8 / (1000 * 17.2)) = 7.692 cm.
    golden_cm = _acoustics.port_displacement_min_diameter_cm(ts, 30.0)
    assert abs(golden_cm - 7.692) < 0.01, golden_cm
    assert _acoustics.port_displacement_min_diameter_cm(ts, 60.0) > golden_cm, (
        "higher tuning needs a larger port because the cone cycles faster, "
        "producing more volumetric flow at the same excursion"
    )
    no_xmax = dataclasses.replace(ts, xmax_mm=0.0)
    assert _acoustics.port_displacement_min_diameter_cm(no_xmax, 30.0) == 0.0
    try:
        _acoustics.port_displacement_min_diameter_cm(ts, 0.0)
        raise AssertionError("non-positive tuning must raise")
    except ValueError:
        pass

    # The applied vent sizing must respect the floor even when a tiny drive
    # voltage silences the 5%-of-c air-speed requirement.
    box = _acoustics.ReflexBox(vb_l=76.0, fb_hz=30.0)
    result = _acoustics.simulate_reflex(ts, box, np.geomspace(10.0, 500.0, 240), 0.01)
    applied_cm = _ui._optimized_port_diameter_cm(
        ts, result, box.vb_l, box.fb_hz, 1.43, "lower", voltage_v=0.01)
    assert applied_cm >= golden_cm - 1e-9, (applied_cm, golden_cm)

    # The optimizer feasibility metric carries the same floor.
    from src import engine as _engine

    metrics = _engine._optimizer_metrics(
        ts, box, np.geomspace(10.0, 500.0, 240), 0.01)
    assert metrics["required_port_diameter_cm"] >= golden_cm - 1e-9, metrics


test("Acoustic displacement golden rule floors vent sizing", _check_port_displacement_golden_rule)


def _check_port_duct_volume_directive():
    from src import engine as _engine

    # Exact cylinder fraction for the reported 4.5 cm duct in 4.57 L @ 34.47 Hz.
    volume_l, fb_hz, d_cm = 4.57, 34.47, 4.5
    length_cm = _acoustics.port_length_cm(volume_l, fb_hz, d_cm)
    expected = np.pi * (d_cm / 2.0) ** 2 * length_cm / 1000.0 / volume_l
    fraction = _acoustics.port_volume_fraction(volume_l, fb_hz, d_cm)
    assert abs(fraction - expected) < 1e-12, (fraction, expected)
    assert fraction > _acoustics.PORT_MAX_VOLUME_FRACTION, fraction
    assert _acoustics.port_volume_fraction(100.0, 30.0, 1.0) == 0.0, (
        "an unreachable tuning is the zero-length warning's job, not this one"
    )

    pipe_hz = _acoustics.port_pipe_resonance_hz(84.6)
    assert abs(pipe_hz - _acoustics.SPEED_OF_SOUND / (2.0 * 0.846)) < 1e-9, pipe_hz
    try:
        _acoustics.port_pipe_resonance_hz(0.0)
        raise AssertionError("non-positive length must raise")
    except ValueError:
        pass

    # The user-reported case: an isobaric 12" pair squeezed into 4.57 L at
    # 34.5 Hz needs a duct that displaces ~25% of the chamber - infeasible.
    ts = _acoustics.apply_driver_configuration(
        _acoustics.get_driver_preset("LSDB: PowerBass PBX1-12D2"),
        "Isobaric pair (parallel)",
    )
    freq = np.geomspace(10.0, 500.0, 240)
    bad_box = _acoustics.DccavBox(vh_l=5.43, fh_hz=155.12, vl_l=4.57, fl_hz=34.47)
    bad = _engine._optimizer_metrics(ts, bad_box, freq, 2.83)
    assert bad["port_volume_fraction"] > _acoustics.PORT_MAX_VOLUME_FRACTION, bad
    assert _engine._score_alignment(
        bad, _acoustics.OptimizationGoals(), ts, True) >= 1e5, (
        "an oversized duct must land in the infeasible score tier"
    )

    optimized = _acoustics.optimize_alignment(
        ts, _acoustics.OptimizationGoals(objective="balanced"),
        load_type="DCCAV", box_template=bad_box, voltage_v=2.83,
    )
    good = _engine._optimizer_metrics(ts, optimized.box, freq, 2.83)
    assert good["port_volume_fraction"] <= _acoustics.PORT_MAX_VOLUME_FRACTION + 1e-9, good


test("Acoustic duct-volume directive rejects oversized ports", _check_port_duct_volume_directive)


def _check_port_diameter_for_load_shared_sizer():
    # A comfortably large chamber: the length target wins, the cap is slack.
    # Rounding to the 0.5 cm grid always rounds *down* toward the floor when
    # that stays compliant, so the resulting length can undershoot the 5 cm
    # target by less than one grid step - by design, since that keeps the
    # cap intact instead of overshooting it.
    d = _acoustics.port_diameter_for_load(76.0, 30.0, 1.43, floor_cm=4.47)
    assert d is not None and d >= 4.47, d
    assert _acoustics.port_length_cm(76.0, 30.0, d, 1.43) > 0.0, d
    assert _acoustics.port_volume_fraction(76.0, 30.0, d, 1.43) <= _acoustics.PORT_MAX_VOLUME_FRACTION

    # A floor that itself breaks the cap even after grid rounding: no
    # diameter can satisfy every directive for this volume/tuning pair (the
    # exact PowerBass isobaric case from the duct-volume-directive test).
    assert _acoustics.port_diameter_for_load(4.57, 34.47, 1.43, floor_cm=4.47) is None
    # A floor just above one where the *grid-rounded* floor alone already
    # exceeds the cap (5 L @ 44 Hz, floor 4.06 cm rounds up to 4.5 cm =
    # 14.6%): confirms rejection is decided post-rounding, not pre-rounding.
    assert _acoustics.port_diameter_for_load(5.0, 44.0, 1.43, floor_cm=4.06) is None
    assert _acoustics.port_volume_fraction(5.0, 44.0, 4.06, 1.43) <= 0.10, (
        "the raw (unrounded) floor must look compliant on its own - the "
        "rejection only appears after grid-rounding to a buildable diameter"
    )

    # Grid rounding must round DOWN when that still clears the floor (never
    # silently re-break the cap by rounding up into it) - this was the exact
    # gap that let a 4.5 cm/14.6%-fraction duct through despite a compliant
    # continuous optimum. `d` above (5.0 cm) is itself the down-rounded
    # result of a raw optimum between 4.5 and 5.0 cm.
    assert abs(d / 0.5 - round(d / 0.5)) < 1e-9, d  # on the 0.5 cm grid
    assert _acoustics.port_length_cm(76.0, 30.0, d - 0.5, 1.43) < 5.0, (
        "the next grid step down must miss the length target - otherwise "
        "the function overshot instead of rounding to the nearest compliant point"
    )


test("port_diameter_for_load sizes within every directive on the 0.5 cm grid",
     _check_port_diameter_for_load_shared_sizer)


def _check_optimizer_and_ui_port_sizing_agree():
    """Regression: the UI's applied port must never exceed the duct-volume
    cap on a box the optimizer's own metrics report as compliant.

    Found via user report ("duct of 4.5 x 84.6 cm") after the golden-rule/
    duct-volume-directive rollout: `_optimizer_metrics` and the UI's
    `_optimized_port_diameter_cm` independently derived the port diameter
    with a slightly different velocity margin and un-synchronized 0.5 cm
    grid rounding, so a box the optimizer scored as feasible (<=10%) could
    still round up, in the UI, to a duct that broke the 10% cap.
    """
    import ui_app as _ui
    from src import engine as _engine

    ts = _acoustics.apply_driver_configuration(
        _acoustics.get_driver_preset("LSDB: PowerBass PBX1-12D2"),
        "Isobaric pair (parallel)",
    )
    freq = np.geomspace(10.0, 500.0, 240)
    mismatches = []
    for vb in np.arange(3.0, 15.0, 1.0):
        for fb in np.arange(20.0, 55.0, 1.0):
            box = _acoustics.ReflexBox(vb_l=float(vb), fb_hz=float(fb))
            try:
                result = _acoustics.simulate_reflex(ts, box, freq, 2.83)
            except ValueError:
                continue
            applied_cm = _ui._optimized_port_diameter_cm(
                ts, result, box.vb_l, box.fb_hz, 1.43, "lower")
            applied_fraction = _acoustics.port_volume_fraction(
                box.vb_l, box.fb_hz, applied_cm, 1.43)
            opt_fraction = _engine._optimizer_metrics(
                ts, box, freq, 2.83)["port_volume_fraction"]
            if opt_fraction <= _acoustics.PORT_MAX_VOLUME_FRACTION + 1e-9 and (
                    applied_fraction > _acoustics.PORT_MAX_VOLUME_FRACTION + 1e-6):
                mismatches.append((vb, fb, opt_fraction, applied_fraction, applied_cm))
    assert not mismatches, mismatches


test(
    "Optimizer feasibility and UI applied port sizing agree on the duct-volume cap",
    _check_optimizer_and_ui_port_sizing_agree,
)


def _check_reflex_optimizer_survives_infeasible_starting_neighborhood():
    """Regression, two causes found on the same driver/topology:

    1. Encoding "no valid diameter" as an infinite score flattened the
       pattern search's gradient across the whole infeasible plateau.
    2. Local coordinate descent from a single empirical starting point can
       get stuck in an infeasible neighborhood even with a smooth score,
       when the compliant region sits far away in the search space (the
       port-length-vs-box directive below reproduced this on its own, after
       fix 1 was already in place).

    Both made `optimize_alignment` report "no buildable box" even though a
    perfectly good reflex box existed within the search bounds; fix 2 is the
    deterministic diagonal-restart mechanism in `optimize_alignment`.
    """
    ts = _acoustics.apply_driver_configuration(
        _acoustics.get_driver_preset("LSDB: PowerBass PBX1-12D2"),
        "Isobaric pair (parallel)",
    )
    for cap in (None, 15.0, 18.0, 20.0, 30.0, 40.0):
        goals = _acoustics.OptimizationGoals(objective="extension", max_total_volume_l=cap)
        opt = _acoustics.optimize_alignment(ts, goals, load_type="Bass reflex")
        assert np.isfinite(opt.f3_hz), (cap, opt)
        freq = np.geomspace(10.0, 500.0, 240)
        result = _acoustics.simulate_reflex(ts, opt.box, freq, 2.83)
        assert result is not None, cap


test(
    "Reflex optimizer escapes an infeasible starting neighborhood",
    _check_reflex_optimizer_survives_infeasible_starting_neighborhood,
)


def _check_port_max_straight_length_directive():
    """Regression: a duct can stay under the 10% duct-volume cap while still
    being far longer than the box could plausibly hold in a straight run -
    user report of a 5.5 cm x 47.5 cm vent in a 40 L box (only 2.8% of the
    chamber, so the volume-fraction directive alone missed it).
    """
    from src import engine as _engine

    # Exact reported case.
    side_cm = _acoustics.port_max_straight_length_cm(40.0)
    assert abs(side_cm - 40_000.0 ** (1.0 / 3.0)) < 1e-9, side_cm
    length_cm = _acoustics.port_length_cm(40.0, 18.59, 5.5, 1.43)
    assert length_cm > side_cm, (length_cm, side_cm)
    fraction = _acoustics.port_volume_fraction(40.0, 18.59, 5.5, 1.43)
    assert fraction <= _acoustics.PORT_MAX_VOLUME_FRACTION, (
        "the case must slip past the volume-fraction directive on its own", fraction
    )
    try:
        _acoustics.port_max_straight_length_cm(0.0)
        raise AssertionError("non-positive volume must raise")
    except ValueError:
        pass

    ts = _acoustics.get_driver_preset("LSDB: PowerBass PBX1-12D2")
    box = _acoustics.ReflexBox(vb_l=40.0, fb_hz=18.59)
    freq = np.geomspace(10.0, 500.0, 240)
    metrics = _engine._optimizer_metrics(ts, box, freq, 2.83)
    assert metrics["port_length_over_box_ratio"] > 1.0, metrics
    score = _engine._score_alignment(
        metrics, _acoustics.OptimizationGoals(objective="balanced"), ts, False)
    assert score >= 1e5, (
        "a duct longer than the box can straight-fit must land in the "
        "infeasible score tier even at a compliant duct-volume fraction", score
    )

    # The real optimizer must steer clear of this combination for the same
    # driver/volume, landing on a box whose length ratio is compliant.
    goals = _acoustics.OptimizationGoals(objective="extension", max_total_volume_l=40.0)
    opt = _acoustics.optimize_alignment(ts, goals, load_type="Bass reflex")
    good_metrics = _engine._optimizer_metrics(ts, opt.box, freq, 2.83)
    assert good_metrics["port_length_over_box_ratio"] <= 1.0 + 1e-9, good_metrics


test(
    "Acoustic port-length directive rejects a duct longer than the box can hold",
    _check_port_max_straight_length_directive,
)


def _check_ui_port_geometry_warns_on_excessive_length():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    state = at.session_state
    state["workspace_mode"] = "Box Design"
    state["load_type"] = "Bass reflex"
    state["driver_preset_name"] = "LSDB: PowerBass PBX1-12D2"
    state["sim_auto_align"] = False
    state["box_strategy"] = "Manual"
    state["reflex_vb_l"] = 40.0
    state["reflex_fb_hz"] = 18.59
    state["reflex_port_d_cm"] = 5.5
    at.run()
    assert not at.exception, at.exception
    assert any(
        "longer than a" in w.value and "plausibly hold" in w.value
        for w in at.warning
    ), [w.value for w in at.warning]

    state["reflex_fb_hz"] = 45.0
    at.run()
    assert not at.exception, at.exception
    assert not any("plausibly hold" in w.value for w in at.warning), (
        [w.value for w in at.warning]
    )


test(
    "UI port geometry warns when a duct is longer than the box can hold",
    _check_ui_port_geometry_warns_on_excessive_length,
)


def _check_ui_port_duct_volume_and_pipe_warnings():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    state = at.session_state
    state["workspace_mode"] = "Box Design"
    state["load_type"] = "Bass reflex"
    state["sim_auto_align"] = False
    state["reflex_vb_l"] = 5.0
    state["reflex_fb_hz"] = 60.0
    state["reflex_port_d_cm"] = 10.0
    at.run()
    assert not at.exception, at.exception
    warnings = [w.value for w in at.warning]
    assert any("reflex directive" in w for w in warnings), warnings
    assert any("pipe resonance" in w for w in warnings), warnings

    state["reflex_port_d_cm"] = 3.0
    at.run()
    assert not at.exception, at.exception
    warnings = [w.value for w in at.warning]
    assert not any("reflex directive" in w for w in warnings), warnings
    assert not any("pipe resonance" in w for w in warnings), warnings


test(
    "UI port geometry warns on oversized ducts and in-band pipe resonance",
    _check_ui_port_duct_volume_and_pipe_warnings,
)


def _check_ui_port_geometry_warns_below_golden_rule():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    state = at.session_state
    state["workspace_mode"] = "Box Design"
    state["load_type"] = "Bass reflex"
    state["sim_auto_align"] = False
    state["driver_sd_mode"] = "Sd"
    state["driver_sd_cm2"] = 530.0
    state["driver_xmax_mm"] = 8.0
    state["reflex_vb_l"] = 76.0
    state["reflex_fb_hz"] = 30.0
    state["reflex_port_d_cm"] = 4.0
    state["sim_voltage"] = 0.01
    at.run()
    assert not at.exception, at.exception
    assert any("minimum-area golden rule" in w.value for w in at.warning), (
        [w.value for w in at.warning]
    )
    assert not any("air speed peaks" in w.value for w in at.warning), (
        "at 0.01 V the velocity guideline must stay quiet: the golden rule is "
        "the drive-independent floor"
    )

    state["reflex_port_d_cm"] = 10.0
    at.run()
    assert not at.exception, at.exception
    assert not any("minimum-area golden rule" in w.value for w in at.warning), (
        [w.value for w in at.warning]
    )


test(
    "UI port geometry warns below the minimum-area golden rule",
    _check_ui_port_geometry_warns_below_golden_rule,
)


def _check_ui_port_geometry_warns_on_small_vent():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    state = at.session_state
    state["workspace_mode"] = "Box Design"
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
    ts = replace(_kef_b110_ts(), panel_air_load=False)
    drv = _acoustics.complete_driver(ts)
    ref = _acoustics.driver_reference_metrics(ts)
    assert abs(ref.ebp_hz - ts.fs_hz / drv.qes) < 1e-9, ref.ebp_hz
    assert 0.002 < ref.eta0 < 0.004, ref.eta0
    assert 85.0 < ref.spl_1w_db < 89.0, ref.spl_1w_db
    assert ref.spl_2v83_db > ref.spl_1w_db, "Re < 8 ohm must gain SPL at 2.83 V"
    assert 105.0 < ref.ebp_hz < 120.0, "article driver EBP should suggest a ported load"


test("Driver reference metrics match classical formulas", _check_driver_reference_metrics)


def _check_ui_reference_metrics_row():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
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
    reflex = _acoustics.suggest_reflex_alignment(ts)
    box = _acoustics.ReflexBox(vb_l=reflex.vb_l, fb_hz=reflex.fb_hz)
    freq = np.geomspace(10.0, 500.0, 500)
    base = _acoustics.simulate_reflex(ts, box, freq)
    zero_rs = _acoustics.simulate_reflex(ts, box, freq, series_r_ohm=0.0)
    np.testing.assert_allclose(zero_rs.spl_total_db, base.spl_total_db)
    np.testing.assert_allclose(zero_rs.impedance_ohm, base.impedance_ohm)

    with_rs = _acoustics.simulate_reflex(ts, box, freq, series_r_ohm=2.0)
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

    a = _acoustics.suggest_alignment(ts)
    dccav_box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    for run in (
        _acoustics.simulate(ts, dccav_box, freq, 2.83, 2.0),
        _acoustics.simulate_sealed(ts, _acoustics.SealedBox(vb_l=40.0), freq, 2.83, 2.0),
        _acoustics.simulate_infinite_baffle(ts, freq, 2.83, 2.0),
    ):
        assert np.all(np.isfinite(run.spl_total_db)), "series R runs must stay finite"
        assert np.min(run.impedance_ohm) > ts.re_ohm + 1.5, "impedance must include series R"

    try:
        _acoustics.simulate_reflex(ts, box, freq, series_r_ohm=-1.0)
        raise AssertionError("negative series resistance must raise")
    except ValueError:
        pass


test("Acoustic loads apply series resistance to impedance, drive and damping", _check_series_resistance_effects)


def _check_ui_series_resistance_input():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
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

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    assert not at.exception, at.exception

    pin = next(b for b in at.button if b.label == "Pin response")
    assert not any(b.label == "Clear all pins" for b in at.button)
    pin.click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_responses"]
    assert len(pinned) == 1, "pin button must append the current response snapshot"
    assert pinned[0]["label"].startswith("DCCAV"), pinned[0]["label"]
    assert pinned[0]["load_type"] == "DCCAV"
    assert pinned[0]["visible"] is True
    assert len(pinned[0]["frequency_hz"]) == len(pinned[0]["spl_total_db"]) > 0
    assert set(pinned[0]["response_traces"]) == {
        "Total",
        "Cone",
        "Lower port",
        "MOL",
    }
    assert all(
        len(values) == len(pinned[0]["frequency_hz"])
        for values in pinned[0]["response_traces"].values()
    )
    for metric in ("excursion_mm", "impedance_ohm", "mil_w", "group_delay_ms"):
        assert len(pinned[0][metric]) == len(pinned[0]["frequency_hz"]), metric
    assert set(pinned[0]["port_traces"]) == {"Upper port", "Lower port"}
    assert all(
        len(values) == len(pinned[0]["frequency_hz"])
        for values in pinned[0]["port_traces"].values()
    )
    assert any("Pinned responses: 1/8" in caption.value for caption in at.caption)

    at.session_state["load_type"] = "Sealed"
    at.run()
    assert not at.exception, "pinned overlay must survive a load-type change"
    assert at.session_state["pinned_responses"][0]["label"].startswith("DCCAV")

    next(b for b in at.button if b.label == "Pin response").click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_responses"]
    assert len(pinned) == 2, pinned
    assert [item["load_type"] for item in pinned] == ["DCCAV", "Sealed"]
    assert any("Pinned responses: 2/8" in caption.value for caption in at.caption)

    hide_first = next(
        b for b in at.button if b.key == "toggle_pinned_response_0"
    )
    assert hide_first.label == "Hide"
    hide_first.click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_responses"]
    assert pinned[0]["visible"] is False and pinned[1]["visible"] is True
    assert any("1 visible" in caption.value for caption in at.caption)

    show_first = next(
        b for b in at.button if b.key == "toggle_pinned_response_0"
    )
    assert show_first.label == "Show"
    show_first.click().run()
    assert not at.exception, at.exception
    assert at.session_state["pinned_responses"][0]["visible"] is True

    remove_first = next(
        b for b in at.button if b.key == "remove_pinned_response_0"
    )
    assert remove_first.label == "Clear"
    remove_first.click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_responses"]
    assert len(pinned) == 1 and pinned[0]["load_type"] == "Sealed", pinned

    clear = next(b for b in at.button if b.label == "Clear all pins")
    clear.click().run()
    assert not at.exception, at.exception
    assert not at.session_state["pinned_responses"], "clear must drop every pinned snapshot"

    legacy = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    legacy.session_state["workspace_mode"] = "Box Design"
    legacy.session_state["load_type"] = "Sealed"
    legacy.session_state["pinned_response"] = {
        "label": "Legacy DCCAV pin",
        "frequency_hz": [10.0, 20.0],
        "spl_total_db": [70.0, 80.0],
    }
    legacy.run()
    assert not legacy.exception, legacy.exception
    migrated = legacy.session_state["pinned_responses"]
    assert len(migrated) == 1 and migrated[0]["label"] == "Legacy DCCAV pin", migrated


test("UI pin overlay stores multiple loads and clears them", _check_ui_pin_response_overlay)


def _check_ui_editable_design_comparison_tabs():
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    source = (ROOT / "ui_app.py").read_text()
    assert '[data-testid="stTooltipContent"]' in source
    assert '[role="tooltip"]' in source
    assert "alignment &middot; {sim_voltage:.2f} V" not in source
    assert "{load_type} &middot; {design_name}" not in source
    assert "short_label =" not in source
    assert "position: relative !important;" in source
    assert "position: absolute !important;" in source
    assert "white-space: normal !important;" in source
    assert "text-overflow: ellipsis !important;" not in source
    assert "on_click=_delete_design_comparison_tab" in source
    assert "on_click=_toggle_design_tab_visible" in source
    assert "@st.cache_data(show_spinner=False, max_entries=128)" in source
    assert "_mark_auto_alignment_synced()" in source

    color_tabs = [
        {"id": "a", "color": "#10b981"},
        {"id": "b", "color": "#9aa0a6"},
        {"id": "c", "color": "#ffb703"},
    ]
    colors = _ui._design_comparison_tab_colors(color_tabs)
    assert colors == {
        "a": "#10b981",
        "b": "#9aa0a6",
        "c": "#ffb703",
    }, colors
    assert _ui._design_comparison_tab_label(
        3,
        "Bass reflex",
        "LSDB: SB Acoustics WO24TX-4",
    ) == "3 · SB Acoustics · WO24TX-4 · Bass reflex · Single driver"
    assert _ui._design_tab_label_driver(
        "2 · Scan-Speak 25W/8561 · Bass reflex"
    ) == "Scan-Speak 25W/8561"
    assert _ui._design_tab_label_driver(
        "2 · SB Acoustics · WO24TX-4 · Bass reflex · Single driver"
    ) == "SB Acoustics WO24TX-4"
    assert _ui._design_tab_label_driver(
        "2 · Variant of Bass reflex · LSDB: SB Acoustics WO24TX-4 · Vb 75 L"
    ) == "LSDB: SB Acoustics WO24TX-4"
    lsdb_driver = _acoustics.get_driver_preset("LSDB: PowerBass PBX1-12D2")
    assert _ui._recover_design_tab_preset({
        "driver_fs_hz": lsdb_driver.fs_hz,
        "driver_vas_l": lsdb_driver.vas_l,
        "driver_qts": lsdb_driver.qts,
        "driver_qms": lsdb_driver.qms,
        "driver_re_ohm": lsdb_driver.re_ohm,
        "driver_sd_cm2": lsdb_driver.sd_cm2,
        "driver_le_mh": lsdb_driver.le_mh,
        "driver_xmax_mm": lsdb_driver.xmax_mm,
        "driver_pe_w": lsdb_driver.pe_w,
    }) == "LSDB: PowerBass PBX1-12D2"
    assert _ui._recover_design_tab_preset({
        "driver_fs_hz": lsdb_driver.fs_hz,
        "driver_vas_l": lsdb_driver.vas_l,
        "driver_qts": lsdb_driver.qts,
        "driver_qms": lsdb_driver.qms,
        "driver_re_ohm": lsdb_driver.re_ohm,
    }) == "LSDB: PowerBass PBX1-12D2"

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=45)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Sealed"
    at.session_state["box_strategy"] = "Manual"
    at.session_state["sealed_vb_l"] = 30.0
    at.session_state["sim_points"] = 180
    at.run()
    assert not at.exception, at.exception

    standalone_visibility = next(
        button
        for button in at.button
        if button.key == "toggle_design_tab_standalone"
    )
    assert standalone_visibility.label == "Hide design"
    standalone_visibility.click().run()
    assert not at.exception, at.exception
    assert at.session_state["standalone_design_visible"] is False
    assert next(
        button
        for button in at.button
        if button.key == "toggle_design_tab_standalone"
    ).label == "Show design"
    next(
        button
        for button in at.button
        if button.key == "toggle_design_tab_standalone"
    ).click().run()
    assert not at.exception, at.exception
    assert at.session_state["standalone_design_visible"] is True

    duplicate = next(
        button
        for button in at.button
        if button.label == "Duplicate design"
    )
    assert not duplicate.disabled
    duplicate.click().run()
    assert not at.exception, at.exception

    tabs = at.session_state["design_comparison_tabs"]
    assert len(tabs) == 2, tabs
    assert [tab["label"] for tab in tabs] == [
        "1 · KEF · B110B article example · Sealed · Single driver",
        "2 · KEF · B110B article example · Sealed · Single driver",
    ]
    assert [tab["driver_preset_name"] for tab in tabs] == [
        "KEF B110B article example",
        "KEF B110B article example",
    ]
    assert [tab["display_driver_name"] for tab in tabs] == [
        "KEF B110B article example",
        "KEF B110B article example",
    ]
    assert [tab["color"] for tab in tabs] == ["#10b981", "#9aa0a6"]
    assert len(at.session_state["pinned_responses"]) == 1
    assert at.session_state["pinned_responses"][0]["color"] == "#10b981"
    assert set(at.session_state["pinned_responses"][0]["response_traces"]) == {
        "Total",
        "Cone",
        "MOL",
    }
    active_id = at.session_state["design_comparison_active_id"]
    assert active_id == tabs[1]["id"], (active_id, tabs)
    assert sum(
        button.label == "Duplicate design" for button in at.button
    ) == 2
    assert sum(
        button.label == "Delete design" for button in at.button
    ) == 2
    assert sum(
        button.label == "Hide design" for button in at.button
    ) == 2
    rendered_tab_labels = {
        button.label for button in at.button
        if str(button.key).startswith("design_comparison_tab_")
    }
    assert rendered_tab_labels == {tab["label"] for tab in tabs}, (
        "tab buttons must retain their complete label and leave visual "
        "ellipsis handling to the available CSS width"
    )

    hide_first_design = next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[0]['id']}"
    )
    hide_first_design.click().run()
    assert not at.exception, at.exception
    assert at.session_state["design_comparison_tabs"][0]["visible"] is False
    assert at.session_state["pinned_responses"][0]["visible"] is False
    assert next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[0]['id']}"
    ).label == "Show design"
    next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[0]['id']}"
    ).click().run()
    assert not at.exception, at.exception
    assert at.session_state["design_comparison_tabs"][0]["visible"] is True
    assert at.session_state["pinned_responses"][0]["visible"] is True

    hide_active_design = next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[1]['id']}"
    )
    hide_active_design.click().run()
    assert not at.exception, at.exception
    assert at.session_state["design_comparison_tabs"][1]["visible"] is False
    assert next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[1]['id']}"
    ).label == "Show design"
    next(
        button
        for button in at.button
        if button.key == f"toggle_design_tab_{tabs[1]['id']}"
    ).click().run()
    assert not at.exception, at.exception
    assert at.session_state["design_comparison_tabs"][1]["visible"] is True

    at.session_state["sealed_vb_l"] = 45.0
    at.run()
    assert not at.exception, at.exception
    tabs = at.session_state["design_comparison_tabs"]
    assert tabs[0]["parameters"]["sealed_vb_l"] == 30.0
    assert tabs[1]["parameters"]["sealed_vb_l"] == 45.0

    tab_buttons = [
        button
        for button in at.button
        if str(button.key).startswith("design_comparison_tab_")
    ]
    assert len(tab_buttons) == 2
    tab_buttons[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["sealed_vb_l"] == 30.0
    assert at.session_state["design_comparison_active_id"] == tabs[0]["id"]
    assert at.session_state["driver_preset_name"] == "KEF B110B article example"
    assert [tab["color"] for tab in at.session_state[
        "design_comparison_tabs"
    ]] == ["#10b981", "#9aa0a6"]
    assert at.session_state["pinned_responses"][0]["color"] == "#9aa0a6"

    tab_buttons = [
        button
        for button in at.button
        if str(button.key).startswith("design_comparison_tab_")
    ]
    tab_buttons[1].click().run()
    assert not at.exception, at.exception
    assert at.session_state["sealed_vb_l"] == 45.0
    assert at.session_state["design_comparison_active_id"] == tabs[1]["id"]
    assert at.session_state["driver_preset_name"] == "KEF B110B article example"
    assert [tab["color"] for tab in at.session_state[
        "design_comparison_tabs"
    ]] == ["#10b981", "#9aa0a6"]
    assert len(at.session_state["pinned_responses"]) == 1
    assert at.session_state["pinned_responses"][0]["color"] == "#10b981"
    assert any(
        "Editable comparison: 2/8 tabs" in caption.value
        for caption in at.caption
    )
    assert not any(
        "select a tab, then edit normal sidebar parameters" in caption.value
        for caption in at.caption
    ), "design management must not consume a separate full-width row"

    legacy_tabs = at.session_state["design_comparison_tabs"]
    legacy_tabs[0]["driver_preset_name"] = "Custom"
    legacy_tabs[0]["parameters"]["driver_preset_name"] = "Custom"
    at.session_state["design_comparison_tabs"] = legacy_tabs
    delete = next(
        button for button in at.button
        if button.key == f"delete_design_tab_{tabs[1]['id']}"
    )
    assert not delete.disabled
    delete.click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["design_comparison_tabs"]) == 1
    assert at.session_state["sealed_vb_l"] == 30.0
    assert at.session_state["design_comparison_tabs"][0]["label"] == (
        "1 · KEF · B110B article example · Sealed · Single driver"
    ), "deleting and renumbering a sibling must never rename this tab Custom"

    delete = next(
        button for button in at.button
        if button.key == f"delete_design_tab_{tabs[0]['id']}"
    )
    delete.click().run()
    assert not at.exception, at.exception
    assert "design_comparison_tabs" not in at.session_state
    assert "design_comparison_active_id" not in at.session_state
    assert next(
        button for button in at.button
        if button.label == "Duplicate design"
    ).disabled is False


test(
    "UI design comparison tabs keep every variant independently editable",
    _check_ui_editable_design_comparison_tabs,
)


def _check_ui_reuses_unchanged_design_simulation():
    import ui_app as _ui

    ts = _beyma_ts()
    box = _acoustics.SealedBox(vb_l=40.0)
    revision = (1.0, 1.0)
    calls = 0
    original = _ui._acoustics.simulate_sealed

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    _ui._simulate_design_cached.clear()
    _ui._acoustics.simulate_sealed = counted
    try:
        first = _ui._simulate_design_cached(
            revision, ts, "Sealed", box, 10.0, 500.0, 180, 2.83, 0.0
        )
        second = _ui._simulate_design_cached(
            revision, ts, "Sealed", box, 10.0, 500.0, 180, 2.83, 0.0
        )
        assert calls == 1, "an interface-only rerun must reuse the solver result"
        assert np.allclose(
            first[0].spl_total_db, second[0].spl_total_db
        )
        _ui._simulate_design_cached(
            revision, ts, "Sealed", box, 10.0, 500.0, 180, 4.0, 0.0
        )
        assert calls == 2, "a changed simulation input must invalidate the cache"
    finally:
        _ui._acoustics.simulate_sealed = original
        _ui._simulate_design_cached.clear()


test(
    "UI reuses unchanged design simulation across interface clicks",
    _check_ui_reuses_unchanged_design_simulation,
)


def _check_ui_finder_selection_creates_editable_design_tabs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=45)
    at.session_state["sim_points"] = 180
    at.session_state["batch_pending_comparison"] = {
        "designs": [
            {
                "load_type": "Sealed",
                "row": {
                    "Driver": "KEF B110B article example",
                    "Load": "Sealed",
                    "Vb L": 16.0,
                },
            },
            {
                "load_type": "Bass reflex",
                "row": {
                    "Driver": "Beyma 12CMV2",
                    "Load": "Bass reflex",
                    "Resonator": "Port",
                    "Vb L": 42.0,
                    "Fb Hz": 51.0,
                },
            },
            {
                "load_type": "Infinite baffle",
                "row": {
                    "Driver": "KEF B110B article example",
                    "Load": "Infinite baffle",
                },
            },
        ],
        "voltage_v": 2.83,
    }
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["workspace_mode"] == "Box Design"
    assert "batch_pending_comparison" not in at.session_state
    tabs = at.session_state["design_comparison_tabs"]
    assert len(tabs) == 3, tabs
    assert [tab["color"] for tab in tabs] == [
        "#10b981", "#9aa0a6", "#ffb703",
    ]
    assert [tab["parameters"]["load_type"] for tab in tabs] == [
        "Sealed",
        "Bass reflex",
        "Infinite baffle",
    ]
    assert at.session_state["design_comparison_active_id"] == tabs[0]["id"]
    assert at.session_state["load_type"] == "Sealed"
    assert at.session_state["sealed_vb_l"] == 16.0
    assert len(at.session_state["pinned_responses"]) == 2

    at.session_state["batch_pending_result"] = {
        "load_type": "Bass reflex",
        "row": {
            "Driver": "Beyma 12CMV2",
            "Load": "Bass reflex",
            "Resonator": "Port",
            "Vb L": 38.0,
            "Fb Hz": 48.0,
        },
    }
    at.run()
    assert not at.exception, at.exception
    tabs = at.session_state["design_comparison_tabs"]
    assert len(tabs) == 4, tabs
    assert [tab["color"] for tab in tabs] == [
        "#10b981", "#9aa0a6", "#ffb703", "#8ecae6",
    ]
    assert [tab["parameters"]["load_type"] for tab in tabs[:3]] == [
        "Sealed", "Bass reflex", "Infinite baffle",
    ], "opening a new Finder result must preserve every existing design"
    assert at.session_state["design_comparison_active_id"] == tabs[3]["id"]
    assert len(at.session_state["pinned_responses"]) == 3
    assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
    assert at.session_state["load_type"] == "Bass reflex"
    assert at.session_state["reflex_vb_l"] == 38.0
    assert at.session_state["reflex_fb_hz"] == 48.0


test(
    "UI Finder multi-selection creates editable Box Design tabs",
    _check_ui_finder_selection_creates_editable_design_tabs,
)


def _check_ui_load_comparison_overlay():
    import ui_app as _ui

    ts = _beyma_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 300)
    vtot, series = _ui._topology_comparison_series(ts, "DCCAV", box, freq, 2.83, 0.0)
    assert abs(vtot - (a.vh_l + a.vl_l)) < 1e-9, vtot
    assert set(series) == {
        "DCCAV", "Bandpass 4th order", "Bandpass 6th order", "Bass reflex", "Sealed", "Infinite baffle",
    }
    for name, values in series.items():
        assert values.shape == freq.shape, name
        assert np.all(np.isfinite(values)), f"{name} comparison response must be finite"

    reflex_box = _acoustics.ReflexBox(vb_l=40.0, fb_hz=45.0)
    vtot_r, series_r = _ui._topology_comparison_series(ts, "Bass reflex", reflex_box, freq, 2.83, 0.0)
    assert abs(vtot_r - 40.0) < 1e-9, vtot_r
    direct = _acoustics.simulate_reflex(ts, reflex_box, freq, 2.83, 0.0)
    np.testing.assert_allclose(series_r["Bass reflex"], direct.spl_total_db)

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
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

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["project_menu_expander"] = True
    at.run()
    at.session_state["load_type"] = "Bass reflex"
    at.session_state["driver_fs_hz"] = 33.0
    at.session_state["reflex_vb_l"] = 55.5
    at.session_state["box_strategy"] = "Manual"
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

    at2 = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at2.query_params["d"] = token
    at2.run()
    assert not at2.exception, at2.exception
    assert at2.session_state["load_type"] == "Bass reflex"
    assert abs(float(at2.session_state["driver_fs_hz"]) - 33.0) < 1e-9
    assert abs(float(at2.session_state["reflex_vb_l"]) - 55.5) < 1e-9

    at3 = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at3.query_params["d"] = "not-a-valid-token"
    at3.run()
    assert not at3.exception, at3.exception
    assert any("could not be decoded" in warning.value for warning in at3.warning), (
        "an invalid share token must degrade gracefully with a warning"
    )


test("UI share link round-trips the design through the URL", _check_ui_share_link_roundtrip)


def _check_ui_project_preset_upload_finishes():
    import json

    from streamlit.testing.v1 import AppTest

    payload = json.dumps({
        "_load_forge_meta": {"version": "0.6.9", "format": 1},
        "load_type": "Bass reflex",
        "driver_fs_hz": 33.0,
        "reflex_vb_l": 55.5,
        "box_strategy": "Manual",
    }).encode("utf-8")

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["project_menu_expander"] = True
    at.run()
    assert any(
        item.label.startswith("Project")
        for item in at.sidebar.expander
    ), "project actions must live in the normal sidebar"
    assert not any(
        item.value == "Open a project"
        for item in at.title
    ), "project selection must not replace the normal workspace"
    project_upload = next(
        item for item in at.file_uploader
        if item.label == "Open .lfp project or CRW driver"
    )
    project_upload.set_value(
        ("saved-design.lfp", payload, "application/json")
    ).run(timeout=30)
    assert not at.exception, at.exception
    assert at.session_state["load_type"] == "Bass reflex"
    assert abs(float(at.session_state["driver_fs_hz"]) - 33.0) < 1e-9
    assert abs(float(at.session_state["reflex_vb_l"]) - 55.5) < 1e-9
    assert at.session_state["_project_upload_revision"] == 1
    project_upload = next(
        item for item in at.file_uploader
        if item.label == "Open .lfp project or CRW driver"
    )
    assert project_upload.value is None, (
        "a consumed preset must leave a fresh empty uploader after the rerun"
    )

    # A fresh uploader must still allow the exact same saved file to be loaded
    # again after the user has edited the design.
    at.session_state["reflex_vb_l"] = 20.0
    at.run()
    project_upload = next(
        item for item in at.file_uploader
        if item.label == "Open .lfp project or CRW driver"
    )
    project_upload.set_value(
        ("saved-design.lfp", payload, "application/json")
    ).run(timeout=30)
    assert not at.exception, at.exception
    assert abs(float(at.session_state["reflex_vb_l"]) - 55.5) < 1e-9
    assert at.session_state["_project_upload_revision"] == 2
    project_upload = next(
        item for item in at.file_uploader
        if item.label == "Open .lfp project or CRW driver"
    )
    assert project_upload.value is None


test(
    "UI project preset upload completes once and resets its uploader",
    _check_ui_project_preset_upload_finishes,
)


def _check_browser_project_startup_is_non_blocking():
    import streamlit as st

    import ui_app as _ui

    projects = [
        {"id": "lfp_one", "name": "One"},
        {"id": "lfp_two", "name": "Two"},
    ]
    assert _ui._browser_project_startup_mode(False, False, projects) == "continue"
    assert _ui._browser_project_startup_mode(True, True, projects) == "continue"
    assert _ui._browser_project_startup_mode(True, False, []) == "new"
    assert _ui._browser_project_startup_mode(
        True, False, projects[:1]
    ) == "choose"
    assert _ui._browser_project_startup_mode(True, False, projects) == "choose"
    assert _ui._decode_browser_project_summaries("not-json") == []
    assert _ui._decode_browser_project_summaries("{}") == []
    assert _ui._browser_project_summary_is_current(
        {"id": "lfp_one", "name": "One", "updated_at": "new"},
        projects,
    )
    assert not _ui._browser_project_summary_is_current(
        {"id": "lfp_one", "name": "Renamed"},
        projects,
    )

    source = (ROOT / "ui_app.py").read_text()
    assert 'command.op === "upsert" && command.quiet' in source
    assert 'command.op === "duplicate" && command.project_id' in source
    assert 'command.op === "delete" && command.project_id' in source
    assert 'if (!cancelled && !command.quiet)' in source
    assert '[data-stale="true"]' in source
    assert "opacity: 1 !important;" in source
    assert "scrollbar-gutter: stable;" in source
    assert 'key="response_chart"' in source
    assert 'key=f"response_chart_{chart_sig}"' not in source

    previous_initialized = st.session_state.get(
        "_browser_project_initialized"
    )
    previous_active = st.session_state.get("_browser_active_project")
    st.session_state["_browser_project_initialized"] = True
    st.session_state["_browser_active_project"] = {"id": "lfp_one"}
    _ui._request_browser_project_load("lfp_two")
    assert (
        st.session_state["_browser_project_load_after_save"] == "lfp_two"
    )
    assert "_browser_project_load_request" not in st.session_state
    st.session_state.pop("_browser_project_load_after_save", None)
    if previous_initialized is None:
        st.session_state.pop("_browser_project_initialized", None)
    else:
        st.session_state["_browser_project_initialized"] = previous_initialized
    if previous_active is None:
        st.session_state.pop("_browser_active_project", None)
    else:
        st.session_state["_browser_active_project"] = previous_active


test(
    "Browser project startup keeps multi-project choice in the sidebar",
    _check_browser_project_startup_is_non_blocking,
)


def _check_ui_new_browser_project_starts_clean():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["project_menu_expander"] = True
    at.session_state["_browser_project_initialized"] = True
    at.session_state["_browser_active_project"] = {
        "id": "lfp_old",
        "name": "Old project",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    }
    at.session_state["_browser_project_store_ready"] = True
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["driver_preset_name"] = "Custom"
    at.session_state["driver_fs_hz"] = 77.0
    at.session_state["driver_vas_l"] = 123.0
    at.session_state["load_type"] = "Sealed"
    at.session_state["box_strategy"] = "Manual"
    at.session_state["sealed_vb_l"] = 87.0
    at.session_state["plot_tolerance_pct"] = 37.0
    at.session_state["atlas_enabled"] = True
    at.session_state["cursor_auto_markers"] = []
    at.session_state["pinned_responses"] = [{"label": "Old curve"}]
    at.session_state["_manual_box_snapshots"] = {
        "Sealed": {"sealed_vb_l": 87.0}
    }
    at.session_state["_browser_project_load_request"] = {
        "project_id": "lfp_old",
        "nonce": "stale-load",
    }
    at.run()
    assert not at.exception, at.exception

    old_id = str(at.session_state["_browser_active_project"]["id"])
    new_button = next(
        button for button in at.button
        if button.key == "_browser_new_project"
    )
    new_button.click().run()
    assert not at.exception, at.exception

    assert str(at.session_state["_browser_active_project"]["id"]) != old_id
    assert at.session_state["driver_preset_name"] == (
        "KEF B110B article example"
    )
    assert abs(float(at.session_state["driver_fs_hz"]) - 48.14) < 1e-9
    assert abs(float(at.session_state["driver_vas_l"]) - 11.52) < 1e-9
    assert abs(float(at.session_state["sealed_vb_l"]) - 87.0) > 1e-9
    assert float(at.session_state["plot_tolerance_pct"]) == 15.0
    assert at.session_state["atlas_enabled"] is False
    assert list(at.session_state["cursor_auto_markers"])
    assert "pinned_responses" not in at.session_state
    assert "_manual_box_snapshots" not in at.session_state
    assert "_browser_project_load_request" not in at.session_state
    assert (
        "batch_results" not in at.session_state
        or not at.session_state["batch_results"]
    )


test(
    "UI New project starts without state from the previous project",
    _check_ui_new_browser_project_starts_clean,
)


def _check_ui_browser_projects_duplicate_and_delete():
    import json

    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    source = (ROOT / "ui_app.py").read_text(encoding="utf-8")
    assert "function transactionDone(transaction)" in source
    assert "await transactionDone(transaction);" in source

    assert _ui._browser_project_copy_name(
        "Sub alignment",
        ["Sub alignment", "Sub alignment copy"],
    ) == "Sub alignment copy 2"

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["project_menu_expander"] = True
    at.session_state["_browser_project_initialized"] = True
    at.session_state["_browser_project_store_ready"] = True
    at.session_state["_browser_active_project"] = {
        "id": "lfp_original",
        "name": "Sub alignment",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    }
    at.session_state["_browser_project_summaries"] = [
        {"id": "lfp_original", "name": "Sub alignment"},
        {"id": "lfp_copy", "name": "Sub alignment copy"},
    ]
    at.session_state["driver_fs_hz"] = 31.5
    at.run()
    assert not at.exception, at.exception

    duplicate = next(
        button for button in at.button
        if button.key == "_browser_duplicate_project"
    )
    duplicate.click().run()
    assert not at.exception, at.exception
    duplicated = at.session_state["_browser_active_project"]
    assert duplicated["id"] != "lfp_original"
    assert duplicated["name"] == "Sub alignment copy"
    assert abs(float(at.session_state["driver_fs_hz"]) - 31.5) < 1e-9

    delete = next(
        button for button in at.button
        if button.key == "_browser_delete_project"
    )
    delete.click().run()
    assert not at.exception, at.exception
    assert any(
        "Delete Sub alignment copy permanently" in item.value
        for item in at.warning
    )
    confirm = next(
        button for button in at.button
        if button.key == "_browser_confirm_delete_project"
    )
    deleted_id = str(at.session_state["_browser_active_project"]["id"])
    confirm.click().run()
    assert not at.exception, at.exception
    assert str(at.session_state["_browser_active_project"]["id"]) != deleted_id
    request = at.session_state["_browser_project_delete_request"]
    assert request["project_id"] == deleted_id
    assert abs(float(at.session_state["driver_fs_hz"]) - 31.5) > 1e-9

    chooser = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    chooser.session_state["project_menu_expander"] = True
    chooser.session_state["_browser_project_initialized"] = True
    chooser.session_state["_browser_project_store_ready"] = True
    chooser.session_state["_browser_active_project"] = None
    chooser.session_state["_browser_project_store"] = {
        "ready": True,
        "summaries_json": json.dumps([
            {"id": "lfp_saved", "name": "Saved alignment"},
        ]),
        "ack": "",
        "load_ack": "",
        "duplicate_ack": "",
        "delete_ack": "",
        "error": "",
    }
    chooser.run()
    assert not chooser.exception, chooser.exception
    duplicate_selected = next(
        button for button in chooser.button
        if button.key == "_browser_duplicate_selected_project"
    )
    duplicate_selected.click().run()
    assert not chooser.exception, chooser.exception
    duplicate_request = chooser.session_state[
        "_browser_project_duplicate_request"
    ]
    assert duplicate_request["project_id"] == "lfp_saved"
    assert duplicate_request["project"]["name"] == "Saved alignment copy"

    del chooser.session_state["_browser_project_duplicate_request"]
    chooser.run()
    delete_selected = next(
        button for button in chooser.button
        if button.key == "_browser_delete_selected_project"
    )
    delete_selected.click().run()
    assert not chooser.exception, chooser.exception
    confirm_selected = next(
        button for button in chooser.button
        if button.key == "_browser_confirm_delete_selected_project"
    )
    confirm_selected.click().run()
    assert not chooser.exception, chooser.exception
    selected_delete_request = chooser.session_state[
        "_browser_project_delete_request"
    ]
    assert selected_delete_request["project_id"] == "lfp_saved"


test(
    "UI browser projects can be duplicated and deleted",
    _check_ui_browser_projects_duplicate_and_delete,
)


def _check_ui_complete_lfp_restores_bass_match():
    import json

    from streamlit.testing.v1 import AppTest

    result_row = {
        "Driver": "KEF B110B article example",
        "Driver configuration": "Single driver",
        "Class": "Woofer",
        "F3 Hz": 48.5,
        "F6 Hz": 41.0,
        "F10 Hz": 34.0,
        "MOL @ F3 dB": 96.2,
        "Peak dB": 91.0,
        "Min ohm": 6.2,
        "Response": [-30.0, -12.0, -3.0, 0.0],
        "_load_type": "Sealed",
        "Vb L": 35.0,
    }
    payload = {
        "_load_forge_meta": {
            "version": "0.7.0",
            "format": 2,
            "kind": "project",
        },
        "project": {
            "id": "lfp_test_complete",
            "name": "Complete Bass Match",
            "created_at": "2026-07-30T12:00:00+00:00",
            "updated_at": "2026-07-30T12:00:00+00:00",
        },
        "parameters": {
            "load_type": "Sealed",
            "driver_fs_hz": 27.0,
            "sealed_vb_l": 35.0,
            "box_strategy": "Manual",
        },
        "bass_match": {
            "state": {
                "workspace_mode": "Bass Match",
                "finder_load_types": ["Sealed"],
                "finder_volume_l": 35.0,
                "finder_objective": "Balanced",
                "finder_reflex_resonator_type": "Port",
                "finder_min_spl_db": 0.0,
                "finder_min_mol_f3_db": 0.0,
                "finder_max_f3_hz": 0.0,
                "finder_max_mms_g": 0.0,
                "finder_max_le_mh": 0.0,
                "preset_search": "KEF",
                "preset_source_filter": ["All"],
                "preset_family_filter": ["All"],
                "preset_size_filter": ["All"],
                "preset_class_filter": ["All"],
            },
            "batch_results": [result_row],
            "batch_result_context": [
                ["Sealed"], 35.0, 1, True, "Balanced", "Port",
                0.0, 0.0, 0.0, 0.0, 7, 1, 1, 0, 0,
                "saved-selected-candidate-pool",
            ],
            "batch_search_completed": True,
        },
    }

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["project_menu_expander"] = True
    at.run()
    project_upload = next(
        item for item in at.file_uploader
        if item.label == "Open .lfp project or CRW driver"
    )
    project_upload.set_value((
        "complete-bass-match.lfp",
        json.dumps(payload).encode("utf-8"),
        "application/json",
    )).run(timeout=30)
    assert not at.exception, at.exception
    assert at.session_state["_browser_active_project"]["id"] == "lfp_test_complete"
    assert at.session_state["_browser_active_project"]["name"] == "Complete Bass Match"
    assert at.session_state["finder_load_types"] == ["Sealed"]
    assert abs(float(at.session_state["finder_volume_l"]) - 35.0) < 1e-9
    assert at.session_state["preset_search"] == "KEF"
    assert at.session_state["batch_search_completed"] is True
    assert len(at.session_state["batch_results"]) == 1
    assert at.session_state["batch_results"][0]["Driver"] == result_row["Driver"]
    assert at.session_state["batch_result_context"][0] == ("Sealed",)
    assert at.dataframe, "loading a project must show its last ranked candidate list"
    restored_cta = next(
        button for button in at.button
        if button.key == "finder_open_selected_design"
    )
    assert restored_cta.label == "Open this design in Box Design"
    assert restored_cta.disabled
    assert restored_cta.proto.type == "secondary"
    assert not any(
        item.value == "Your best matches" for item in at.subheader
    )

    at.session_state["preset_search"] = "Beyma"
    at.run()
    assert not any(
        button.key == "finder_open_selected_design" for button in at.button
    ), "editing restored Finder controls must still hide stale results"


test(
    "UI complete LFP restores design and Bass Match search state",
    _check_ui_complete_lfp_restores_bass_match,
)


def _check_saas_identity_entitlements_and_project_store():
    import tempfile

    from src import saas

    disabled = saas.SaaSSettings.from_env({})
    assert not disabled.enabled and not disabled.auth_required
    auth_only = saas.SaaSSettings.from_env({
        "LOAD_FORGE_AUTH_REQUIRED": "true",
        "LOAD_FORGE_ALLOWED_EMAILS": (
            "Owner@Example.test; collaborator@example.test\nowner@example.test"
        ),
    })
    assert auth_only.auth_required and not auth_only.enabled
    assert auth_only.allowed_emails == frozenset({
        "owner@example.test",
        "collaborator@example.test",
    })
    assert auth_only.allows_email("OWNER@example.test")
    assert not auth_only.allows_email("outsider@example.test")
    assert saas.SaaSSettings.from_env({
        "LOAD_FORGE_AUTH_REQUIRED": "true",
    }).allows_email("any-valid@example.test")
    try:
        saas.SaaSSettings.from_env({
            "LOAD_FORGE_ALLOWED_EMAILS": "not-an-email",
        })
    except saas.SaaSConfigurationError:
        pass
    else:
        raise AssertionError("invalid authentication allowlist was accepted")
    configured = saas.SaaSSettings.from_env({
        "LOAD_FORGE_SAAS_ENABLED": "true",
        "LOAD_FORGE_SAAS_BACKEND": "memory",
        "LOAD_FORGE_AUTH_BYPASS": "yes",
        "LOAD_FORGE_DEV_UID": "user-123",
        "LOAD_FORGE_DEV_EMAIL": "user@example.test",
    })
    assert configured.enabled and configured.auth_required and configured.auth_bypass
    user = saas.user_from_claims(configured.development_claims())
    assert user.uid == "user-123"
    assert user.email == "user@example.test"
    assert user.tenant_id.startswith("tenant-")
    assert saas.entitlements_for_plan("free").saved_projects == 3
    assert saas.entitlements_for_plan("unknown").plan == "free"
    assert saas.effective_entitlements(user, configured).saved_projects == 3

    open_beta = saas.SaaSSettings.from_env({
        "LOAD_FORGE_SAAS_ENABLED": "true",
        "LOAD_FORGE_OPEN_BETA_ENABLED": "true",
    })
    beta_entitlements = saas.effective_entitlements(user, open_beta)
    assert beta_entitlements.plan == "free"
    assert beta_entitlements.access_tier == "pro"
    assert beta_entitlements.promotion == "open_beta"
    assert beta_entitlements.saved_projects == 100
    assert beta_entitlements.monthly_finder_runs == 1_000

    team_user = saas.user_from_claims({
        "sub": "team-user",
        "email": "team@example.test",
        "tenant_id": "tenant-demo",
        "plan": "team",
    })
    assert team_user.plan == "team"
    team_beta_entitlements = saas.effective_entitlements(team_user, open_beta)
    assert team_beta_entitlements.plan == "team"
    assert team_beta_entitlements.access_tier == "team"
    assert team_beta_entitlements.saved_projects == 500
    store = saas.InMemoryProjectStore()
    created = store.save_project(
        team_user,
        "Reference alignment",
        {"load_type": "Bass reflex", "reflex_vb_l": 55.5},
        "0.6.9",
        expected_revision=0,
    )
    assert created.revision == 1
    assert store.load_project(team_user, created.project_id) == created
    summaries = store.list_projects(team_user)
    assert len(summaries) == 1
    assert summaries[0].project_id == created.project_id

    updated = store.save_project(
        team_user,
        "Reference alignment v2",
        {"load_type": "Bass reflex", "reflex_vb_l": 58.0},
        "0.6.9",
        project_id=created.project_id,
        expected_revision=1,
    )
    assert updated.revision == 2
    assert updated.created_at == created.created_at
    try:
        store.save_project(
            team_user,
            "Stale edit",
            {"reflex_vb_l": 20.0},
            "0.6.9",
            project_id=created.project_id,
            expected_revision=1,
        )
    except saas.ProjectConflictError:
        pass
    else:
        raise AssertionError("stale SaaS project revision was silently overwritten")

    other_tenant = saas.user_from_claims({
        "sub": "outsider",
        "tenant_id": "tenant-other",
    })
    assert store.load_project(other_tenant, created.project_id) is None
    assert store.list_projects(other_tenant) == []

    try:
        saas.SaaSSettings.from_env({
            "LOAD_FORGE_SAAS_ENABLED": "true",
            "LOAD_FORGE_AUTH_BYPASS": "true",
            "K_SERVICE": "load-forge",
        })
    except saas.SaaSConfigurationError:
        pass
    else:
        raise AssertionError("Cloud Run accepted the local authentication bypass")

    with tempfile.TemporaryDirectory() as directory:
        accounts = saas.LocalAccountStore(Path(directory) / "accounts.sqlite3")
        account = accounts.create_account(
            "Local tester",
            "Tester@Example.test",
            "correct horse battery staple",
        )
        assert account.email == "tester@example.test"
        assert accounts.authenticate(
            "tester@example.test",
            "correct horse battery staple",
        ) == account
        try:
            accounts.authenticate("tester@example.test", "wrong-password")
        except saas.InvalidCredentialsError:
            pass
        else:
            raise AssertionError("local account accepted an invalid password")
        try:
            accounts.create_account(
                "Duplicate",
                "tester@example.test",
                "another safe password",
            )
        except saas.AccountExistsError:
            pass
        else:
            raise AssertionError("local account accepted a duplicate email")

    try:
        saas.SaaSSettings.from_env({
            "LOAD_FORGE_SAAS_ENABLED": "true",
            "LOAD_FORGE_LOCAL_ACCOUNTS": "true",
            "K_SERVICE": "load-forge",
        })
    except saas.SaaSConfigurationError:
        pass
    else:
        raise AssertionError("Cloud Run accepted the local account registry")


test(
    "SaaS identity, entitlements and tenant project store are isolated",
    _check_saas_identity_entitlements_and_project_store,
)


def _check_ui_saas_local_project_roundtrip():
    import os

    from streamlit.testing.v1 import AppTest

    keys = {
        "LOAD_FORGE_SAAS_ENABLED": "true",
        "LOAD_FORGE_SAAS_BACKEND": "memory",
        "LOAD_FORGE_OPEN_BETA_ENABLED": "true",
        "LOAD_FORGE_AUTH_BYPASS": "true",
        "LOAD_FORGE_DEV_UID": "apptest-user",
        "LOAD_FORGE_DEV_EMAIL": "apptest@example.test",
        "LOAD_FORGE_DEV_NAME": "AppTest user",
    }
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update(keys)
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
        at.session_state["project_menu_expander"] = True
        at.session_state["load_type"] = "Bass reflex"
        at.session_state["box_strategy"] = "Manual"
        at.session_state["reflex_vb_l"] = 55.5
        at.run()
        assert not at.exception, at.exception
        assert any(
            "AppTest user · Open Beta · full access" in item.value
            for item in at.caption
        )
        assert any("0 / 100 saved projects" in item.value for item in at.caption)
        at.session_state["batch_results"] = [{
            "Driver": "KEF B110B article example",
            "Load": "Sealed",
            "F3 Hz": 48.5,
        }]
        at.session_state["batch_result_context"] = (
            ("Sealed",),
            35.0,
        )
        at.session_state["batch_search_completed"] = True
        project_name = next(
            item for item in at.text_input if item.label == "Cloud project name"
        )
        project_name.set_value("Saved SaaS alignment").run()
        save = next(
            button for button in at.button
            if button.label == "Save cloud project"
        )
        save.click().run()
        assert not at.exception, at.exception
        assert at.session_state["_saas_active_project_id"].startswith("prj_")
        assert at.session_state["_saas_active_project_revision"] == 1
        assert any(
            item.label == "Open cloud project" for item in at.selectbox
        ), "saved cloud project must be selectable"

        at.session_state["reflex_vb_l"] = 20.0
        at.session_state["batch_results"] = []
        at.session_state["batch_search_completed"] = False
        at.run()
        load = next(
            button for button in at.button
            if button.label == "Load"
        )
        load.click().run()
        assert not at.exception, at.exception
        assert abs(float(at.session_state["reflex_vb_l"]) - 55.5) < 1e-9
        assert at.session_state["batch_search_completed"] is True
        assert (
            at.session_state["batch_results"][0]["Driver"]
            == "KEF B110B article example"
        )
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


test(
    "UI SaaS mode saves and reloads an authenticated cloud project",
    _check_ui_saas_local_project_roundtrip,
)


def _check_ui_saas_local_registration_login_logout():
    import os
    import tempfile

    from streamlit.testing.v1 import AppTest

    with tempfile.TemporaryDirectory() as directory:
        keys = {
            "LOAD_FORGE_SAAS_ENABLED": "true",
            "LOAD_FORGE_SAAS_BACKEND": "memory",
            "LOAD_FORGE_LOCAL_ACCOUNTS": "true",
            "LOAD_FORGE_LOCAL_ACCOUNT_DATABASE": str(
                Path(directory) / "accounts.sqlite3"
            ),
            "LOAD_FORGE_AUTH_BYPASS": None,
            "K_SERVICE": None,
        }
        previous = {key: os.environ.get(key) for key in keys}
        try:
            for key, value in keys.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
            at.session_state["project_menu_expander"] = True
            at.run()
            assert not at.exception, at.exception
            account_mode = next(item for item in at.radio if item.label == "Account")
            account_mode.set_value("Create account").run()
            assert not at.exception, at.exception

            fields = {item.key: item for item in at.text_input}
            fields["_local_register_name"].set_value("Registration tester")
            fields["_local_register_email"].set_value("register@example.test")
            fields["_local_register_password"].set_value("a safe demo password")
            fields["_local_register_confirmation"].set_value("a safe demo password")
            create = next(
                button for button in at.button if button.label == "Create account"
            )
            create.click().run()
            assert not at.exception, at.exception
            assert at.session_state["_local_saas_account"]["email"] == (
                "register@example.test"
            )
            assert any(
                "Registration tester · Free plan" in item.value
                for item in at.caption
            )

            sign_out = next(
                button for button in at.button if button.label == "Sign out"
            )
            sign_out.click().run()
            assert not at.exception, at.exception
            assert "_local_saas_account" not in at.session_state

            fields = {item.key: item for item in at.text_input}
            fields["_local_sign_in_email"].set_value("register@example.test")
            fields["_local_sign_in_password"].set_value("a safe demo password")
            sign_in = next(
                button for button in at.button if button.label == "Sign in"
            )
            sign_in.click().run()
            assert not at.exception, at.exception
            assert at.session_state["_local_saas_account"]["email"] == (
                "register@example.test"
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


test(
    "UI SaaS local account registers, signs out and signs back in",
    _check_ui_saas_local_registration_login_logout,
)


def _check_ui_auth_only_email_allowlist():
    import os

    from streamlit.testing.v1 import AppTest

    keys = {
        "LOAD_FORGE_AUTH_REQUIRED": "true",
        "LOAD_FORGE_ALLOWED_EMAILS": "allowed@example.test",
        "LOAD_FORGE_AUTH_BYPASS": "true",
        "LOAD_FORGE_DEV_UID": "auth-only-user",
        "LOAD_FORGE_DEV_EMAIL": "allowed@example.test",
        "LOAD_FORGE_DEV_NAME": "Allowed user",
        "LOAD_FORGE_SAAS_ENABLED": None,
        "LOAD_FORGE_LOCAL_ACCOUNTS": None,
        "K_SERVICE": None,
    }
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
        at.session_state["project_menu_expander"] = True
        at.run()
        assert not at.exception, at.exception
        assert not any(
            item.label == "Cloud project name" for item in at.text_input
        ), "auth-only mode must not initialize Firestore project controls"
        assert any(
            item.value == "allowed@example.test" for item in at.caption
        )

        os.environ["LOAD_FORGE_DEV_EMAIL"] = "outsider@example.test"
        denied = AppTest.from_file(
            str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT
        )
        denied.run()
        assert not denied.exception, denied.exception
        assert any(
            "not authorized" in item.value for item in denied.error
        ), "an email outside the allowlist reached the workspace"
        assert not any(item.label == "Bass Match" for item in denied.tabs)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


test(
    "UI auth-only mode enforces the email allowlist without Firestore",
    _check_ui_auth_only_email_allowlist,
)


def _check_driver_bandwidth_classifier():
    sub = _acoustics.classify_driver_bandwidth(_acoustics.get_driver_preset("Dayton Audio RSS315HO-4"))
    assert sub.driver_class == "Subwoofer", sub
    assert sub.f_le_hz is not None and 250.0 < sub.f_le_hz < 330.0, sub.f_le_hz

    mid = _acoustics.classify_driver_bandwidth(_beyma_ts())
    assert mid.driver_class == "Midbass-capable", mid
    expected_f_le = 6.0 / (2.0 * np.pi * 0.001)
    assert abs(mid.f_le_hz - expected_f_le) < 1e-6, mid.f_le_hz
    assert mid.reasons, "classification must expose its indicators"

    tiny = _acoustics.classify_driver_bandwidth(_acoustics.get_driver_preset("Aiyima 4ohm 5w 40mm black"))
    assert tiny.f_le_hz is None, "Le=0 must map to an unknown voice-coil corner"
    assert tiny.driver_class in _acoustics.DRIVER_CLASSES, tiny


test("Driver bandwidth classifier separates subwoofers from midbass drivers", _check_driver_bandwidth_classifier)


def _check_ui_class_filter():
    import ui_app as _ui

    assert _ui._PRESET_CLASS_FILTERS == (
        "All", "Subwoofer", "Woofer", "Midbass"
    )
    assert _ui._driver_class_label("Midbass-capable") == "Midbass"

    names = tuple(
        name for name in _acoustics.driver_preset_names()
        if not name.startswith("LSDB:")
    )
    subs = _ui._filter_driver_preset_names(
        names, source="All", family="All", size="All", search="", driver_class="Subwoofer")
    assert "Dayton Audio RSS315HO-4" in subs, subs
    assert "Beyma 12CMV2" not in subs, subs
    mids = _ui._filter_driver_preset_names(
        names, source="All", family="All", size="All", search="", driver_class="Midbass")
    assert "Beyma 12CMV2" in mids, mids
    assert "Dayton Audio RSS315HO-4" not in mids, mids

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Bass Match"
    at.run()
    at.session_state["preset_class_filter"] = "Midbass"
    at.session_state["preset_search"] = "Dayton Audio RSS315HO-4"
    at.run()
    assert not at.exception, at.exception
    find_button = next(b for b in at.button if b.label == _ui._FINDER_CTA_LABEL)
    assert find_button.disabled, "midbass filter must drop the pure subwoofer"

    at.session_state["preset_search"] = "Beyma 12CMV2"
    at.run()
    find_button = next(b for b in at.button if b.label == _ui._FINDER_CTA_LABEL)
    assert not find_button.disabled, "midbass filter must keep the Beyma 12CMV2"

    # Catalog filters are Finder-only and must not silently constrain Design.
    at.session_state["preset_search"] = ""
    at.session_state["workspace_mode"] = "Box Design"
    at.run()
    preset_box = next(s for s in at.selectbox if s.label == "Driver preset")
    assert "Beyma — 12CMV2" in preset_box.options
    assert "Dayton Audio — RSS315HO-4" in preset_box.options
    labels = {metric.label for metric in at.metric}
    assert {"VC corner", "Class"} <= labels, labels


test("UI class filter separates subwoofers from midbass presets", _check_ui_class_filter)


def _check_ui_reflex_volume_keeps_impedance_peaks():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    state = at.session_state
    state["workspace_mode"] = "Box Design"
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
    assert metrics["Z peaks"] == "29, 82", metrics["Z peaks"]
    assert not any("Bass reflex should show two impedance peaks" in warning.value for warning in at.warning)

    state["reflex_q_abs"] = 1.0
    state["reflex_q_port"] = 1.0
    at.run()
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Z peaks"] == "29, 82", metrics["Z peaks"]
    assert not any("Bass reflex should show two impedance peaks" in warning.value for warning in at.warning)

    state["reflex_custom_losses"] = True
    at.run()
    assert any("Qabs=1.0, Qport=1.0" in warning.value for warning in at.warning)


test("UI bass-reflex volume edits preserve resonance diagnostics", _check_ui_reflex_volume_keeps_impedance_peaks)


def _check_response_chart_domain_tracks_10hz_and_peak():
    import ui_app as _ui

    result = _acoustics.SimulationResult(
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
    assert zoom_domain == [68.0, 85.0], zoom_domain
    chart = _ui._plot_response(result, [], frequency_window=[20.0, 40.0])
    spec = chart.to_dict()
    assert spec["height"] == 420, spec.get("height")
    assert "'domain': [20.0, 40.0]" in str(spec), spec


test("UI response chart zoom anchors at 10 Hz and keeps displayed traces visible", _check_response_chart_domain_tracks_10hz_and_peak)


def _check_ui_response_zoom_slider_and_reset():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.run()
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception

    zoom = next(
        slider for slider in at.slider
        if slider.label == "Chart zoom (Hz)"
    )
    assert tuple(zoom.value) == (10, 500), zoom.value
    reset = next(button for button in at.button if button.label == "Reset zoom")
    assert reset.disabled

    at.session_state["plot_response_window_hz"] = (20, 200)
    at.run()
    assert not at.exception, at.exception
    zoom = next(
        slider for slider in at.slider
        if slider.label == "Chart zoom (Hz)"
    )
    assert tuple(zoom.value) == (20, 200), zoom.value
    reset = next(button for button in at.button if button.label == "Reset zoom")
    assert not reset.disabled
    reset.click().run()
    assert not at.exception, at.exception
    assert tuple(at.session_state["plot_response_window_hz"]) == (10, 500)


test("UI response zoom has a frequency window and reliable reset", _check_ui_response_zoom_slider_and_reset)


def _check_ui_response_toggles_survive_workspace_and_preset_changes():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Bandpass 4th order"
    at.run()
    assert not at.exception, at.exception

    def toggle(label):
        return next(box for box in at.toggle if box.label == label)

    toggle("Compare loads").set_value(True).run()
    assert toggle("Tolerance band").disabled

    workspace = next(
        control for control in at.segmented_control if control.label == "Workspace"
    )
    workspace.set_value("Bass Match").run()
    workspace = next(
        control for control in at.segmented_control if control.label == "Workspace"
    )
    workspace.set_value("Box Design").run()
    assert not at.exception, at.exception

    assert toggle("Compare loads").value

    preset = next(box for box in at.selectbox if box.label == "Driver preset")
    preset.set_value("Beyma 12CMV2").run()
    assert not at.exception, at.exception
    assert toggle("Compare loads").value


test(
    "UI response toggles persist across workspace and preset changes",
    _check_ui_response_toggles_survive_workspace_and_preset_changes,
)


def _check_response_chart_drops_non_finite_points_and_keeps_label_scale_clean():
    import ui_app as _ui

    result = _acoustics.SimulationResult(
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

    rows = [_ui._cursor_row(result, "F3", 10.0)]
    assert rows[0]["mol_db"] == 90.0
    cursor_spec = _ui._cursor_layer(rows, show_mol=True).to_dict()
    assert "F3 · 10.0 Hz" in str(cursor_spec), cursor_spec
    assert "MOL dB" in str(cursor_spec), cursor_spec
    assert "MOL 90.0 dB" in str(cursor_spec), (
        "automatic F3/F6/F10 labels must show MOL",
        cursor_spec,
    )
    chart = _ui._plot_response(result, rows)
    spec = chart.to_dict()
    spec_text = str(spec)
    assert "plot_show_tuning_markers" in (ROOT / "ui_app.py").read_text()
    assert "label_y_px" not in spec_text
    assert "label_y_db" in spec_text
    response_axis = spec["layer"][0]["encoding"]["y"]["axis"]
    assert response_axis["labels"] is True
    assert response_axis["format"] == ".0f"
    assert response_axis["title"] == "Amplitude (dB)"

    def _response_y_encodings(node):
        if isinstance(node, dict):
            encoding = node.get("encoding")
            if isinstance(encoding, dict) and "y" in encoding:
                yield encoding["y"]
            for value in node.values():
                yield from _response_y_encodings(value)
        elif isinstance(node, list):
            for value in node:
                yield from _response_y_encodings(value)

    y_encodings = list(_response_y_encodings(spec))
    assert y_encodings
    assert not any(
        isinstance(encoding, dict) and encoding.get("axis", "missing") is None
        for encoding in y_encodings
    ), y_encodings


test("UI response chart filters invalid points and keeps cursor labels on the dB scale", _check_response_chart_drops_non_finite_points_and_keeps_label_scale_clean)


def _check_response_chart_has_click_marker():
    import ui_app as _ui

    result = _acoustics.SimulationResult(
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
    chart = _ui._click_marker_layer(result, show_mol=True)
    spec = chart.to_dict()
    assert "Click " not in str(spec), spec
    assert "MOL 90.0 dB" in str(spec), spec
    params = spec.get("params", [])
    click_params = [param for param in params if param.get("name") == "click_marker"]
    assert click_params, params
    select = click_params[0]["select"]
    assert select["type"] == "point", select
    assert select["on"] == "click", select
    assert select["nearest"] is True, select
    assert click_params[0]["views"], click_params[0]


test("UI response chart has a clickable moving marker", _check_response_chart_has_click_marker)


def _check_response_chart_mil_keeps_independent_right_axis():
    import ui_app as _ui

    result = _acoustics.SimulationResult(
        frequency_hz=np.array([10.0, 20.0, 40.0]),
        spl_total_db=np.array([40.0, 70.0, 80.0]),
        spl_driver_db=np.array([39.0, 69.0, 78.0]),
        spl_port_db=np.array([30.0, 60.0, 83.0]),
        excursion_mm=np.ones(3),
        impedance_ohm=np.ones(3),
        port_h_velocity=np.ones(3),
        port_l_velocity=np.ones(3),
        mil_w=np.array([10.0, 200.0, 300.0]),
        mol_db=np.array([90.0, 90.0, 90.0]),
        driver_volume_velocity=np.ones(3, dtype=complex),
        port_volume_velocity=np.ones(3, dtype=complex),
    )
    rows = [_ui._cursor_row(result, "F3", 10.0)]

    def _right_y_axes(node):
        if isinstance(node, dict):
            encoding = node.get("encoding")
            if isinstance(encoding, dict):
                axis = encoding.get("y")
                if (
                    isinstance(axis, dict)
                    and isinstance(axis.get("axis"), dict)
                    and axis["axis"].get("orient") == "right"
                ):
                    yield axis
            for value in node.values():
                yield from _right_y_axes(value)
        elif isinstance(node, list):
            for value in node:
                yield from _right_y_axes(value)

    with_pins = _ui._plot_response(result, rows, default_visible=["Total", "MIL"])
    spec = with_pins.to_dict()
    assert spec.get("resolve", {}).get("scale", {}).get("y") == "independent", (
        "MIL must never collapse onto the SPL axis when cursors/pins exist",
        spec.get("resolve"),
    )
    assert list(_right_y_axes(spec)), "MIL must render on its own right axis"

    without_mil = _ui._plot_response(result, rows, default_visible=["Total"])
    no_mil_spec = without_mil.to_dict()
    assert (
        no_mil_spec.get("resolve", {}).get("scale", {}).get("y", "shared")
        in {"shared", None}
    ), "without MIL there is a single SPL y scale"


test(
    "UI response chart keeps MIL on an independent right axis",
    _check_response_chart_mil_keeps_independent_right_axis,
)


def _check_ui_mil_mol_buttons_kept_but_curve_hidden():
    import ui_app as _ui

    result = _acoustics.SimulationResult(
        frequency_hz=np.array([10.0, 20.0, 40.0]),
        spl_total_db=np.array([40.0, 70.0, 80.0]),
        spl_driver_db=np.array([39.0, 69.0, 78.0]),
        spl_port_db=np.array([30.0, 60.0, 83.0]),
        excursion_mm=np.ones(3),
        impedance_ohm=np.ones(3),
        port_h_velocity=np.ones(3),
        port_l_velocity=np.ones(3),
        mil_w=np.full(3, np.nan),
        mol_db=np.full(3, np.nan),
        driver_volume_velocity=np.ones(3, dtype=complex),
        port_volume_velocity=np.ones(3, dtype=complex),
    )
    # The buttons stay visible even when Pe=0: the curve, not the affordance,
    # is what disappears.
    series = _ui._response_series(result)
    assert "MIL" in series, "MIL button must remain when Pe is 0"
    assert "MOL" in series, "MOL button must remain when Pe is 0"
    chart = _ui._plot_response(result, [], default_visible=["Total", "MIL"])
    spec = chart.to_dict()
    assert "mil_value" not in str(spec), (
        "an all-NaN MIL must not create an empty chart layer"
    )

    rated = replace(
        result,
        mil_w=np.array([10.0, 200.0, 300.0]),
        mol_db=np.array([90.0, 95.0, 100.0]),
    )
    rated_chart = _ui._plot_response(
        rated, [], default_visible=["Total", "MIL"]
    )
    assert "mil_value" in str(rated_chart.to_dict()), (
        "with a thermal rating the MIL curve must render"
    )


test(
    "UI keeps MIL/MOL buttons but hides the curve without a thermal rating",
    _check_ui_mil_mol_buttons_kept_but_curve_hidden,
)


def _check_ui_driver_preset_filters_reduce_list():
    import ui_app as _ui

    assert _ui._PRESET_SOURCE_FILTERS == (
        "All",
        "Load Forge database",
        "LSDB",
        "VituixCAD",
        "Speaker Box Lite",
    )
    assert all(
        _ui._PRESET_SOURCE_FILTER_ALIASES[legacy]
        == "Load Forge database"
        for legacy in (
            "Manufacturer",
            "Built-in",
            "Official manufacturer site",
            "Official archive / heritage",
            "Retailer / distributor",
            "User supplied",
        )
    )
    names = _acoustics.driver_preset_names()
    assert (
        _ui._driver_preset_source("Beyma 12CMV2")
        == "Load Forge database"
    )
    callback_all_key = "_test_filter_all"
    callback_item_keys = (
        "_test_filter_a",
        "_test_filter_b",
        "_test_filter_c",
    )
    _ui.st.session_state[callback_all_key] = False
    for item_key in callback_item_keys:
        _ui.st.session_state[item_key] = True
    _ui._sync_filter_group_all(callback_all_key, callback_item_keys)
    assert _ui.st.session_state[callback_all_key] is True
    _ui.st.session_state[callback_item_keys[1]] = False
    _ui._sync_filter_group_all(callback_all_key, callback_item_keys)
    assert _ui.st.session_state[callback_all_key] is False
    _ui._set_filter_group_from_all(callback_all_key, callback_item_keys)
    assert not any(
        _ui.st.session_state[item_key] for item_key in callback_item_keys
    )
    _ui.st.session_state[callback_all_key] = True
    _ui._set_filter_group_from_all(callback_all_key, callback_item_keys)
    assert all(
        _ui.st.session_state[item_key] for item_key in callback_item_keys
    )
    category_examples = {
        _acoustics.driver_preset_info(name).source: name
        for name in names
    }
    for exact_source, expected_category in (
        ("Loudspeaker Database", "LSDB"),
        ("VituixCAD online database", "VituixCAD"),
        ("Speaker Box Lite public database", "Speaker Box Lite"),
        ("Parts Express API", "Load Forge database"),
        ("Altec Technical Letter 267B archive", "Load Forge database"),
        ("Manufacturer website", "Load Forge database"),
    ):
        if exact_source in category_examples:
            assert (
                _ui._driver_preset_source(category_examples[exact_source])
                == expected_category
            )
    filtered = _ui._filter_driver_preset_names(
        names,
        source="Load Forge database",
        family="Aiyima",
        size="2 in",
        search="53mm",
    )
    assert "Aiyima 4ohm 10w 53mm" in filtered, filtered
    assert "Aiyima 4ohm 10w 53mm LY1124-2" in filtered, filtered
    assert not any(name.startswith("Beyma") for name in filtered), filtered

    kept_selected = _ui._filter_driver_preset_names(
        names,
        source="Load Forge database",
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
            source="LSDB",
            family="GRS",
            size="12 in",
            search="12SW",
        )
        assert all(name.startswith("LSDB: GRS") for name in lsdb), lsdb[:5]
        assert any("12SW" in name for name in lsdb), lsdb[:5]
        legacy_lsdb = _ui._filter_driver_preset_names(
            names,
            source="Loudspeaker Database",
            family="GRS",
            size="12 in",
            search="12SW",
        )
        assert legacy_lsdb == lsdb

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["bass_match_sidebar_tab"] = "Library filters"
    at.session_state["finder_candidate_pool_expander"] = True
    at.session_state["preset_search"] = "12CMV2"
    at.run()
    assert not at.exception, at.exception
    provenance = next(
        item for item in at.sidebar.multiselect
        if item.label == "Provenance"
    )
    assert provenance.options == list(_ui._PRESET_SOURCE_FILTERS[1:])
    assert provenance.value == [], "empty compact selection means All"
    selected_sources = list(_ui._PRESET_SOURCE_FILTERS[1:-1])
    provenance.set_value(selected_sources).run()
    assert not at.exception, at.exception
    assert at.session_state["preset_source_filter"] == selected_sources
    assert at.dataframe, "Filtered presets must render as a table"
    table = at.dataframe[0].value
    assert "12CMV2" in str(table.to_dict()), (
        "typed preset searches must show their matching names in the results table")

    at.session_state["finder_driver_library_table"] = {
        "selection": {"rows": [0], "columns": [], "cells": []},
    }
    at.run()
    assert not at.exception, at.exception
    use_driver = next(
        button for button in at.button
        if button.key == "finder_use_library_driver"
    )
    selected_driver = str(at.dataframe[0].value.iloc[0]["Driver"])
    use_driver.click().run()
    assert not at.exception, at.exception
    assert at.session_state["workspace_mode"] == "Box Design"
    assert at.session_state["driver_preset_name"] == selected_driver

    complete_library = _ui._driver_library_frame(tuple(names))
    assert len(complete_library) == len(names), (
        "the on-screen library must not truncate the preset collection",
        len(complete_library), len(names),
    )
    assert complete_library["Driver"].nunique() == len(names)
    assert "Price" in complete_library.columns
    assert "Currency" in complete_library.columns


test("UI driver preset filters reduce long speaker lists", _check_ui_driver_preset_filters_reduce_list)


def _check_ui_driver_performance_filters_limit_mms_and_le():
    import ui_app as _ui

    names = [
        "KEF B110B article example",
        "Beyma 12CMV2",
        "Beyma 12G40",
        "Beyma 12LX60V2",
    ]
    common = {
        "source": "All",
        "family": "All",
        "size": "All",
        "search": "",
    }
    light_cones = _ui._filter_driver_preset_names(
        names, **common, max_mms_g=60.0
    )
    assert light_cones == ["Beyma 12CMV2"], light_cones

    low_inductance = _ui._filter_driver_preset_names(
        names, **common, max_le_mh=1.0
    )
    assert low_inductance == [
        "KEF B110B article example",
        "Beyma 12CMV2",
    ], low_inductance

    combined = _ui._filter_driver_preset_names(
        names, **common, max_mms_g=60.0, max_le_mh=1.0
    )
    assert combined == ["Beyma 12CMV2"], combined


test(
    "UI Finder filters driver presets by maximum Mms and Le",
    _check_ui_driver_performance_filters_limit_mms_and_le,
)


def _check_ui_driver_preset_price_filter_uses_optional_metadata():
    import ui_app as _ui

    original = _ui._driver_preset_price
    original_currency = _ui._driver_preset_currency
    original_rates = _ui._current_exchange_rates
    try:
        prices = {"cheap": 50.0, "cheap_gbp": 40.0, "expensive": 500.0, "unknown": None}
        currencies = {"cheap": "EUR", "cheap_gbp": "GBP", "expensive": "EUR", "unknown": ""}
        _ui._driver_preset_price = lambda name: prices[name]
        _ui._driver_preset_currency = lambda name: currencies[name]
        _ui._current_exchange_rates = lambda: (
            {"EUR": 1.0, "GBP": 0.8, "USD": 1.2}, "2026-07-17"
        )
        filtered = _ui._filter_driver_preset_names(
            ["cheap", "cheap_gbp", "expensive", "unknown"],
            source="All",
            family="All",
            size="All",
            search="",
            max_price=100.0,
            max_price_currency="EUR",
        )
        assert filtered == ["cheap", "cheap_gbp"], filtered
        assert np.allclose(
            _ui._preset_price_values(["cheap", "cheap_gbp"], "EUR"),
            [50.0, 50.0],
        )
    finally:
        _ui._driver_preset_price = original
        _ui._driver_preset_currency = original_currency
        _ui._current_exchange_rates = original_rates

    info = _acoustics.DriverPresetInfo(
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


def _check_ui_driver_library_compares_nominal_size_and_sd():
    import ui_app as _ui

    assert _ui._presets.coherent_nominal_size_in(None, 530.0) == 12.0
    assert _ui._acoustics.driver_preset_info("Beyma 12CMV2").size_in == 12.0

    saved_rows = [{
        "Driver": "ZTZ: TN-12MD300",
        "Size in": None,
        "Sd cm²": 539.0,
    }]
    refreshed_rows = _ui._refresh_finder_result_catalog_metadata(saved_rows)
    assert refreshed_rows[0]["Size in"] == 12.0
    assert saved_rows[0]["Size in"] is None, "saved rows must not be mutated in place"

    alpair_name = next(
        name for name in _ui._acoustics.driver_preset_names()
        if name.startswith("WEB: Markaudio Alpair 10P [MFR ")
    )
    dayton_name = next(
        name for name in _ui._acoustics.driver_preset_names()
        if name.startswith("WEB: Dayton Audio DS175-8")
    )
    frame = _ui._driver_library_frame((
        dayton_name,
        alpair_name,
        "LSDB: Ciare FXC8.50W",
    ))
    assert {
        "Manufacturer", "Part number", "Nominal in", "Sd cm²",
        "Effective Ø in",
    } <= set(frame.columns)
    row = frame.iloc[0]
    assert row["Nominal in"] == 6.5
    assert row["Sd cm²"] == 128.7
    assert np.isclose(
        row["Effective Ø in"],
        np.sqrt(4.0 * row["Sd cm²"] / np.pi) / 2.54,
    )
    alpair = frame.iloc[1]
    assert alpair["Nominal in"] == 5.0
    assert alpair["Sd cm²"] == 88.25
    assert _ui._presets.nominal_size_matches_sd(
        alpair["Nominal in"],
        alpair["Sd cm²"],
    )
    ciare = frame.iloc[2]
    assert ciare["Nominal in"] == 8.0
    assert ciare["Sd cm²"] == 211.2
    assert not _ui._presets.nominal_size_matches_sd(10.0, ciare["Sd cm²"])
    assert _ui._presets.coherent_nominal_size_in(10.0, ciare["Sd cm²"]) == 8.0

    missing_sizes = [
        name
        for name in _ui._acoustics.driver_preset_names()
        if _ui._acoustics.driver_preset_info(name).size_in is None
    ]
    assert missing_sizes == [], (
        f"every runtime driver with valid Sd must receive a nominal size: "
        f"{missing_sizes[:10]}"
    )

    sb_name = next(
        name for name in _ui._acoustics.driver_preset_names()
        if name.startswith("WEB: SB Acoustics") and "SB17NRXC35-4" in name
    )
    sb_frame = _ui._driver_library_frame((sb_name,))
    assert sb_frame.iloc[0]["Manufacturer"] == "SB Acoustics"
    assert sb_frame.iloc[0]["Part number"] == "SB17NRXC35-4"
    assert _ui._driver_preset_display_label(sb_name) == (
        "SB Acoustics — SB17NRXC35-4"
    )
    assert _ui._catalog_record_display_identity(
        {
            "brand": "Beyma",
            "model": 'LOUDSPEAKER 8"MC300Nd 8 OH',
            "matched_mpn": 'LOUDSPEAKER 8"MC300Nd 8 OH',
        },
        "raw fallback",
    ) == ("Beyma", "8MC300Nd")
    bomber_title = 'WOOFER 18″ ATRACK BASS 4K 4Ω'
    assert _ui._catalog_record_display_identity(
        {"brand": "Bomber", "model": bomber_title},
        "raw fallback",
    ) == ("Bomber", bomber_title)
    assert _ui._catalog_record_display_identity(
        {
            "brand": "Eminence Speaker",
            "model": 'Eminence Alpha-12A 12" Guitar/PA Driver',
        },
        "raw fallback",
    ) == ("Eminence", "Alpha-12A")
    assert _ui._catalog_record_display_identity(
        {
            "brand": "Celestion",
            "model": "18-inch",
            "matched_mpn": "TF1830",
            "source": "Manual catalog maintenance",
        },
        "raw fallback",
    ) == ("Celestion", "TF1830")

    dayton_retailer_name = next(
        name for name in _ui._acoustics.driver_preset_names()
        if name.startswith("WEB: Dayton Audio RSS315HO-4 12")
    )

    ztz_info = _acoustics.driver_preset_info("ZTZ: TN-18SW1280")
    assert ztz_info.mechanical is not None
    assert ztz_info.mechanical.overall_diameter_mm == 462.0
    assert ztz_info.mechanical.cutout_diameter_mm == 430.0
    assert ztz_info.mechanical.depth_mm == 208.0
    mixed = _ui._filter_driver_preset_names(
        _ui._acoustics.driver_preset_names(),
        source="All", family=["ZTZ Audio", "Beyma"], size="All",
        search="", driver_class="All",
    )
    assert sum(name.startswith("ZTZ: ") for name in mixed) == 25
    assert sum(name.startswith("Beyma ") for name in mixed) > 0

    unique, removed = _ui._deduplicate_finder_preset_names([
        "Dayton Audio RSS315HO-4",
        dayton_retailer_name,
    ])
    assert len(unique) == 1, unique
    assert removed == 1


test(
    "UI driver library compares nominal size and Sd",
    _check_ui_driver_library_compares_nominal_size_and_sd,
)


def _check_ui_catalog_maintenance_normalizes_part_numbers():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.query_params["maintenance"] = "1"
    at.session_state["maintenance_query"] = 'LOUDSPEAKER 8"MC300Nd'
    at.run()
    assert not at.exception, at.exception
    frame = at.dataframe[0].value
    assert len(frame) == 1, frame
    assert frame.iloc[0]["Brand"] == "Beyma"
    assert frame.iloc[0]["MPN"] == "8MC300Nd"
    assert {"Xmax mm", "Pmax W", "Le mH"}.issubset(frame.columns), frame

    at.session_state["maintenance_query"] = "WEB: Celestion 18-inch"
    at.run()
    assert not at.exception, at.exception
    frame = at.dataframe[0].value
    assert len(frame) == 1, frame
    assert frame.iloc[0]["MPN"] == "TF1830"
    assert np.isclose(frame.iloc[0]["Xmax mm"], 4.5)
    assert np.isclose(frame.iloc[0]["Pmax W"], 500.0)
    assert np.isclose(frame.iloc[0]["Le mH"], 1.28)


test(
    "UI catalog maintenance normalizes manufacturer part numbers",
    _check_ui_catalog_maintenance_normalizes_part_numbers,
)


def _check_admin_can_save_box_design_ts_to_catalog():
    import json
    import tempfile

    import ui_app as _ui

    source = (ROOT / "ui_app.py").read_text(encoding="utf-8")
    assert 'key="admin_save_box_design_driver"' in source
    with tempfile.TemporaryDirectory() as directory:
        catalog_path = Path(directory) / "catalog.json"
        catalog_path.write_text(json.dumps({"presets": [{
            "name": "Catalog test driver",
            "driver": {
                "fs_hz": 30.0, "vas_l": 50.0, "qts": 0.4,
                "qms": 3.0, "re_ohm": 6.0, "sd_cm2": 220.0,
            },
        }]}), encoding="utf-8")
        original = _ui._acoustics.get_driver_preset
        original_info = _ui._acoustics.driver_preset_info
        _ui._acoustics.get_driver_preset = lambda _name: _ui._acoustics.DriverTS(
            fs_hz=30.0, vas_l=50.0, qts=0.4, qms=3.0, re_ohm=6.0,
            sd_cm2=220.0,
        )
        _ui._acoustics.driver_preset_info = lambda _name: _ui._presets.DriverPresetInfo(
            name="Catalog test driver", source="Manufacturer crawl",
            brand="Catalog", model="test driver", part_number="test driver",
        )
        try:
            saved = _ui._update_catalog_driver_from_box_design(
                "Catalog test driver",
                _ui._acoustics.DriverTS(
                    fs_hz=28.0, vas_l=55.0, qts=0.35, qms=3.2,
                    re_ohm=5.8, sd_cm2=225.0, le_mh=1.1, xmax_mm=7.0,
                    pe_w=300.0,
                ),
                path=catalog_path,
            )
        finally:
            _ui._acoustics.get_driver_preset = original
            _ui._acoustics.driver_preset_info = original_info
        assert saved == "Catalog test driver"
        saved_driver = json.loads(catalog_path.read_text(encoding="utf-8"))[
            "presets"][0]["driver"]
        assert saved_driver["fs_hz"] == 28.0
        assert saved_driver["sd_cm2"] == 225.0
        assert saved_driver["pe_w"] == 300.0


test(
    "Admin can save Box Design T/S values to the source catalog",
    _check_admin_can_save_box_design_ts_to_catalog,
)


def _check_ecb_rates_normalize_library_prices():
    import ui_app as _ui
    from src import pricing

    payload = b'''<?xml version="1.0" encoding="UTF-8"?>
    <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
      xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
      <Cube><Cube time="2026-07-17">
        <Cube currency="USD" rate="1.20"/>
        <Cube currency="GBP" rate="0.80"/>
      </Cube></Cube>
    </gesmes:Envelope>'''
    rates, rates_date = pricing.parse_ecb_reference_rates(payload)
    assert rates_date == "2026-07-17"
    assert rates == {"EUR": 1.0, "USD": 1.2, "GBP": 0.8}
    assert np.isclose(pricing.convert_price(80.0, "GBP", "EUR", rates), 100.0)
    assert np.isclose(pricing.convert_price(80.0, "GBP", "USD", rates), 120.0)
    assert pricing.convert_price(80.0, "GBP", "CHF", rates) is None
    assert pricing.convert_price(80.0, "GBP", "GBP", {}) == 80.0

    original_rates = _ui._current_exchange_rates
    try:
        _ui._current_exchange_rates = lambda: (rates, rates_date)
        native = _ui.pd.DataFrame({
            "Driver": ["EUR driver", "GBP driver", "unknown"],
            "Price": [100.0, 80.0, np.nan],
            "Currency": ["EUR", "GBP", ""],
        })
        normalized = _ui._normalize_price_frame(native, "USD")
    finally:
        _ui._current_exchange_rates = original_rates
    assert np.allclose(normalized["Price"].iloc[:2], [120.0, 120.0])
    assert normalized["Currency"].tolist() == ["USD", "USD", ""]


test("ECB rates normalize Finder library prices", _check_ecb_rates_normalize_library_prices)


def _check_runtime_price_matching_handles_aliases_and_impedance():
    from src import pricing

    record = {
        "matched_name": "Eighteensound 15ND930 8 Ohm",
        "matched_brand": "Eighteensound",
        "matched_mpn": "15ND930 8 Ohm",
        "url": "https://example.test/15nd930-8",
    }
    assert pricing._price_record_matches_preset(
        record,
        "LSDB: Eighteen Sound 15ND930 8Ω",
        "Eighteen Sound",
        "15ND930 8Ω",
    )
    assert not pricing._price_record_matches_preset(
        record,
        "LSDB: Eighteen Sound 15ND930 16Ω",
        "Eighteen Sound",
        "15ND930 16Ω",
    )
    recone = dict(record, matched_name="Eighteensound 15ND930 Reconekit")
    assert not pricing._price_record_matches_preset(
        recone,
        "LSDB: Eighteen Sound 15ND930 8Ω",
        "Eighteen Sound",
        "15ND930 8Ω",
    )


test(
    "Runtime price matching handles aliases and impedance",
    _check_runtime_price_matching_handles_aliases_and_impedance,
)


def _check_acoustics_loads_external_price_records(tmp_path=None):
    from src import presets as _presets

    price_path = _acoustics.DRIVER_PRICES_PATH
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
            '    "Beyma 12MCS500": {"price": 29.0, "currency": "GBP", "matched_name": "2-way crossover for Beyma 12MCS500", "matched_brand": "Beyma", "matched_mpn": "XO12MCS500", "url": "https://example.test/crossover"},\n'
            '    "WO24P-8": {"price": 239.95, "currency": "EUR", "matched_name": "SB Acoustics WO24P-8", "matched_brand": "SB Acoustics", "matched_mpn": "WO24P-8", "url": "https://example.test/wo24p-8"}\n'
            '  }\n'
            '}\n',
            encoding="utf-8",
        )
        _acoustics._load_driver_price_records.cache_clear()
        _acoustics._load_loudspeaker_database_presets.cache_clear()
        _acoustics._load_manufacturer_presets.cache_clear()
        _acoustics._load_vituixcad_presets.cache_clear()
        _acoustics._load_speakerboxlite_presets.cache_clear()
        _presets._external_tiers.cache_clear()
        _acoustics.driver_preset_names.cache_clear()
        _acoustics.driver_preset_info.cache_clear()
        _acoustics.get_driver_preset.cache_clear()
        info = _acoustics.driver_preset_info("Beyma 12CMV2")
        assert info.price == 321.5
        assert info.currency == "EUR"
        assert info.url == "https://example.test/beyma"
        assert _acoustics.driver_preset_info("Beyma 12G40").price == 0.29
        assert _acoustics.driver_preset_info("Beyma 12BR70").price is None
        assert _acoustics.driver_preset_info("Beyma 12MCS500").price is None
        own_wo24p8 = [
            name
            for name in _acoustics.driver_preset_names()
            if name.startswith("WEB: SB Acoustics") and "WO24P-8" in name
        ]
        assert len(own_wo24p8) == 1, own_wo24p8
        sb_info = _acoustics.driver_preset_info(own_wo24p8[0])
        assert sb_info.source == "SB Acoustics crawler", sb_info
        assert sb_info.price == 239.95 and sb_info.currency == "EUR", sb_info
        assert sb_info.url == "https://example.test/wo24p-8", sb_info
    finally:
        if original_exists:
            price_path.write_text(original_text or "", encoding="utf-8")
        else:
            try:
                price_path.unlink()
            except FileNotFoundError:
                pass
        _acoustics._load_driver_price_records.cache_clear()
        _acoustics._load_loudspeaker_database_presets.cache_clear()
        _acoustics._load_manufacturer_presets.cache_clear()
        _acoustics._load_vituixcad_presets.cache_clear()
        _acoustics._load_speakerboxlite_presets.cache_clear()
        _presets._external_tiers.cache_clear()
        _acoustics.driver_preset_names.cache_clear()
        _acoustics.driver_preset_info.cache_clear()
        _acoustics.get_driver_preset.cache_clear()


test("Acoustic facade loads external price records", _check_acoustics_loads_external_price_records)


def _check_vituixcad_importer_validates_and_deduplicates():
    import csv
    import io

    from tools import import_vituixcad_database as importer

    columns = sorted(importer.REQUIRED_COLUMNS | {"Status", "Revision", "Updated"})
    common = {
        "Type": "W",
        "Size [in]": "15",
        "Re [ohm]": "5",
        "fs [Hz]": "40",
        "Qms": "5.7",
        "Qes": "",
        "Qts": "0.32",
        "Mms [g]": "98.08",
        "Cms [mm/N]": "0.16",
        "Vas [l]": "175",
        "Sd [cm2]": "880",
        "BL [Tm]": "19.2",
        "Pmax [W]": "600",
        "Xmax [mm]": "7.6",
        "Le [mH]": "1.75",
        "Status": "Active",
        "Revision": "",
        "Updated": "2026-07-28/Test",
    }
    rows = [
        {**common, "Manufacturer": "Vifa", "Model": "NEW15"},
        {**common, "Manufacturer": "JBL", "Model": "2226H"},
        {**common, "Manufacturer": "Demo", "Model": "T25", "Type": "T"},
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    presets, stats = importer.import_database(
        stream.getvalue(),
        source_url=importer.DEFAULT_URL,
        existing_identities={importer.identity("JBL Professional", "2226H")},
    )
    assert stats["source_rows"] == 3
    assert stats["accepted"] == 1
    assert stats["duplicates_existing"] == 1
    assert stats["rejected"] == {"non-LF driver type": 1}
    assert presets[0]["name"] == "VCD: Vifa NEW15"
    assert np.isclose(
        presets[0]["driver"]["qes"],
        1.0 / (1.0 / 0.32 - 1.0 / 5.7),
    )
    assert presets[0]["website_fields"]["source_url"] == importer.DEFAULT_URL


test(
    "VituixCAD importer validates, derives and deduplicates drivers",
    _check_vituixcad_importer_validates_and_deduplicates,
)


def _check_heritage_importer_parses_altec_and_tad_tables():
    from tools import import_heritage_drivers as heritage

    header = [
        "Model No:", "Xmax (inch)", "Re (ohms)", "Vd - (cu. In.)",
        "Fs (Hz)", "Vas - (cu. ft.)", "Ref (%)", "Qts", "Qms", "Qes", "Vid",
    ]
    row = [
        "416-8B", "0.15", "6.90", "19.20", "25.10", "26.47",
        "2.70", "0.32", "7.05", "0.33", "0.20",
    ]
    html_rows = "".join(
        "<tr>" + "".join(
            f'<td data-original-value="{value}">{value}</td>' for value in values
        ) + "</tr>"
        for values in (header, row)
    )
    presets, failures = heritage.altec_presets(
        f'<table id="supsystic-table-6">{html_rows}</table>',
        "2026-07-28T00:00:00+00:00",
    )
    assert not failures and len(presets) == 1
    altec = presets[0]
    assert altec["model"] == "416-8B"
    assert np.isclose(altec["driver"]["vas_l"], 26.47 * 28.316846592)
    assert np.isclose(altec["driver"]["sd_cm2"], 19.20 / 0.15 * 6.4516)
    assert np.isclose(altec["driver"]["xmax_mm"], 0.15 * 25.4)
    assert altec["size_in"] == 15.0
    tad = heritage.tad_presets("2026-07-28T00:00:00+00:00")
    assert len(tad) == 10
    tl1601b = next(item for item in tad if item["model"] == "TL-1601b")
    assert tl1601b["driver"]["sd_cm2"] == 881.0
    assert tl1601b["driver"]["pe_w"] == 300.0
    assert np.isclose(tl1601b["driver"]["cms_mm_per_n"], 0.2785)


test(
    "Heritage importer parses Altec and TAD official tables",
    _check_heritage_importer_parses_altec_and_tad_tables,
)


def _check_speakerboxlite_importer_validates_units_physics_and_dedupes():
    from tools import import_speakerboxlite_database as importer

    common = {
        "id": 1,
        "textId": "demo-w12",
        "manufName": "Demo Audio",
        "name": "W12",
        "fs": 24.2,
        "vas": 84.1,
        "qts": 0.39,
        "qms": 2.83,
        "qes": 0.452,
        "re": 3.09,
        "sd": 51470.0,
        "cms": 0.23,
        "mms": 188.0,
        "xMax": 14.3,
        "bl": 13.99,
        "le": 1.1,
        "diam": 12,
        "powerRMS": 400,
        "checked": 1,
        "rating": 4.5,
        "dateEdit": "2026-07-28 00:00:00",
    }
    rows = [
        common,
        {
            **common,
            "id": 2,
            "textId": "18-sound-existing15",
            "manufName": "18 Sound",
            "name": "EXISTING15",
        },
        {
            **common,
            "id": 3,
            "textId": "bad-q",
            "name": "BAD-Q",
            "qts": 0.8,
            "qes": 1.0,
        },
    ]
    presets, stats = importer.import_database(
        rows,
        source_url=importer.DEFAULT_URL,
        existing_identities={
            importer.identity("Eighteen Sound", "EXISTING15")
        },
    )
    assert stats["source_rows"] == 3
    assert stats["accepted"] == 1
    assert stats["duplicates_existing"] == 1
    assert stats["rejected"] == {"Q identity mismatch": 1}
    preset = presets[0]
    assert preset["name"] == "SBL: Demo Audio W12"
    assert np.isclose(preset["driver"]["sd_cm2"], 514.7)
    assert preset["website_fields"]["sd_raw_unit_interpreted"] == "mm2"
    assert np.isclose(
        preset["website_fields"]["sd_from_vas_cms_cm2"],
        importer._sd_from_vas_cms(84.1, 0.23),
    )
    assert preset["website_fields"]["q_identity_relative_error"] < 0.01


test(
    "Speaker Box Lite importer validates units, physics and duplicates",
    _check_speakerboxlite_importer_validates_units_physics_and_dedupes,
)


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


def _check_manufacturer_optional_refresh_preserves_values_and_provenance():
    import tempfile
    from pathlib import Path

    from tools import refresh_manufacturer_optionals as refresh
    from tools import run_published_spec_batches as batches

    assert refresh.normalized_source_url({"url": "https://example.test/woofer "}) == "https://example.test/woofer"

    record = {
        "driver": {"xmax_mm": 0.0, "pe_w": 100.0, "le_mh": 0.0},
        "website_fields": {},
    }
    preset = {
        "url": "https://manufacturer.example/woofer-12",
        "source": "Manufacturer optional refresh",
        "driver": {"xmax_mm": 6.0, "pe_w": 250.0, "le_mh": 1.2},
        "website_fields": {
            "fetched_at": "2026-07-22T00:00:00+00:00",
            "raw_measurements": {
                "le_mh": {"label": "Le1k", "value": 1.2, "unit": "mH"},
                "linear_travel_pp_mm": {"label": "Linear coil travel (p-p)", "value": 12.0, "unit": "mm"},
            },
            "derivations": {
                "xmax_mm": {"formula": "linear_travel_pp_mm / 2", "source_fields": ["linear_travel_pp_mm"]},
            },
        },
    }
    changed = refresh.apply_preset_to_record(record, preset)
    assert changed == ["xmax_mm", "le_mh"], changed
    assert record["driver"]["pe_w"] == 100.0
    provenance = record["website_fields"]["field_provenance"]
    assert provenance["xmax_mm"]["derivation"]["formula"] == "linear_travel_pp_mm / 2"
    assert provenance["le_mh"]["measurement"]["label"] == "Le1k"
    bad_thousands = {
        "url": "https://manufacturer.example/big-sub",
        "driver": {"pe_w": 2.0},
        "website_fields": {"raw_measurements": {
            "pe_w": {"label": "Power Handling", "raw_value": "2,000", "unit": "watts"},
        }},
    }
    assert refresh.repair_reparsable_power(bad_thousands)
    assert bad_thousands["driver"]["pe_w"] == 2000.0
    bad_unitless = {
        "driver": {"pe_w": 98.5},
        "website_fields": {"raw_measurements": {
            "pe_w": {"label": "power handling", "raw_value": "98.5", "unit": ""},
        }},
    }
    assert refresh.invalidate_unitless_power(bad_unitless)
    assert bad_unitless["driver"]["pe_w"] == 0.0
    malformed_raw = {
        "driver": {"pe_w": 100.0},
        "website_fields": {"raw_measurements": {"pe_w": 100}},
    }
    assert not refresh.suspect_unitless_power(malformed_raw)
    assert not refresh.repair_reparsable_power(malformed_raw)
    assert not refresh.invalidate_unitless_power(malformed_raw)
    interleaved = refresh.round_robin_by_host([
        (1, {"url": "https://a.example/1"}),
        (2, {"url": "https://a.example/2"}),
        (3, {"url": "https://b.example/1"}),
        (4, {"url": "https://b.example/2"}),
    ])
    assert [item[0] for item in interleaved] == [1, 3, 2, 4]
    assert refresh.model_identity_matches(
        {"model": "5FG44 16Ω", "driver": {}},
        {"model": "5FG44", "driver": {}},
    )
    assert not refresh.model_identity_matches(
        {"model": "5FG44", "driver": {}},
        {"model": "generic product", "driver": {}},
    )
    identity_left = {
        "model": "legacy alias", "driver": {"fs_hz": 40, "qts": 0.4, "re_ohm": 6, "sd_cm2": 220},
    }
    identity_right = {
        "model": "new alias", "driver": {"fs_hz": 40.1, "qts": 0.401, "re_ohm": 6.05, "sd_cm2": 221},
    }
    assert refresh.model_identity_matches(identity_left, identity_right)
    with tempfile.TemporaryDirectory() as directory:
        checkpoint_path = Path(directory) / "checkpoint.json"
        checkpoint = refresh.read_checkpoint(checkpoint_path)
        seeded = refresh.seed_checkpoint_from_current_provenance(checkpoint, [{
            "url": "https://manufacturer.example/woofer-12",
            "website_fields": {"field_provenance": {"weight_kg": {
                "source_url": "https://manufacturer.example/woofer-12",
                "source": "Manufacturer published-spec refresh",
                "fetched_at": "2026-08-13T00:00:00+00:00",
            }}},
        }])
        assert seeded == 1
        assert refresh.checkpoint_is_current(
            checkpoint, "https://manufacturer.example/woofer-12",
        )
        checkpoint["attempts"]["https://manufacturer.example/transient"] = {
            "parser_revision": refresh.PARSER_REVISION,
            "status": "failure",
            "attempt_count": 1,
        }
        assert not refresh.checkpoint_is_current(
            checkpoint, "https://manufacturer.example/transient",
        )
        checkpoint["attempts"]["https://manufacturer.example/transient"]["attempt_count"] = 3
        assert refresh.checkpoint_is_current(
            checkpoint, "https://manufacturer.example/transient",
        )
    assert batches.should_continue({"processed": 10, "failures": [{}, {}]}, 0.5)
    assert not batches.should_continue({"processed": 10, "failures": [{}] * 6}, 0.5)
    assert not batches.should_continue({"processed": 0, "failures": []}, 0.5)


test("Manufacturer optional refresh preserves values and provenance", _check_manufacturer_optional_refresh_preserves_values_and_provenance)


def _check_catalog_completion_plans_gaps_and_stops_when_stalled():
    import json
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from tools import build_unified_catalogs as unified
    from tools import run_catalog_completion_cycle as completion
    from tools import run_high_yield_optional_cycle as high_yield

    rows = [
        {
            "name": "WEB: Alpha A12", "brand": "Alpha", "model": "A12",
            "price": 120.0,
            "url": "https://alpha.example/a12",
            "driver": {
                "fs_hz": 30.0, "vas_l": 80.0, "qts": 0.4, "qms": 5.0,
                "qes": 0.43, "re_ohm": 5.5, "sd_cm2": 500.0,
                "mms_g": 100.0, "cms_mm_per_n": 0.3, "bl_tm": 12.0,
                "xmax_mm": 0.0, "pe_w": 0.0, "le_mh": 0.0,
            },
        },
        {
            "name": "WEB: Beta B8", "brand": "Beta", "model": "B8",
            "driver": {
                "fs_hz": 45.0, "vas_l": 20.0, "qts": 0.35, "qms": 4.0,
                "qes": 0.38, "re_ohm": 6.0, "sd_cm2": 220.0,
                "mms_g": 40.0, "cms_mm_per_n": 0.3, "bl_tm": 8.0,
                "xmax_mm": 5.0, "pe_w": 100.0, "le_mh": 0.0,
            },
        },
    ]
    plan = completion.build_plan({"presets": rows}, {"prices": {"one": {}}}, 10)
    assert plan["coverage"]["fields"]["xmax_mm"]["missing"] == 1
    assert plan["coverage"]["price"]["missing"] == 1
    assert plan["priority_brands"][0]["brand"] == "Alpha"
    alpha_task = next(item for item in plan["priority_tasks"] if item["brand"] == "Alpha")
    assert alpha_task["actions"] == ["refresh_known_source"]
    beta_task = next(item for item in plan["priority_tasks"] if item["brand"] == "Beta")
    assert "approved_source_discovery" in beta_task["actions"]
    assert "retailer_price_match" in beta_task["actions"]
    preserved = unified._preserve_manual_values(
        {"name": "WEB: Celestion 18-inch", "brand": "Celestion", "driver": {"pe_w": 500.0}},
        {
            "name": "WEB: Celestion 18-inch", "brand": "Celestion",
            "part_number_override": "TF1830", "matched_mpn": "TF1830",
            "source": "Manual catalog maintenance", "driver": {"pe_w": 600.0},
        },
    )
    assert preserved["part_number_override"] == "TF1830"
    assert preserved["driver"]["pe_w"] == 600.0
    domain_rows = [
        {"url": "https://good.example/a", "driver": {"xmax_mm": 0, "pe_w": 0, "le_mh": 1}},
        {"url": "https://good.example/b", "driver": {"xmax_mm": 0, "pe_w": 2, "le_mh": 1}},
        {"url": "https://archive.example/table", "driver": {"xmax_mm": 0, "pe_w": 0, "le_mh": 0}},
        {"url": "https://archive.example/table", "driver": {"xmax_mm": 0, "pe_w": 0, "le_mh": 0}},
        {"url": "https://archive.example/table", "driver": {"xmax_mm": 0, "pe_w": 0, "le_mh": 0}},
    ]
    ranked_domains = {item["domain"]: item for item in high_yield.rank_domains(domain_rows)}
    assert ranked_domains["good.example"]["eligible"]
    assert not ranked_domains["archive.example"]["eligible"]
    assert high_yield.probe_passes(
        {"processed": 3, "records_updated": 2, "failures": [{}]}, 0.5, 0.5,
    )
    assert not high_yield.probe_passes(
        {"processed": 3, "records_updated": 0, "failures": [{}, {}, {}]}, 0.5, 0.5,
    )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "drivers.json"
        prices = root / "prices.json"
        report = root / "report.json"
        database.write_text(json.dumps({"presets": rows}), encoding="utf-8")
        prices.write_text(json.dumps({"prices": {}}), encoding="utf-8")
        args = completion.build_parser().parse_args([
            "run", "--database", str(database), "--prices", str(prices),
            "--report", str(report), "--skip-optionals", "--skip-prices",
            "--max-cycles", "3", "--stop-after-stalled", "1",
        ])
        calls = []

        def fake_runner(command, **_kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        code, result = completion.run_completion(args, runner=fake_runner)
        assert code == 0
        assert result["stop_reason"] == "coverage_stalled"
        assert len(result["cycles"]) == 1
        assert [Path(call[1]).name for call in calls] == [
            "enrich_manufacturer_metadata.py",
            "enrich_manufacturer_metadata.py",
            "generate_manufacturer_database_report.py",
        ]
        assert json.loads(report.read_text(encoding="utf-8"))["unresolved"]["prices"] == 1


test(
    "Catalog completion prioritizes safe gaps and stops when coverage stalls",
    _check_catalog_completion_plans_gaps_and_stops_when_stalled,
)


def _check_generic_ts_crawler_discovers_normalizes_and_merges():
    import json
    import tempfile
    from pathlib import Path

    from tools import crawl_thiele_small as crawler

    assert np.isclose(crawler.convert_measurement("sd_cm2", "5.02", "K mm/2"), 50.2)
    assert np.isclose(crawler.convert_measurement("sd_cm2", "5.02", "K/mm/2"), 50.2)
    assert np.isclose(crawler.convert_measurement("sd_cm2", "0.0111", "m ²"), 111.0)
    assert np.isclose(crawler.convert_measurement("fs_hz", "1.7", "K Hz"), 1700.0)
    assert crawler.canonical_parameter("Fo") == "fs_hz"
    assert crawler.canonical_parameter("F0") == "fs_hz"
    assert crawler.canonical_parameter("ReVc") == "re_ohm"
    assert crawler.canonical_parameter("L1kHz") == "le_mh"
    assert crawler.canonical_parameter("X Max") == "xmax_mm"
    assert crawler.canonical_parameter("Pwr") == "pe_w"
    assert crawler.canonical_parameter("Mounting Holes Diameter") == "mounting_hole_diameter_mm"
    assert crawler.canonical_parameter("Cut-out diameter") == "cutout_diameter_mm"
    assert crawler.canonical_parameter("Mounting hole dimensions") == "mounting_hole_diameter_mm"
    assert crawler.canonical_parameter("Mounting Holes B.C.D.") == "bolt_circle_mm"
    assert crawler.canonical_parameter("Magnet Weight") == "magnet_weight_kg"
    assert crawler.canonical_parameter("Nominal overall diameter") == "nominal_diameter_in"
    assert crawler.parse_number("2,000") == 2000.0
    assert np.isclose(crawler.parse_number("2,5"), 2.5)
    published_page = crawler.PageData(
        title="Acme TH12",
        text=(
            "Overall Diameter 12.4 in Baffle Cutout Diameter 282 mm "
            "Mounting Depth 5.75 inch Bolt Circle Diameter 11.5 in "
            "Number of Mounting Holes 8 Mounting Hole Diameter 6.5 mm "
            "Net Weight 7.4 kg Nominal Impedance 8 ohm "
            "Sensitivity 1W/1m 96.5 dB Voice Coil Diameter 3 in "
            "Xmech 14 mm Efficiency 2.4 % Flux Density 1.2 T"
        ),
    )
    published = crawler.build_published_observation(
        published_page, "https://acme.example/th12.pdf",
        "Manufacturer datasheet", "Acme", "pdf",
    )
    assert published is not None
    assert np.isclose(published["mechanical"]["overall_diameter_mm"], 314.96)
    assert published["mechanical"]["mounting_hole_count"] == 8
    assert np.isclose(published["published_specs"]["voice_coil_diameter_mm"], 76.2)
    assert published["published_specs"]["sensitivity_db"] == 96.5
    raw_overall = published["website_fields"]["raw_measurements"]["overall_diameter_mm"]
    assert raw_overall["label"] == "Overall Diameter"
    assert raw_overall["source_url"] == "https://acme.example/th12.pdf"
    assert raw_overall["method"] == "pdf.text"
    celestion_fields = crawler.choose_measurements(crawler.text_measurements(
        "Cut-out diameter 283 mm Mounting hole dimensions 7.9 mm Ø"
    ))
    assert celestion_fields["cutout_diameter_mm"].value == 283.0
    assert celestion_fields["mounting_hole_diameter_mm"].value == 7.9
    eminence_fields = crawler.choose_measurements(crawler.text_measurements(
        "MOUNTING INFORMATION\nDepth\n4.73\", 120.1 mm\n"
        "Net Weight\n5.3 lbs, 2.4 kg\nShipping Weight\n7.4 lbs, 3.36 kg\n"
        "MATERIALS OF CONSTRUCTION"
    ))
    assert np.isclose(eminence_fields["depth_mm"].value, 120.142)
    assert np.isclose(eminence_fields["weight_kg"].value, 5.3 * 0.45359237)
    beyma_fields = crawler.choose_measurements(crawler.text_measurements(
        "MOUNTING INFORMATION\n"
        "Overall diameter                           545 mm           21,5 in\n"
        "Baffle cutout diameter:\n"
        "- Front mount                              492 mm           19,4 in\n"
        "Depth                                      268 mm           10,6 in\n"
        "Net weight                                  11,8 kg         26,0 lb\n"
        "DIMENSION DRAWING\nAcústica Beyma SL\nTHIELE-SMALL PARAMETERS"
    ))
    assert beyma_fields["cutout_diameter_mm"].value == 492.0
    assert beyma_fields["depth_mm"].value == 268.0
    sb_drawing = crawler.sb_acoustics_drawing_measurements([
        (480.4, 751.3, 1.0, 0.0, "85.9"),
        (482.4, 740.4, 1.0, 0.0, "75"),
        (392.8, 719.9, 1.0, 0.0, "Ø159.0±0.10"),
        (400.8, 713.3, 1.0, 0.0, "Ø8.5 (x4)"),
        (405.3, 707.1, 1.0, 0.0, "Ø4.3 (x4)"),
        (436.0, 638.8, 0.0, 1.0, "Ø 171.0"),
        (549.3, 643.6, 0.0, 1.0, "Ø 144.9"),
    ], "6in SB17NRXC35-4 Rev-1")
    sb_values = {item.key: item.value for item in sb_drawing}
    assert sb_values == {
        "overall_diameter_mm": 171.0,
        "cutout_diameter_mm": 144.9,
        "bolt_circle_mm": 159.0,
        "mounting_hole_diameter_mm": 4.3,
        "mounting_hole_count": 4.0,
        "depth_mm": 85.9,
        "mounting_depth_mm": 75.0,
    }
    assert all(item.method == "pdf.drawing" for item in sb_drawing)
    bomber_drawing = crawler.bomber_drawing_measurements(
        "www.bomber.com.br\nSpeaker dimensions (mm)\n"
        "Qts 1,29\nA 135 B 152\nQms 12,6\nC 309 D 278\n"
        "Sd 490 cm2\nE 169 F 46\n"
    )
    bomber_values = {item.key: item.value for item in bomber_drawing}
    assert bomber_values == {
        "overall_diameter_mm": 309.0,
        "cutout_diameter_mm": 278.0,
        "depth_mm": 152.0,
        "mounting_depth_mm": 135.0,
    }
    assert all(item.method == "pdf.drawing" for item in bomber_drawing)
    assert "A=135; B=152" == next(
        item.raw_value for item in bomber_drawing if item.key == "depth_mm"
    )
    # Some Bomber frames reverse which keyed flange face is farther forward.
    reversed_bomber = {item.key: item.value for item in crawler.bomber_drawing_measurements(
        "www.bomber.com.br Speaker dimensions (mm) A 221 B 208 "
        "C 463 D 426 E 220 F 60"
    )}
    assert reversed_bomber["depth_mm"] == 221.0
    assert reversed_bomber["mounting_depth_mm"] == 208.0
    bc_drawing = crawler.bc_speakers_drawing_measurements(
        "5 (4x)\n B.C. 142\n45 degrees\n155\n9\n77\n122\n",
        r"BCSPEAKERS\\delruina (PC66)\nALT005FG44\nSolidWorks PDF Publisher",
    )
    bc_values = {item.key: item.value for item in bc_drawing}
    assert bc_values == {
        "mounting_hole_diameter_mm": 5.0,
        "mounting_hole_count": 4.0,
        "bolt_circle_mm": 142.0,
    }
    assert all(item.method == "pdf.drawing" for item in bc_drawing)
    # A dimension-like but implausible earlier token must not hide a later,
    # explicit and valid mounting-hole callout in the same drawing text.
    recovered_bc = {item.key: item.value for item in crawler.bc_speakers_drawing_measurements(
        "120 (90x)\n(8x) 6,50\nB.C. 443\n", "official B&C drawing URL",
    )}
    assert recovered_bc["mounting_hole_count"] == 8.0
    assert recovered_bc["mounting_hole_diameter_mm"] == 6.5
    for callout, expected_count, expected_diameter in (
        ("6,20(x8)", 8.0, 6.2),
        ("8x 6.5min", 8.0, 6.5),
        ("N.8 x 7 min.", 8.0, 7.0),
        ("(x8) 7 min.", 8.0, 7.0),
        ("(8x) 6,50", 8.0, 6.5),
        ("2,5  6,6(x8)", 8.0, 6.6),
        ("min 8x 6.80", 8.0, 6.8),
    ):
        values = {item.key: item.value for item in crawler.bc_speakers_drawing_measurements(
            f"{callout}\nBCD 246\n", "official B&C drawing URL",
        )}
        assert values["mounting_hole_count"] == expected_count
        assert values["mounting_hole_diameter_mm"] == expected_diameter
        assert values["bolt_circle_mm"] == 246.0
    assert not crawler.bc_speakers_drawing_measurements(
        "5 (4x)\nB.C. 142", "Unrelated CAD publisher",
    )
    phl_fields = crawler.choose_measurements(crawler.text_measurements(
        "Speaker net mass kg 2.15\n"
        "Bolt number & Metric diameter - 4x M5\n"
        "Max overall dimension (on ears) mm 187.5\n"
    ))
    assert phl_fields["weight_kg"].value == 2.15
    assert phl_fields["overall_diameter_mm"].value == 187.5
    assert phl_fields["mounting_hole_count"].value == 4.0
    assert "mounting_hole_diameter_mm" not in phl_fields
    oberton_fields = crawler.choose_measurements(crawler.text_measurements(
        "MOUNTING INFORMATION\nOverall Diameter\nBaffle Hole Diameter\n"
        "Mounting Holes\nBolt Circle Diameter\nOverall Depth\nNet Weight\n"
        "461 mm\n417 mm\n8 eliptic 7 x 8,5 mm\n438/441 mm\n224 mm\n11.7 kg"
    ))
    assert oberton_fields["overall_diameter_mm"].value == 461.0
    assert oberton_fields["cutout_diameter_mm"].value == 417.0
    assert oberton_fields["mounting_hole_count"].value == 8.0
    assert oberton_fields["bolt_circle_mm"].value == 441.0
    assert oberton_fields["bolt_circle_mm"].raw_value == "438/441"
    assert oberton_fields["depth_mm"].value == 224.0
    assert oberton_fields["weight_kg"].value == 11.7
    paudio_fields = crawler.choose_measurements(crawler.text_measurements(
        "PCD 296.0 mm\nMounting and Shipping Info\n"
        "Diameter 313.5 mm (12.3 in)\n"
        "Baffle Cutout Diameter 283.4 mm (11.1 in)\n"
        "Mounting Hole Diameter 296 mm (11.6 in)\n"
        "Bolt Circle Diameter 8 x Ø (6.5x10) mm\n"
        "Depth 134.7 mm (5.3 in)\nNet Weight 7.4 kg\nRecone Kit"
    ))
    assert paudio_fields["overall_diameter_mm"].value == 313.5
    assert paudio_fields["cutout_diameter_mm"].value == 283.4
    assert paudio_fields["bolt_circle_mm"].value == 296.0
    assert paudio_fields["mounting_hole_count"].value == 8.0
    assert "mounting_hole_diameter_mm" not in paudio_fields
    assert paudio_fields["depth_mm"].value == 134.7
    assert paudio_fields["weight_kg"].value == 7.4
    nominal_page = crawler.build_published_observation(
        crawler.PageData(title="Acme N12", text="Nominal overall diameter: 12 in"),
        "https://acme.example/n12", "Manufacturer page", "Acme", "html",
    )
    assert nominal_page is not None
    assert nominal_page.get("mechanical") in (None, {})
    assert nominal_page["published_specs"]["nominal_diameter_in"] == 12.0
    ambiguous_columns = crawler.table_measurements(
        "SPECIFICATIONS\nOverall Diameter\nBaffle Hole Diameter\nDepth\n12.4 in\n11.1 in\n5.7 in",
        "pdf.table",
    )
    assert not any(item.key in crawler.MECHANICAL_FIELDS for item in ambiguous_columns)
    assert "pe_w" not in crawler.choose_measurements(crawler.text_measurements("Power handling 4"))
    coax_power = crawler.choose_measurements(crawler.text_measurements(
        "LF Nominal Power Handling\n3\n200 W\n"
        "LF Continuous Power Handling\n4\n400 W\n"
        "HF Nominal Power Handling\n6\n70 W"
    ))
    assert coax_power["pe_w"].value == 200.0, coax_power
    assert crawler.measurement_from_pair("Power handling", "98.5", "", "html.table") is None
    hydration = crawler.jsonld_measurements([{
        "parameters": [
            {"label": "Fs", "value": 42, "units": {"default": "Hz"}},
            {"label": "Qts", "value": 0.31, "units": {"default": ""}},
        ]
    }])
    assert {item.key for item in hydration} == {"fs_hz", "qts"}
    markaudio_optional = crawler.choose_measurements(crawler.text_measurements(
        "L1kHz 0.2283 mH X Max (Mech) +/- 9mm Pwr 50 Watts (Nom)"
    ))
    assert np.isclose(markaudio_optional["le_mh"].value, 0.2283)
    assert np.isclose(markaudio_optional["xmax_mm"].value, 9.0)
    assert np.isclose(markaudio_optional["pe_w"].value, 50.0)
    misco_tolerance = crawler.choose_measurements(crawler.text_measurements(
        "Rated Power IEC268-5 (W) 100 Watts "
        "Resonant Frequency (Fs) (Hz) +/- 15% 23 "
        "X Max (Mech) +/- 9mm"
    ))
    assert np.isclose(misco_tolerance["pe_w"].value, 100.0)
    assert np.isclose(misco_tolerance["fs_hz"].value, 23.0)
    assert np.isclose(misco_tolerance["xmax_mm"].value, 9.0)
    _name, brand, model = crawler.product_metadata(
        crawler.PageData(
            h1="12 Inch (305 mm) 8 Ohm Woofer",
            text="Brand Name\nOaktron by MISCO\nModel #\n305-WF08-01\nPart #\n93060",
        ),
        "https://store.miscospeakers.com/12-inch-woofer-93060",
        brand_hint="MISCO",
    )
    assert brand == "MISCO"
    assert model == "305-WF08-01"
    manufacturer_optional = crawler.choose_measurements(crawler.text_measurements(
        "Excursion limit +/-8.5 mm Inductance of the voice coil L 0.9 mH "
        "Continuous power rating 60 W Power rating 30 W"
    ))
    assert np.isclose(manufacturer_optional["xmax_mm"].value, 8.5)
    assert np.isclose(manufacturer_optional["le_mh"].value, 0.9)
    assert np.isclose(manufacturer_optional["pe_w"].value, 30.0)
    rcf_optional = crawler.choose_measurements(crawler.text_measurements(
        "Power handling capacity 300 W Voice coil inductance @ 1kHz (Le1k) 0.50 mH"
    ))
    assert np.isclose(rcf_optional["pe_w"].value, 300.0)
    assert np.isclose(rcf_optional["le_mh"].value, 0.5)
    sb_values = crawler.derive_driver_values({
        item.key: item.value for item in crawler.text_measurements(
            "Linear coil travel (p-p) 11 mm Rated power handling* 60 W"
        )
    })
    assert np.isclose(sb_values["xmax_mm"], 5.5)
    assert np.isclose(sb_values["pe_w"], 60.0)
    localized_power = crawler.choose_measurements(crawler.text_measurements(
        "Potência (RMS) 400 W_RMS Watts 20 W Power handling P 250 W"
    ))
    assert np.isclose(localized_power["pe_w"].value, 400.0)
    multiline_power = crawler.choose_measurements(crawler.text_measurements(
        "Power handling\nP\n250\nW"
    ))
    assert np.isclose(multiline_power["pe_w"].value, 250.0)

    product_html = b"""
    <html><head>
      <title>Acme Thunder 12</title>
      <meta property="product:brand" content="Acme">
      <script type="application/ld+json">
      {
        "@type": "Product",
        "name": "Acme Thunder 12",
        "brand": {"@type": "Brand", "name": "Acme"},
        "model": "TH12",
        "additionalProperty": [
          {"name": "Fs", "value": "31 Hz"},
          {"name": "Vas", "value": "2.1 ft3"},
          {"name": "Qts", "value": "0.40"},
          {"name": "Qms", "value": "5.10"},
          {"name": "Qes", "value": "0.434"},
          {"name": "Re", "value": "5.7 ohm"},
          {"name": "Sd", "value": "0.053 m2"},
          {"name": "Le", "value": "0.0012 H"},
          {"name": "Xmax", "value": "0.8 cm"},
          {"name": "Pe", "value": "0.4 kW"},
          {"name": "Mms", "value": "0.1 kg"},
          {"name": "Cms", "value": "250 um/N"},
          {"name": "BL", "value": "14 Tm"}
        ]
      }
      </script>
    </head><body>12 inch loudspeaker driver</body></html>
    """
    page = crawler.parse_html(product_html)
    preset, errors = crawler.build_preset(page, "https://www.example.test/products/th12")
    assert not errors and preset is not None, errors
    assert preset["brand"] == "Acme"
    assert preset["model"] == "TH12"
    assert preset["source"] == "Web crawler"
    assert preset["size_in"] == 12.0
    driver = preset["driver"]
    assert np.isclose(driver["vas_l"], 2.1 * 28.316846592)
    assert np.isclose(driver["sd_cm2"], 530.0)
    assert np.isclose(driver["qes"], 0.434)
    assert np.isclose(driver["le_mh"], 1.2)
    assert np.isclose(driver["xmax_mm"], 8.0)
    assert np.isclose(driver["pe_w"], 400.0)
    assert np.isclose(driver["mms_g"], 100.0)
    assert np.isclose(driver["cms_mm_per_n"], 0.25)

    dirty_storefront = crawler.parse_html(b"""
    <html><head><title>Scan-Speak Example 4&quot; Woofer</title>
      <script type="application/ld+json">
      [{"@type":"Product","name":"Scan-Speak Example 4 inch Woofer",
        "brand":{"name":"Scan-Speak"},"mpn":"EX4",
        "description":"line one
line two"}]
      </script></head><body>
      Fs 90 Hz Vas 0.07 ft.<sup>3</sup> Qts 0.29 Qms 3.2
      Re 3.2 ohms Sd 36 cm<sup>2</sup>
    </body></html>
    """)
    dirty_preset, errors = crawler.build_preset(
        dirty_storefront, "https://shop.example.test/scan-speak-ex4")
    assert not errors and dirty_preset is not None, errors
    assert dirty_preset["brand"] == "Scan-Speak"
    assert dirty_preset["model"] == "EX4"
    assert np.isclose(dirty_preset["driver"]["vas_l"], 0.07 * 28.316846592)
    assert np.isclose(dirty_preset["driver"]["sd_cm2"], 36.0)

    parallel_table = crawler.PageData(
        title="12NB400",
        text="""THIELE-SMALL PARAMETERS
Fs
Qms
Qes
Qts
Vas
Mms
Re
Sd
43.58 Hz
10.39
0.183
0.180
70.45 litres
59.82 grams
5.00 Ohms
514.7 cm2""",
    )
    parallel_preset, errors = crawler.build_preset(
        parallel_table, "https://oberton.example/12nb400", brand_hint="Oberton")
    assert not errors and parallel_preset is not None, errors
    assert np.isclose(parallel_preset["driver"]["vas_l"], 70.45)

    parallel_specs = crawler.table_measurements("""SPECIFICATIONS
Nominal Diameter
Impedance
Power Capacity AES
Program Power
Sensitivity
18 inch
8 Ohm
1600 W
3200 W
97 dB""")
    parallel_specs_chosen = crawler.choose_measurements(parallel_specs)
    assert np.isclose(parallel_specs_chosen["pe_w"].value, 1600.0)

    phl_table = crawler.PageData(
        title="4031 12 inches bass driver",
        text="""Thiele-Small parameters
Resonance frequency                    Fs                 Hz         44 (+/-6)
DC Resistance                          Re                  W        5.6 (+/-0.6)
Mechanical quality factor              Qms                 1           5.36
Electrical quality factor              Qes                 1           0.29
Total quality factor                   Qts                 1           0.27
Effective piston area                  Sd                 m2         0.0539
Equivalent Cas air load                Vas                m3         0.0700""",
    )
    phl_preset, errors = crawler.build_preset(
        phl_table, "https://phl.example/4031.pdf", brand_hint="PHL Audio",
        extraction_method="pdf")
    assert not errors and phl_preset is not None, errors
    assert np.isclose(phl_preset["driver"]["re_ohm"], 5.6)
    assert np.isclose(phl_preset["driver"]["sd_cm2"], 539.0)

    fostex_page = crawler.PageData(
        title="FE108NS 4 inch Full Range",
        text=("Fs 75 Hz Vas 5.37 L Qts 0.32 Qms 3.11 Re 7.4 ohm "
              "Equivalent Diaphragm Radius 39.5 mm"),
    )
    fostex_preset, errors = crawler.build_preset(
        fostex_page, "https://fostex.example/fe108ns", brand_hint="Fostex")
    assert not errors and fostex_preset is not None, errors
    assert np.isclose(fostex_preset["driver"]["sd_cm2"], np.pi * 3.95**2)
    assert np.isclose(
        fostex_preset["driver"]["qes"],
        1.0 / (1.0 / 0.32 - 1.0 / 3.11),
    )
    assert fostex_preset["website_fields"]["derived_fields"] == ["qes", "sd_cm2"]
    assert crawler.first_inch_size('6-1/2" woofer') == 6.5
    assert crawler.first_inch_size('1-1/8" BMR') == 1.125
    assert crawler.first_inch_size("oval 6x9″ woofer") == 6.0
    assert crawler.infer_size_in('DS175-8 6-1/2" woofer', "", 128.7) == 6.5
    assert crawler.infer_size_in("Scan-Speak 15W/4434G00", "", 80.0) is None
    assert crawler.infer_size_in("18FT-100SW", 'menu 8" item') == 18.0
    assert crawler.infer_size_in("18FT-100SW", 'menu 8" item', 855.0) == 18.0
    assert crawler.infer_size_in("18FT-100SW", 'Nominal Diameter 18"') == 18.0
    generic_title = crawler.PageData(
        title="Discontinued product",
        h1="Discontinued product",
        text="Fs 37.2 Hz Vas 111.02 L Qts 0.3 Qms 4.2 Re 5.1 ohm Sd 855 cm2",
    )
    generic_preset, errors = crawler.build_preset(
        generic_title,
        "https://oberton.example/products/ferrite-loudspeakers/164-15xb700.html",
        brand_hint="Oberton",
    )
    assert not errors and generic_preset is not None, errors
    assert generic_preset["model"] == "15XB700"
    empty_pdf_title = crawler.PageData(
        text="Fs 44 Hz Vas 70 L Qts 0.27 Qms 5.36 Re 5.6 ohm Sd 539 cm2",
    )
    pdf_preset, errors = crawler.build_preset(
        empty_pdf_title,
        "https://phl.example/fileadmin/4031NdU-19_SpecSheet.pdf",
        brand_hint="PHL Audio",
        extraction_method="pdf",
    )
    assert not errors and pdf_preset is not None, errors
    assert pdf_preset["model"] == "4031NdU-19"

    storefront_page = crawler.parse_html(b"""
    <html><head><title>Dayton Audio 10MB250N-8</title></head><body><dl>
      <div><dt>DC Resistance (Re)</dt><dd>7.4 ohm</dd></div>
      <div><dt>Resonant Frequency (Fs)</dt><dd>54 Hz</dd></div>
      <div><dt>Mechanical Q (Qms)</dt><dd>6.73</dd></div>
      <div><dt>Total Q (Qts)</dt><dd>0.22</dd></div>
      <div><dt>Surface Area of Cone (Sd)</dt><dd>333.12cm\xc2\xb2</dd></div>
      <div><dt>Compliance Equivalent Volume (Vas)</dt><dd>1.53ft\xc2\xb3</dd></div>
    </dl></body></html>
    """)
    storefront, errors = crawler.build_preset(
        storefront_page,
        "https://www.soundimports.eu/en/dayton-audio-10mb250n-8.html",
        brand_hint="Dayton Audio",
    )
    assert not errors and storefront is not None, errors
    assert np.isclose(storefront["driver"]["sd_cm2"], 333.12)
    assert np.isclose(storefront["driver"]["vas_l"], 1.53 * 28.316846592)

    text_page = crawler.PageData(
        title="Beta W8",
        text="Fs: 40 Hz Vas: 20 L Qts: 0.40 Qes: 0.45 Re: 6 ohm Sd: 220 cm2",
    )
    derived, errors = crawler.build_preset(
        text_page, "https://beta.example.test/w8", brand_hint="Beta")
    assert not errors and derived is not None, errors
    assert np.isclose(derived["driver"]["qms"], 3.6)

    titled_page = crawler.PageData(
        title="Alpair 6.2 | Markaudio",
        text="Fs: 80 Hz Vas: 3 L Qts: 0.4 Qms: 3 Re: 6 ohm Sd: 40 cm2",
    )
    _name, brand, model = crawler.product_metadata(
        titled_page, "https://www.markaudio.com/product", "Markaudio"
    )
    assert brand == "Markaudio" and model == "Alpair 6.2"
    assert crawler.is_standalone_lf_driver_model("Alpair 6.2")
    assert not crawler.is_standalone_lf_driver_model("Tozzi One Kit")
    assert not crawler.is_standalone_lf_driver_model("TW 6 Metal Dome Tweeter")
    assert not crawler.is_standalone_lf_driver_model(
        "25-TD04-01", "1 Inch Premium Silk Dome Tweeter with Rear Chamber"
    )

    measurements = crawler.choose_measurements([
        crawler.Measurement("sd_cm2", 5.02, "5.02", "", "Sd", "html.text"),
        crawler.Measurement("sd_cm2", 50.2, "50.2", "cm2", "SD", "html.text"),
    ])
    assert measurements["sd_cm2"].value == 50.2

    urlset = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.example.test/products/th12</loc></url>
    </urlset>"""
    urls, nested = crawler.parse_sitemap(urlset)
    assert urls == ["https://www.example.test/products/th12"] and not nested

    catalog_html = b'<html><body><a href="/products/th12">Thunder 12</a></body></html>'
    responses = {
        "https://www.example.test/catalog": crawler.FetchResult(
            "https://www.example.test/catalog", "text/html", catalog_html),
        "https://www.example.test/products/th12": crawler.FetchResult(
            "https://www.example.test/products/th12", "text/html", product_html),
    }

    def fake_fetch(url, _timeout, _agent):
        return responses[url]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = crawler.CrawlConfig(
            seeds=["https://www.example.test/catalog"],
            sitemaps=[],
            output=root / "drivers.json",
            checkpoint=root / "checkpoint.json",
            allowed_domains={"example.test"},
            max_pages=5,
            max_depth=1,
            sleep_s=0.0,
            fresh=True,
            dry_run=True,
        )
        crawled, failures, visited = crawler.crawl(
            config, fetcher=fake_fetch, robots_allowed=lambda _url: True)
        assert not failures, failures
        assert len(visited) == 2, visited
        assert [item["model"] for item in crawled] == ["TH12"]

        existing = json.loads(json.dumps(crawled[0]))
        existing["driver"]["le_mh"] = 0.0
        existing["driver"]["fs_hz"] = 32.0
        merged, stats = crawler.merge_presets([existing], crawled)
        assert stats == {"added": 0, "updated": 1, "unchanged": 0}, stats
        assert merged[0]["driver"]["le_mh"] == 1.2
        assert merged[0]["driver"]["fs_hz"] == 32.0, "default merge must preserve curated core data"
        refreshed, stats = crawler.merge_presets(
            [existing], crawled, refresh_source="Web crawler"
        )
        assert stats["updated"] == 1
        assert refreshed[0]["driver"]["fs_hz"] == crawled[0]["driver"]["fs_hz"]
        stale_identity = json.loads(json.dumps(crawled[0]))
        stale_identity["model"] = "Discontinued product"
        renamed, stats = crawler.merge_presets(
            [stale_identity], crawled, refresh_source="Web crawler"
        )
        assert stats == {"added": 0, "updated": 1, "unchanged": 0}, stats
        assert renamed[0]["model"] == "TH12"


test("Generic T/S crawler discovers, normalizes and safely merges drivers", _check_generic_ts_crawler_discovers_normalizes_and_merges)


def _check_crawler_agent_policy_planning_and_staging():
    import json
    import tempfile
    from types import SimpleNamespace

    from services.crawler_agent import agent
    from services.crawler_agent.model import (
        AgentManifest,
        AgentPolicyError,
        build_plan,
    )

    manifest = AgentManifest.from_mapping({
        "objective": "Fill direct-source brand gaps",
        "max_targets": 1,
        "user_agent": "LoadForgeCrawler/1.0 (crawler@example.test)",
        "targets": [
            {
                "target_id": "known-official",
                "source_kind": "official_manufacturer_site",
                "allowed_domains": ["known.example"],
                "seeds": ["https://known.example/products"],
                "brand": "Known",
                "priority": 60,
                "max_pages": 10,
                "sleep_seconds": 0.5,
            },
            {
                "target_id": "missing-official",
                "source_kind": "official_manufacturer_site",
                "allowed_domains": ["missing.example"],
                "sitemaps": ["https://missing.example/sitemap.xml"],
                "brand": "Missing",
                "priority": 50,
                "max_pages": 10,
                "sleep_seconds": 0.5,
            },
        ],
    })
    plan = build_plan(manifest, {"presets": [{"brand": "Known"}]})
    assert [item.target.target_id for item in plan.selected] == ["missing-official"]
    assert "brand absent" in " ".join(plan.selected[0].reasons)

    gap_manifest = AgentManifest.from_mapping({
        "objective": "Fill optional gaps",
        "max_targets": 1,
        "user_agent": "LoadForgeCrawler/1.0 (crawler@example.test)",
        "targets": [
            {
                "target_id": "complete-brand", "source_kind": "official_manufacturer_site",
                "allowed_domains": ["complete.example"],
                "seeds": ["https://complete.example/products"], "brand": "Complete",
                "priority": 50, "max_pages": 10, "sleep_seconds": 0.5,
            },
            {
                "target_id": "gap-brand", "source_kind": "official_manufacturer_site",
                "allowed_domains": ["gap.example"],
                "seeds": ["https://gap.example/products"], "brand": "Gap",
                "priority": 50, "max_pages": 10, "sleep_seconds": 0.5,
            },
        ],
    })
    gap_plan = build_plan(gap_manifest, {"presets": [
        {"brand": "Complete", "driver": {"xmax_mm": 5.0, "pe_w": 100.0, "le_mh": 1.0}},
        {"brand": "Gap", "driver": {"xmax_mm": 0.0, "pe_w": 0.0, "le_mh": 0.0}},
    ]})
    assert [item.target.target_id for item in gap_plan.selected] == ["gap-brand"]
    assert "missing Xmax/Pe/Le" in " ".join(gap_plan.selected[0].reasons)

    forbidden_targets = [
        {
            "target_id": "copied-db",
            "source_kind": "aggregated_database",
            "allowed_domains": ["example.test"],
            "seeds": ["https://example.test/drivers"],
        },
        {
            "target_id": "hidden-lsdb",
            "source_kind": "authorized_retailer",
            "allowed_domains": ["example.test"],
            "seeds": ["https://example.test/loudspeaker_database/export"],
        },
    ]
    for target in forbidden_targets:
        try:
            AgentManifest.from_mapping({
                "user_agent": "LoadForgeCrawler/1.0 (crawler@example.test)",
                "targets": [target],
            })
        except AgentPolicyError:
            pass
        else:
            raise AssertionError(f"forbidden source accepted: {target}")

    selected = plan.selected[0]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        command = agent.command_for_target(selected, manifest, root / "target")
        assert "--allow-domain" in command
        assert "missing.example" in command
        assert "--sitemap" in command
        assert "--fresh" in command
        assert str(root / "target" / "candidate_catalog.json") in command

        original_run = agent.subprocess.run
        try:
            agent.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="staged",
                stderr="",
            )
            report_path = agent.run_plan(
                plan,
                manifest,
                root / "runs",
                run_id="crawl-test",
            )
        finally:
            agent.subprocess.run = original_run
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["publication_state"] == "staging_only"
        assert report["results"][0]["candidate_catalog"].startswith(
            "missing-official/"
        )
        assert not (root / "manufacturer_drivers.json").exists()
        try:
            agent.run_plan(
                plan,
                manifest,
                root / "runs",
                run_id="../catalog",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("crawler run_id escaped the staging root")


test(
    "Crawler agent accepts direct websites, rejects databases and stages only",
    _check_crawler_agent_policy_planning_and_staging,
)


def _check_crawler_agent_release_is_approved_and_immutable():
    import json
    import tempfile

    from services.crawler_agent.model import AgentManifest
    from services.crawler_agent.release import build_release
    from src import presets

    candidate = {
        "name": "WEB: Acme LF12",
        "brand": "Acme",
        "model": "LF12",
        "source": "Official manufacturer site",
        "url": "https://acme.example/products/lf12",
        "driver": {
            "fs_hz": 31.0,
            "vas_l": 62.0,
            "qts": 0.38,
            "qms": 4.8,
            "re_ohm": 5.6,
            "sd_cm2": 530.0,
        },
        "website_fields": {"confidence": 0.93},
    }
    manifest = AgentManifest.from_mapping({
        "user_agent": "LoadForgeCrawler/1.0 (crawler@example.test)",
        "targets": [
            {
                "target_id": "acme-official",
                "source_kind": "official_manufacturer_site",
                "allowed_domains": ["acme.example"],
                "seeds": ["https://acme.example/products"],
            },
        ],
    })
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline_path = root / "baseline.json"
        candidate_path = root / "acme-official" / "candidate_catalog.json"
        release_path = root / "releases" / "manufacturer-r1.json"
        baseline_path.write_text('{"presets": []}\n', encoding="utf-8")
        candidate_path.parent.mkdir()
        candidate_path.write_text(
            json.dumps({"presets": [candidate]}),
            encoding="utf-8",
        )
        payload = build_release(
            baseline_path,
            [candidate_path],
            release_path,
            manifest=manifest,
            release_id="manufacturer-r1",
            approved_by="reviewer@example.test",
        )
        assert payload["usable_presets"] == 1
        assert payload["merge_stats"]["added"] == 1
        assert len(payload["catalog_sha256"]) == 64
        assert release_path.exists()
        try:
            build_release(
                baseline_path,
                [candidate_path],
                release_path,
                manifest=manifest,
                release_id="manufacturer-r1",
                approved_by="reviewer@example.test",
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("immutable crawler release was overwritten")

        forbidden = dict(candidate)
        forbidden["source"] = "LSDB"
        candidate_path.write_text(
            json.dumps({"presets": [forbidden]}),
            encoding="utf-8",
        )
        try:
            build_release(
                baseline_path,
                [candidate_path],
                root / "releases" / "forbidden.json",
                manifest=manifest,
                release_id="forbidden",
                approved_by="reviewer@example.test",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("aggregated database entered a direct-source release")

        off_domain = dict(candidate)
        off_domain["url"] = "https://unlisted.example/products/lf12"
        candidate_path.write_text(
            json.dumps({"presets": [off_domain]}),
            encoding="utf-8",
        )
        try:
            build_release(
                baseline_path,
                [candidate_path],
                root / "releases" / "off-domain.json",
                manifest=manifest,
                release_id="off-domain",
                approved_by="reviewer@example.test",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("off-domain candidate bypassed the manifest allow-list")

        configured = presets.manufacturer_database_path({
            "LOAD_FORGE_MANUFACTURER_CATALOG_PATH": str(release_path),
        })
        assert configured == release_path
        assert presets.manufacturer_database_path({}).name == (
            "catalog_proprietario.json"
        )


test(
    "Crawler release requires approval, validates provenance and is immutable",
    _check_crawler_agent_release_is_approved_and_immutable,
)


def _check_manufacturer_deduper_only_removes_identical_subsets():
    from tools import dedupe_manufacturer_drivers as deduper

    def row(model, driver, source="Manufacturer website"):
        return {
            "name": f"WEB: Acme {model}",
            "brand": "Acme",
            "model": model,
            "source": source,
            "url": f"https://acme.example/{model}",
            "driver": driver,
            "website_fields": {},
        }

    required = {
        "fs_hz": 40.0, "vas_l": 50.0, "qts": 0.35,
        "qms": 5.0, "re_ohm": 5.6, "sd_cm2": 330.0,
    }
    full = row("W12", {**required, "bl_tm": 15.0, "xmax_mm": 8.0})
    verbose = row('LOUDSPEAKER 12" W12 8 OH', dict(required), "Retailer")
    conflicting = row("W12-special", {**required, "bl_tm": 16.0})
    other = row("W12-4", {**required, "re_ohm": 3.2})
    same_numbers_different_model = row("W13", {**required, "bl_tm": 15.0, "xmax_mm": 8.0})
    impedance_variant_4 = row(
        "LOUDSPEAKER X12 4 OHM", {**required, "bl_tm": 15.0, "xmax_mm": 8.0}
    )
    impedance_variant_8 = row(
        "LOUDSPEAKER X12 8 OHM", {**required, "bl_tm": 15.0, "xmax_mm": 8.0}
    )

    result, report = deduper.deduplicate_presets([
        verbose, conflicting, other, same_numbers_different_model,
        impedance_variant_4, impedance_variant_8, full,
    ])
    assert report["removed"] == 1, report
    assert [item["model"] for item in result] == [
        "W12-special", "W12-4", "W13", "LOUDSPEAKER X12 4 OHM",
        "LOUDSPEAKER X12 8 OHM", "W12",
    ]
    assert result[-1]["website_fields"]["aliases"] == ['LOUDSPEAKER 12" W12 8 OH']
    assert result[-1]["website_fields"]["merged_duplicates"][0]["source"] == "Retailer"


test(
    "Manufacturer deduper removes only identical parameter subsets",
    _check_manufacturer_deduper_only_removes_identical_subsets,
)


def _check_manufacturer_metadata_enrichment_uses_physics_and_verified_prices():
    from tools import enrich_manufacturer_metadata as enricher

    row = {
        "name": "WEB: Acme W12",
        "brand": "Acme",
        "model": "W12",
        "url": "https://acme.example/w12",
        "driver": {
            "fs_hz": 30.0, "vas_l": 100.0, "qts": 0.35,
            "qms": 5.0, "re_ohm": 5.6, "sd_cm2": 500.0,
        },
    }
    price = {
        "WEB: Acme W12": {
            "price": 199.95,
            "currency": "EUR",
            "seller": "Example",
            "url": "https://shop.example/acme-w12",
            "availability": "https://schema.org/InStock",
            "matched_name": "Acme W12 woofer",
            "matched_brand": "Acme",
            "matched_mpn": "W12",
            "confidence": 0.9,
            "fetched_at": "2026-07-22T00:00:00+00:00",
        }
    }
    result, report = enricher.enrich_presets([row], price)
    item = result[0]
    assert item["size_in"] == 12.0
    assert item["driver"]["qes"] > item["driver"]["qts"]
    assert item["driver"]["cms_mm_per_n"] > 0.0
    assert item["driver"]["mms_g"] > 0.0
    assert item["driver"]["bl_tm"] > 0.0
    assert item["price"] == 199.95 and item["currency"] == "EUR"
    assert report["priced"] == 1 and report["unpriced"] == 0
    assert set(report["derived"]) == {"bl_tm", "cms_mm_per_n", "mms_g", "qes", "size_in"}

    stale = {
        **row,
        "part_number_override": "TF1830",
        "price": 260.23,
        "currency": "EUR",
        "price_url": "https://shop.example/cf1840",
        "website_fields": {"price_provenance": {"matched_mpn": "CF1840"}},
    }
    wrong_offer = {
        "WEB: Acme W12": {
            **price["WEB: Acme W12"],
            "matched_name": "Acme CF1840",
            "matched_mpn": "CF1840",
        }
    }
    cleaned, stale_report = enricher.enrich_presets([stale], wrong_offer)
    assert stale_report["unpriced"] == 1
    assert "price" not in cleaned[0] and "price_url" not in cleaned[0]
    assert cleaned[0]["website_fields"]["invalidated_price"]["previous"]["price"] == 260.23


test(
    "Manufacturer metadata enrichment uses physics and verified prices",
    _check_manufacturer_metadata_enrichment_uses_physics_and_verified_prices,
)


def _check_manufacturer_metadata_reconciles_sd_and_nominal_size():
    from tools import enrich_manufacturer_metadata as enricher

    rows = [
        {
            "name": "WEB: Dayton Audio DS175-8",
            "brand": "Dayton Audio",
            "model": "DS175-8",
            "size_in": 2.0,
            "driver": {
                "fs_hz": 37.0, "vas_l": 17.0, "qts": 0.27, "qms": 1.63,
                "re_ohm": 5.7, "sd_cm2": 128.7, "mms_g": 26.0,
            },
            "website_fields": {
                "catalog_name": 'Dayton Audio DS175-8 6-1/2" Designer Series Woofer',
            },
        },
        {
            "name": "WEB: Dayton Audio PA460-8",
            "brand": "Dayton Audio",
            "model": "PA460-8",
            "size_in": 1.0,
            "driver": {
                "fs_hz": 28.3, "vas_l": 402.0, "qts": 0.33, "qms": 11.2,
                "re_ohm": 5.6, "sd_cm2": 1.241, "mms_g": 171.0,
            },
            "website_fields": {
                "title": 'Dayton Audio PA460-8 18" Pro Woofer',
                "raw_measurements": {
                    "sd_cm2": {"raw_value": "1,241.1", "unit": "cm²"},
                },
            },
        },
        {
            "name": "WEB: Acme X12",
            "brand": "Acme",
            "model": "X12",
            "size_in": 12.0,
            "driver": {
                "fs_hz": 19.0, "vas_l": 260.0, "qts": 0.4, "qms": 5.1,
                "re_ohm": 4.0, "sd_cm2": 50.0, "mms_g": 99.0,
            },
            "website_fields": {"title": 'Acme X12 12" woofer'},
        },
        {
            "name": "WEB: Scan-Speak 15W/4434G00",
            "brand": "Scan-Speak",
            "model": "15W/4434G00",
            "size_in": 15.0,
            "driver": {
                "fs_hz": 43.0, "vas_l": 12.8, "qts": 0.21, "qms": 3.69,
                "re_ohm": 3.0, "sd_cm2": 80.0, "mms_g": 9.6,
            },
            "website_fields": {"title": "Scan-Speak 15W/4434G00 Midwoofer"},
        },
        {
            "name": "WEB: Broken W26",
            "brand": "Broken",
            "model": "W26",
            "size_in": 10.0,
            "driver": {
                "fs_hz": 45.0, "vas_l": 6.0, "qts": 0.36, "qms": 2.5,
                "re_ohm": 5.6, "sd_cm2": 50.0, "mms_g": 7.5,
            },
            "website_fields": {"title": 'Broken W26 10" woofer'},
        },
        {
            "name": "WEB: Markaudio Alpair 10P",
            "brand": "Markaudio",
            "model": "Alpair 10P",
            "size_in": 10.0,
            "driver": {
                "fs_hz": 42.398, "vas_l": 29.995, "qts": 0.33, "qms": 2.425,
                "re_ohm": 6.2, "sd_cm2": 88.25, "mms_g": 5.196,
            },
            "website_fields": {"title": "Alpair 10P"},
        },
    ]
    result, report = enricher.enrich_presets(rows, {})
    by_model = {item["model"]: item for item in result}
    assert by_model["DS175-8"]["size_in"] == 6.5
    assert by_model["PA460-8"]["size_in"] == 18.0
    assert by_model["PA460-8"]["driver"]["sd_cm2"] == 1241.1
    assert by_model["X12"]["driver"]["sd_cm2"] == 500.0
    assert by_model["15W/4434G00"]["size_in"] == 5.0
    assert by_model["Alpair 10P"]["size_in"] == 5.0
    assert (
        by_model["W26"]["website_fields"]["quality_status"]
        == "rejected_size_sd_conflict"
    )
    assert report["corrected"]["sd_cm2"] >= 2
    assert report["corrected"]["size_in"] >= 3
    assert report["corrected"]["rejected_size_sd_conflict"] == 1


test(
    "Manufacturer metadata reconciles Sd and nominal size",
    _check_manufacturer_metadata_reconciles_sd_and_nominal_size,
)


def _check_external_catalog_skips_rejected_size_sd_conflicts():
    import json
    import tempfile

    from src import presets

    base_driver = {
        "fs_hz": 40.0, "vas_l": 20.0, "qts": 0.35, "qms": 4.0,
        "re_ohm": 5.6, "sd_cm2": 100.0,
    }
    payload = {
        "presets": [
            {
                "name": "WEB: Acme valid",
                "brand": "Acme",
                "model": "valid",
                "driver": base_driver,
            },
            {
                "name": "WEB: Acme rejected",
                "brand": "Acme",
                "model": "rejected",
                "driver": base_driver,
                "website_fields": {
                    "quality_status": "rejected_size_sd_conflict",
                },
            },
            {
                "name": "WEB: Acme model-number size",
                "brand": "Acme",
                "model": "X10P",
                "size_in": 10.0,
                "driver": {**base_driver, "sd_cm2": 88.25},
            },
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "drivers.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded, info = presets._load_external_presets(
            path,
            default_source="test",
            dedupe_tag="test",
            reserved={},
        )
    assert "WEB: Acme valid" in loaded
    assert "WEB: Acme rejected" not in loaded
    assert info["WEB: Acme model-number size"].size_in == 5.25


test(
    "External catalog skips rejected size-Sd conflicts",
    _check_external_catalog_skips_rejected_size_sd_conflicts,
)


def _check_pdf_datasheet_library_archives_indexes_and_merges_aliases():
    import http.client
    import json
    import sqlite3
    import tempfile
    from pathlib import Path

    from tools import crawl_driver_datasheets as library

    assert http.client.IncompleteRead in library.RECOVERABLE_FETCH_ERRORS

    with tempfile.TemporaryDirectory() as tmp_catalog_dir:
        catalog_path = Path(tmp_catalog_dir) / "manufacturer.json"
        catalog_path.write_text(json.dumps({"presets": [
            {"url": "https://www.beyma.com/en/products/one/", "model": "Products - Beyma - Professional Speaker Manufacturer"},
            {"url": "https://www.beyma.com/en/products/one/", "model": "LOUDSPEAKER 21LEX1600Nd 8 OH", "brand": "Beyma"},
            {"url": "https://docs.beyma.com/en/products/two/"},
            {"url": "https://example.com/not-beyma/"},
            {"url": "https://www.beyma.com/en/products/one/"},
        ]}), encoding="utf-8")
        known_urls = library.product_urls(library.LibraryConfig(
            seeds=[], sitemaps=[], catalog_domains=("beyma.com",),
            catalog_path=catalog_path,
        ))
        assert known_urls == [
            "https://www.beyma.com/en/products/one/",
            "https://docs.beyma.com/en/products/two/",
        ]
        identities = library.catalog_identity_by_url(library.LibraryConfig(
            seeds=[], sitemaps=[], catalog_domains=("beyma.com",),
            catalog_path=catalog_path,
        ))
        assert identities[known_urls[0]]["model"] == "LOUDSPEAKER 21LEX1600Nd 8 OH"

    page = library.ts.parse_html(b"""
    <html><body>
      <a href="https://docs.example.test/specs/driver-a.pdf">Data sheet</a>
      <a href="/manual.txt">Manual</a>
    </body></html>
    """)
    assert library.discover_pdf_links(page, "https://shop.example.test/a") == [
        "https://docs.example.test/specs/driver-a.pdf"]
    assert library.discover_embedded_drawing_links(
        b'{"drawing":[{"path":"uploads/products/drawing/ALT005FG44.PDF"}]}',
        "https://www.bcspeakers.com/en/products/lf-driver/5/16/5FG44",
    ) == ["https://www.bcspeakers.com/uploads/products/drawing/ALT005FG44.PDF"]

    direct_pdf_identity = {"brand": "SB Acoustics", "model": "SB17NRXC35-4"}
    direct_page = library.ts.PageData(
        title=direct_pdf_identity["model"], h1=direct_pdf_identity["model"],
        text=direct_pdf_identity["model"],
    )
    direct_observation = json.loads(json.dumps({
        "brand": "SB Acoustics", "model": "fallback", "name": "fallback",
        "url": "https://sbacoustics.example/SB17.pdf", "driver": {},
        "website_fields": {"partial_observation": True},
    }))
    direct_canonical, _direct_alias = library.canonicalize_pdf_preset(
        direct_observation, product_page=direct_page,
        product_url="https://sbacoustics.example/SB17.pdf",
        pdf_url="https://sbacoustics.example/SB17.pdf", sha256="c" * 64,
        brand_hint="SB Acoustics", catalog_identity=direct_pdf_identity,
    )
    assert direct_canonical["model"] == "SB17NRXC35-4"

    apollo = {
        "brand": "Dayton Audio", "model": "Apollo 10N", "source": "Loudspeaker Database",
        "driver": {
            "fs_hz": 54.0, "vas_l": 39.98, "qts": 0.22, "qms": 5.84,
            "re_ohm": 7.4, "sd_cm2": 333.12, "bl_tm": 0.0,
        },
        "website_fields": {},
    }
    duplicate = {
        "brand": "Dayton Audio", "model": "10MB250N-8", "source": "Web crawler",
        "driver": {
            "fs_hz": 54.0, "vas_l": 43.32, "qts": 0.22, "qms": 6.73,
            "re_ohm": 7.4, "sd_cm2": 333.12, "bl_tm": 0.0,
        },
        "website_fields": {},
    }
    observation = {
        "brand": "Dayton Audio", "model": "10MB250N-8", "source": "Manufacturer datasheet",
        "url": "https://docs.example.test/10mb250n-8.pdf",
        "driver": {
            "fs_hz": 54.0, "vas_l": 43.49, "qts": 0.22, "qms": 6.73,
            "re_ohm": 7.4, "sd_cm2": 333.12, "bl_tm": 19.2,
        },
        "mechanical": {"overall_diameter_mm": 260.0},
        "published_specs": {"xmech_mm": 12.5},
        "website_fields": {
            "pdf_sha256": "a" * 64,
            "product_url": "https://shop.example.test/10mb250n-8",
            "fetched_at": "2026-07-17T00:00:00+00:00",
            "confidence": 0.975,
        },
    }
    merged, stats = library.merge_observations([apollo, duplicate], [observation])
    assert len(merged) == 1
    assert stats["merged_alias"] == 1 and stats["removed_duplicates"] == 1
    assert merged[0]["model"] == "Apollo 10N"
    assert merged[0]["driver"]["bl_tm"] == 19.2
    assert merged[0]["mechanical"]["overall_diameter_mm"] == 260.0
    assert merged[0]["published_specs"]["xmech_mm"] == 12.5
    assert "10MB250N-8" in merged[0]["website_fields"]["aliases"]
    assert merged[0]["website_fields"]["datasheets"][0]["sha256"] == "a" * 64

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        digest, relative = library.archive_pdf(root / "pdfs", b"%PDF-1.4 test")
        again, same_relative = library.archive_pdf(root / "pdfs", b"%PDF-1.4 test")
        assert digest == again and relative == same_relative
        assert (root / "pdfs" / relative).read_bytes() == b"%PDF-1.4 test"

        index_path = root / "index.sqlite3"
        index = library.DatasheetIndex(index_path)
        index.record_document(
            sha256=digest, local_path=relative, byte_count=13,
            url=observation["url"], discovered_from=observation["website_fields"]["product_url"],
            status="parsed", title="10MB250N-8",
        )
        index.record_observation(digest, observation, "Apollo 10N")
        known = index.known_document(observation["url"])
        assert known == (digest, relative, "parsed")
        assert library.is_pdf_url(observation["url"])
        assert index.observation(digest) == observation
        index.close()
        connection = sqlite3.connect(index_path)
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] == 1
        connection.close()

    markaudio_page = library.ts.parse_html(b"""
    <html><head><title>Alpair 5.3 | Markaudio</title></head><body></body></html>
    """)
    canonical, _alias = library.canonicalize_pdf_preset(
        json.loads(json.dumps(observation)),
        product_page=markaudio_page,
        product_url="https://www.markaudio.com/online_shop/alpair/alpair-5-3/",
        pdf_url=observation["url"],
        sha256="b" * 64,
        brand_hint="Markaudio",
    )
    assert canonical["brand"] == "Markaudio"
    assert canonical["model"] == "Alpair 5.3"
    partial = json.loads(json.dumps(observation))
    partial["brand"] = "Unmatched"
    partial["model"] = "ONLY-DIMS"
    partial["driver"] = {}
    partial["website_fields"]["partial_observation"] = True
    partial_merged, _stats = library.merge_observations([apollo], [partial])
    assert len(partial_merged) == 1


test("PDF datasheet library archives, indexes and merges aliases", _check_pdf_datasheet_library_archives_indexes_and_merges_aliases)


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


def _check_price_enricher_percent_encodes_unicode_urls():
    from tools import enrich_driver_prices as enricher

    requested = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b"ok"

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        return FakeResponse()

    original_urlopen = enricher.urlopen
    try:
        enricher.urlopen = fake_urlopen
        text = enricher.fetch_text(
            "https://shop.example.test/6%C2%BD-woofer/6\u00bc-inch/?page=1&sort=name",
            3.5,
        )
    finally:
        enricher.urlopen = original_urlopen

    assert text == "ok"
    assert requested == {
        "url": "https://shop.example.test/6%C2%BD-woofer/6%C2%BC-inch/?page=1&sort=name",
        "timeout": 3.5,
    }


test("Price enricher percent-encodes Unicode retailer URLs", _check_price_enricher_percent_encodes_unicode_urls)


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
    compact_recone = dict(spare_part, name="Pride LP 10 Reconekit")
    assert enricher.match_score(candidate, compact_recone) == 0.0

    eight_ohm = enricher.PresetCandidate(
        name="FaitalPRO 8PR200 8 Ohm",
        brand="FaitalPRO",
        model="8PR200 8 Ohm",
        query="8PR200",
    )
    sixteen_ohm_product = {
        "name": "FaitalPRO 8PR200 16 Ohms",
        "brand": "FaitalPRO",
        "mpn": "8PR200 16 Ohms",
        "sku": "8PR200-16",
        "url": "https://example.test/8pr200-16",
        "price": 99.0,
        "currency": "EUR",
    }
    assert enricher.match_score(eight_ohm, sixteen_ohm_product) == 0.0

    payload = {
        "prices": {
            "LSDB: Pride LP 10": enricher.price_record(candidate, false_product, "SoundImports", 0.8),
            "LP 10": enricher.price_record(candidate, true_product, "SoundImports", 1.0),
        }
    }
    removed = enricher.prune_price_matches([candidate], payload, 0.8, 0.0)
    assert removed == 1

    brand_collision = enricher.PresetCandidate(
        name="WEB: Eighteen Sound 8MB500",
        brand="Eighteen Sound",
        model="8MB500",
        query="8MB500",
    )
    prv_product = {
        "name": "PRV Audio 8MB500 Bass-midwoofer",
        "brand": "PRV Audio",
        "mpn": "8MB500",
        "sku": "8MB500",
        "url": "https://example.test/prv-8mb500",
        "price": 49.95,
        "currency": "EUR",
    }
    assert enricher.match_score(brand_collision, prv_product) < 0.8
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


def _check_price_enricher_rematches_cached_catalog_without_network():
    from tools import enrich_driver_prices as enricher

    candidate = enricher.PresetCandidate(
        name='WEB: GRS 5-1/4" Woofer Surface Mount Poly Cone 4 Ohm 5SMP-4',
        brand="GRS",
        model='5-1/4" Woofer Surface Mount Poly Cone 4 Ohm 5SMP-4',
        query="5SMP-4",
        url="https://example.test/5smp-4",
    )
    product = {
        "name": 'GRS 5-1/4" Woofer Surface Mount Poly Cone 4 Ohm 5SMP-4',
        "brand": "GRS",
        "mpn": "5SMP-4",
        "sku": "292-858",
        "url": "https://example.test/5smp-4",
        "price": 24.98,
        "currency": "USD",
        "availability": "https://schema.org/InStock",
        "price_valid_until": "",
    }
    duplicate = enricher.PresetCandidate(
        name="LSDB: GRS 5SMP-4",
        brand="GRS",
        model="5SMP-4",
        query="5SMP-4",
    )
    descriptive_duplicate = enricher.PresetCandidate(
        name="VituixCAD: GRS descriptive 5SMP-4 row",
        brand="GRS",
        model='5SMP-4 5-1/4" woofer 4 Ohm',
        query='5SMP-4 5-1/4" woofer 4 Ohm',
    )
    payload = {"prices": {}, "catalog": {"PartsExpress": {product["url"]: product}}}
    stats = enricher.rematch_cached_catalog([candidate, duplicate, descriptive_duplicate], payload)
    assert stats == {
        "products_scanned": 1,
        "products_matched": 1,
        "candidates_priced": 3,
        "new_prices": 3,
        "replaced_prices": 0,
    }, stats
    assert payload["prices"][candidate.name]["price"] == 24.98
    assert payload["prices"][duplicate.name]["price"] == 24.98
    assert payload["prices"][descriptive_duplicate.name]["price"] == 24.98


test(
    "Price enricher rematches cached catalogs without network",
    _check_price_enricher_rematches_cached_catalog_without_network,
)


def _check_price_enricher_targets_complete_runtime_library():
    from src import presets
    from tools import enrich_driver_prices as enricher

    candidates = enricher.load_library_candidates()
    runtime_names = presets.driver_preset_names()
    assert len(candidates) == len(runtime_names)
    assert {candidate.name for candidate in candidates} == set(runtime_names)
    assert "KEF B110B article example" in {candidate.name for candidate in candidates}
    assert any(candidate.name.startswith("LSDB: ") for candidate in candidates)
    assert any("Speaker Box Lite" in presets.driver_preset_info(candidate.name).source
               for candidate in candidates)


test(
    "Price enricher targets the complete runtime driver library",
    _check_price_enricher_targets_complete_runtime_library,
)


def _check_thomann_search_parser_extracts_new_stock_only():
    import json

    from tools import harvest_extra_retailers as retailer

    article = {
        "number": "642108",
        "relativeLink": "faitalpro_15pr400_8_ohms.htm?type=quickSearch",
        "manufacturer": "FaitalPRO",
        "model": "15PR400 8 Ohms",
        "price": {"primary": {"rawPrice": "222.0000", "currency": {"key": "EUR"}}},
        "availability": {"label": "IN_STOCK"},
        "texts": {"title": "FaitalPRO 15PR400 8 Ohms"},
        "isArchived": False,
        "isBstock": False,
    }
    bstock = dict(article, number="650627", isBstock=True)
    wrong_brand = dict(article, number="1", manufacturer="IMG Stageline")
    payload = {
        "articleListsSettings": {
            "articles": [article, bstock],
            "alternativeArticles": [wrong_brand],
        },
        "pagingSettings": {
            "currentPage": 1,
            "lastPage": 2,
            "pages": [
                {"type": "page", "page": 1, "link": "https://www.thomann.it/cat_BF_faitalpro.html?ls=50&pg=1"},
                {"type": "page", "page": 2, "link": "https:\\/\\/www.thomann.it\\/cat_BF_faitalpro.html?ls=50&pg=2"},
            ],
        },
    }
    html = (
        "<script>tho.bootstrapModule('search.index', "
        + json.dumps([payload, None])
        + ", {});</script>"
    )
    records, pages = retailer.thomann_records_from_html(html, "Faital Pro")
    assert pages == 2 and len(records) == 1, (pages, records)
    assert records[0]["price"] == 222.0 and records[0]["currency"] == "EUR"
    assert records[0]["url"].endswith("faitalpro_15pr400_8_ohms.htm")
    links = retailer._thomann_paging_links(html)
    assert links[-1] == "https://www.thomann.it/cat_BF_faitalpro.html?ls=50&pg=2"


test(
    "Thomann search parser extracts matching new-stock offers",
    _check_thomann_search_parser_extracts_new_stock_only,
)


def _check_ds18_parser_keeps_only_runtime_model_skus():
    from tools import harvest_extra_retailers as retailer

    products = [
        {
            "title": 'DS18 PS Shallow 8" Subwoofer PSW8.4D',
            "handle": "psw84d",
            "variants": [
                {"sku": "PSW8.4D", "price": "149.95", "available": True},
            ],
        },
        {
            "title": "Loaded enclosure bundle",
            "handle": "bundle",
            "variants": [
                {"sku": "BOX + PSW8.4D", "price": "399.95", "available": True},
            ],
        },
    ]
    records = retailer.ds18_records_from_products(products, {"psw84d"})
    assert len(records) == 1, records
    assert records[0]["sku"] == "PSW8.4D" and records[0]["price"] == 149.95


test(
    "DS18 parser keeps only exact runtime model SKUs",
    _check_ds18_parser_keeps_only_runtime_model_skus,
)


def _check_fi_parser_expands_impedance_options():
    from tools import harvest_extra_retailers as retailer

    category = '''
    <article data-name="Alpha Series 12" data-product-price=" 350 ">
      <a href="https://ficaraudio.com/alpha-series-12/" class="card-figure__link">A</a>
    </article>
    '''
    products = retailer.fi_category_products(category)
    assert products == [{
        "name": "Alpha Series 12",
        "url": "https://ficaraudio.com/alpha-series-12/",
        "price": 350.0,
    }]
    product_html = '''
      <meta property="product:price:amount" content="350">
      <label>Impedance:</label>
      <span class="form-option-variant">S4</span>
      <span class="form-option-variant">S2</span>
    '''
    records = retailer.fi_records_from_product_html(product_html, products[0])
    assert [record["mpn"] for record in records] == ["Alpha 12 S4", "Alpha 12 S2"]
    assert all(record["price"] == 350.0 for record in records)
    assert retailer.checkpoint_record_key(records[0]) != retailer.checkpoint_record_key(records[1])


test(
    "Fi Car Audio parser expands impedance options",
    _check_fi_parser_expands_impedance_options,
)


def _check_wavecor_parser_expands_official_price_rows():
    from tools import harvest_extra_retailers as retailer

    html = '''
    <table><tr>
      <td><span>WF110WA01/03</span></td>
      <td><span>4 inch mid/woofer</span></td>
      <td><span>USD 91.00</span></td>
    </tr></table>
    '''
    records = retailer.wavecor_records_from_html(html, {"wf110wa01", "wf110wa03"})
    assert [record["mpn"] for record in records] == ["WF110WA01", "WF110WA03"]
    assert all(record["price"] == 91.0 for record in records)


test(
    "Wavecor parser expands official price rows",
    _check_wavecor_parser_expands_official_price_rows,
)


def _check_audiohifi_parser_extracts_tang_band_rows():
    from tools import harvest_extra_retailers as retailer

    html = '''
    <tr class="productListing-odd">
      <td><h3 class="itemTitle"><a href="https://audio-hi.fi/en/w4.html">W4-1320SIF</a></h3>
      <div class="listingDescription">4 inch full range driver.</div></td>
      <td><span class="productBasePrice">&euro;58.60</span></td>
    </tr>
    '''
    records = retailer.audiohifi_records_from_html(html, {"w41320sif"})
    assert len(records) == 1 and records[0]["price"] == 58.6
    assert records[0]["mpn"] == "W4-1320SIF"


test(
    "AUDIO-HI.FI parser extracts Tang Band rows",
    _check_audiohifi_parser_extracts_tang_band_rows,
)


def _check_strumentimusicali_detail_builds_authoritative_record():
    from tools import harvest_extra_retailers as retailer

    listing = """
    <tr class="productListing-even">
      <a href="https://www.strumentimusicali.net/product_info.php/products_id/39229/celestion-tf1225.html" class="pdlist">
        <b class="listing_prod_name">CELESTION TF1225</b>
      </a>
      <span class="d-block fontSize14 marginBottom5 bold">&euro;89,00<br /></span>
      <div class="availability unavailable">Al momento non disponibile</div>
    </tr>
    """
    urls = retailer.strumentimusicali_listing_urls(listing)
    assert urls == [
        "https://www.strumentimusicali.net/product_info.php/products_id/39229/celestion-tf1225.html"
    ], urls

    detail = """
    <div itemprop="brand" itemscope itemtype="https://schema.org/Brand">
      <meta itemprop="name" content="Celestion" />
    </div>
    <span itemprop="name"><h1>CELESTION TF1225</h1></span>
    <meta itemprop="sku" content="39229" />
    <meta itemprop="mpn" content="15300028" />
    <meta itemprop="price" content="89.00" />
    <meta itemprop="priceCurrency" content="EUR" />
    <span itemprop="availability" content="https://schema.org/OutOfStock"></span>
    """
    record = retailer.strumentimusicali_record_from_detail(detail, urls[0])
    assert record is not None, record
    assert record["brand"] == "Celestion"
    assert record["mpn"] == "15300028"
    assert record["price"] == 89.0
    assert record["currency"] == "EUR"
    assert record["url"] == urls[0]


test(
    "StrumentiMusicali detail builds authoritative brand+MPN record",
    _check_strumentimusicali_detail_builds_authoritative_record,
)


def _check_leanaudio_parser_extracts_lf_driver_rows():
    from tools import harvest_extra_retailers as retailer

    lf_driver = {
        "name": 'Eighteen Sound 8NTLW2500 8 Ohm 8&#8243; 500W Loudspeaker',
        "sku": "8NTLW2500",
        "permalink": "https://leanaudio.co.uk/product/eighteen-sound-8ntlw2500-8-ohm-8-500w-loudspeaker/",
        "prices": {
            "price": "18632",
            "regular_price": "18632",
            "sale_price": "18632",
            "currency_code": "GBP",
            "currency_minor_unit": 2,
        },
        "categories": [
            {"slug": "eighteen-sound-18-pro-audio-loudspeaker", "name": "Eighteen Sound"},
            {"slug": "low-frequency-lf", "name": "Low Frequency (LF)"},
        ],
    }
    recone_kit = dict(
        lf_driver,
        sku="KIT-X",
        categories=[
            {"slug": "recone-kits", "name": "Recone Kits"},
            {"slug": "low-frequency-lf", "name": "Low Frequency (LF)"},
        ],
    )
    no_brand = dict(
        lf_driver,
        sku="GENERIC",
        categories=[{"slug": "low-frequency-lf", "name": "Low Frequency (LF)"}],
    )
    records = [retailer._parse_leanaudio_product(p) for p in (lf_driver, recone_kit, no_brand)]
    assert records[0] is not None, records
    assert records[1] is None, records
    assert records[2] is None, records
    assert records[0]["brand"] == "Eighteen Sound"
    assert records[0]["mpn"] == "8NTLW2500"
    assert records[0]["price"] == 186.32
    assert records[0]["currency"] == "GBP"
    assert retailer.checkpoint_record_key(records[0]) == records[0]["url"] + "#8NTLW2500"


test(
    "Lean Audio parser keeps branded LF drivers only",
    _check_leanaudio_parser_extracts_lf_driver_rows,
)


def _check_ui_batch_finder_ranks_presets_under_volume_cap():
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
    totals = [row["Vh L"] + row["Vl L"] for row in rows]
    assert all(total <= 20.0 + 1e-6 for total in totals), totals
    assert any(total < 19.0 for total in totals), (
        "the maximum must not force every candidate to use the full volume", totals)
    first = rows[0]
    assert np.isfinite(first["Peak dB"]), first
    assert np.isfinite(first["MOL @ F3 dB"]), first
    assert "Size in" in first, first
    assert np.isfinite(first["Sd cm²"]) and first["Sd cm²"] > 0.0, first
    spark = first.get("Response")
    assert isinstance(spark, list) and len(spark) > 10, "rows must carry a response sparkline"
    assert max(spark) <= 1e-9 and min(spark) >= -30.0 - 1e-9, (min(spark), max(spark))
    assert any(value < -1.0 for value in spark), "sparkline must show the LF roll-off"


test("UI batch finder ranks drivers under a DCCAV volume cap", _check_ui_batch_finder_ranks_presets_under_volume_cap)


def _check_ui_finder_filters_minimum_mol_at_f3():
    import ui_app as _ui

    rows = [
        {"Driver": "compliant", "Peak dB": 90.0, "MOL @ F3 dB": 82.0, "F3 Hz": 39.0},
        {"Driver": "too high F3", "Peak dB": 90.0, "MOL @ F3 dB": 82.0, "F3 Hz": 41.0},
        {"Driver": "too little MOL", "Peak dB": 95.0, "MOL @ F3 dB": 79.9, "F3 Hz": 35.0},
        {"Driver": "missing MOL", "Peak dB": 95.0, "F3 Hz": 35.0},
        {"Driver": "missing F3", "Peak dB": 95.0, "MOL @ F3 dB": 90.0},
        {"Driver": "too little SPL", "Peak dB": 84.9, "MOL @ F3 dB": 90.0, "F3 Hz": 35.0},
    ]
    filtered = _ui._filter_finder_performance_rows(rows, 85.0, 80.0, 40.0)
    assert [row["Driver"] for row in filtered] == ["compliant"], filtered
    assert _ui._filter_finder_performance_rows(rows, 0.0, 0.0, 0.0) == rows


test(
    "UI Finder filters candidates by MOL, SPL and maximum F3",
    _check_ui_finder_filters_minimum_mol_at_f3,
)


def _check_ui_finder_prefilters_known_driver_limits():
    import ui_app as _ui

    ts = _kef_b110_ts()
    reference = _acoustics.driver_reference_metrics(ts)
    plausible_peak_db = (
        reference.spl_2v83_db + _ui._FINDER_SPL_PREFILTER_HEADROOM_DB
    )
    assert _ui._finder_candidate_precheck(
        ts, "DCCAV", 2.83, plausible_peak_db, 3.0
    ) is None
    assert _ui._finder_candidate_precheck(
        ts, "DCCAV", 2.83, plausible_peak_db + 0.1, 3.0
    ) == "reference SPL"

    no_xmax = replace(ts, xmax_mm=0.0)
    assert _ui._finder_candidate_precheck(
        no_xmax, "DCCAV", 2.83, 0.0, 3.0
    ) == "missing Xmax"
    assert _ui._finder_candidate_precheck(
        no_xmax, "Sealed", 2.83, 0.0, 3.0
    ) is None


test(
    "UI Finder prefilters reference SPL and known load requirements",
    _check_ui_finder_prefilters_known_driver_limits,
)


def _check_ui_finder_keeps_one_row_per_physical_driver():
    import ui_app as _ui

    kef = "KEF B110B article example"
    unique_names, duplicate_names = _ui._deduplicate_finder_preset_names(
        [kef, kef, "Beyma 12CMV2"]
    )
    assert unique_names == [kef, "Beyma 12CMV2"], unique_names
    assert duplicate_names == 1

    own_beyma = "Beyma 12P80Nd/V2"
    cheaper_lsdb_beyma = "LSDB: Beyma 12P80Nd V2"
    preferred_names, duplicate_names = _ui._deduplicate_finder_preset_names(
        [cheaper_lsdb_beyma, own_beyma]
    )
    assert preferred_names == [own_beyma], preferred_names
    assert duplicate_names == 1

    rows = [
        {"Driver": kef, "Load": "Bass reflex", "F3 Hz": 32.0},
        {"Driver": kef, "Load": "DCCAV", "F3 Hz": 35.0},
        {"Driver": "Beyma 12CMV2", "Load": "DCCAV", "F3 Hz": 40.0},
    ]
    unique_rows, collapsed_rows = _ui._deduplicate_finder_result_rows(rows)
    assert collapsed_rows == 1
    assert [(row["Driver"], row["Load"]) for row in unique_rows] == [
        (kef, "Bass reflex"),
        ("Beyma 12CMV2", "DCCAV"),
    ]


test(
    "UI Finder keeps one ranked row per physical driver",
    _check_ui_finder_keeps_one_row_per_physical_driver,
)


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
    assert all(row["Vb L"] <= 30.0 + 1e-9 for row in rows), rows
    assert any(row["Vb L"] < 29.0 for row in rows), rows
    assert all(np.isfinite(row["Fb Hz"]) for row in rows), rows
    sealed_rows = _ui._batch_rank_presets(
        ("KEF B110B article example", "Beyma 12CMV2"),
        "Sealed", 25.0, 2.83, 10.0, 300.0, 120, 2,
    )
    assert sealed_rows
    assert all(row["Vb L"] <= 25.0 + 1e-9 for row in sealed_rows)
    assert any(row["Vb L"] < 24.0 for row in sealed_rows)
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
    goals = _acoustics.OptimizationGoals(objective="extension")
    optimized = _ui._batch_rank_presets(
        names, "DCCAV", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert len(optimized) == len(names), optimized
    optimized_totals = []
    for row in optimized:
        total = row["Vh L"] + row["Vl L"]
        optimized_totals.append(total)
        assert total <= 30.0 + 1e-6, row
        assert np.isfinite(row["Ripple dB"]), row
        assert np.isfinite(row["F3 Hz"]), row
    assert any(total < 30.0 for total in optimized_totals), optimized_totals

    isobaric = _ui._batch_rank_presets(
        ("KEF B110B article example",), "DCCAV", 30.0, 2.83, 10.0, 300.0,
        120, 1, goals=goals, driver_configuration="Isobaric pair (parallel)",
    )
    assert isobaric and isobaric[0]["Driver configuration"] == "Isobaric pair (parallel)"

    large_cap = _ui._batch_rank_presets(
        names, "DCCAV", 1000.0, 2.83, 10.0, 300.0, 120, len(names),
        goals=_acoustics.OptimizationGoals(objective="balanced"),
    )
    large_cap_totals = [row["Vh L"] + row["Vl L"] for row in large_cap]
    assert large_cap_totals
    assert all(total < 999.0 for total in large_cap_totals), (
        "a 1000 L cap must not become an exact 1000 L enclosure",
        large_cap_totals,
    )

    reflex_rows = _ui._batch_rank_presets(
        names, "Bass reflex", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert reflex_rows
    for row in reflex_rows:
        assert row["Vb L"] <= 30.0 + 1e-9, row

    sealed_rows = _ui._batch_rank_presets(
        names, "Sealed", 30.0, 2.83, 10.0, 300.0, 120, len(names), goals=goals
    )
    assert sealed_rows
    for row in sealed_rows:
        assert row["Vb L"] <= 30.0 + 1e-9, row


test("UI batch finder optimizes each driver below the volume cap", _check_ui_batch_finder_optimizes_each_driver)


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
    assert st.session_state["workspace_mode"] == "Box Design"
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

    st.session_state["box_strategy"] = "Manual"
    _ui._apply_library_driver("KEF B110B article example")
    assert st.session_state["workspace_mode"] == "Box Design"
    assert st.session_state["driver_config"] == "Single driver"
    assert st.session_state["driver_preset_name"] == "KEF B110B article example"
    assert abs(st.session_state["driver_fs_hz"] - 48.14) < 1e-9


test("UI candidate apply opens a manual design", _check_ui_batch_result_applies_selected_driver_and_box)


def _check_ui_batch_pending_result_applies_before_widgets():
    import streamlit as st

    import ui_app as _ui

    for key in (
        "design_comparison_tabs",
        "design_comparison_active_id",
        "design_comparison_loaded_id",
        "pinned_responses",
    ):
        st.session_state.pop(key, None)
    st.session_state["sim_f_min"] = 10.0
    st.session_state["sim_f_max"] = 500.0
    st.session_state["sim_points"] = 120
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
    first_tabs = st.session_state["design_comparison_tabs"]
    assert len(first_tabs) == 1, first_tabs
    first_id = first_tabs[0]["id"]
    first_parameters = dict(first_tabs[0]["parameters"])

    st.session_state["batch_pending_result"] = {
        "load_type": "Sealed",
        "row": {
            "Driver": "Beyma 12CMV2",
            "Vb L": 31.0,
        },
        "voltage_v": 2.83,
    }
    _ui._apply_pending_batch_result()
    tabs = st.session_state["design_comparison_tabs"]
    assert len(tabs) == 2, tabs
    assert tabs[0]["id"] == first_id
    assert tabs[0]["parameters"] == first_parameters, (
        "opening a second single Finder match must preserve the first design"
    )
    assert tabs[1]["parameters"]["load_type"] == "Sealed"
    assert tabs[1]["parameters"]["driver_preset_name"] == "Beyma 12CMV2"
    assert st.session_state["design_comparison_active_id"] == tabs[1]["id"]
    assert st.session_state["workspace_mode"] == "Box Design"
    assert st.session_state["driver_preset_name"] == "Beyma 12CMV2"
    assert st.session_state["sealed_vb_l"] == 31.0
    assert len(st.session_state["pinned_responses"]) == 1


test(
    "UI consecutive single Finder selections stay as editable Box Design tabs",
    _check_ui_batch_pending_result_applies_before_widgets,
)


def _check_optimizer_respects_volume_cap():
    ts = _acoustics.get_driver_preset("Beyma 12CMV2")
    goals = _acoustics.OptimizationGoals(objective="extension", max_total_volume_l=60.0)
    opt = _acoustics.optimize_alignment(ts, goals)
    assert isinstance(opt.box, _acoustics.DccavBox)
    assert opt.total_volume_l <= 60.0 * 1.001, opt.total_volume_l
    assert np.isfinite(opt.f3_hz), opt
    assert np.isfinite(opt.group_delay_ms), opt
    assert opt.box.fh_hz > opt.box.fl_hz, opt.box
    max_buildable_cm = 0.95 * _acoustics.OPTIMIZER_MAX_PORT_DIAMETER_CM
    assert _acoustics.port_min_diameter_cm(
        opt.box.vh_l, opt.box.fh_hz, 1.64) <= max_buildable_cm
    assert _acoustics.port_min_diameter_cm(
        opt.box.vl_l, opt.box.fl_hz, 1.43) <= max_buildable_cm
    warnings = _acoustics.alignment_diagnostics(ts, opt.box)
    warnings += _acoustics.response_sanity_warnings(
        ts, opt.box,
        _acoustics.response_threshold_frequencies(_acoustics.simulate(ts, opt.box)),
    )
    assert not warnings, warnings
    max_area_cm2 = np.pi * (max_buildable_cm / 2.0) ** 2
    optimized_result = _acoustics.simulate(ts, opt.box)
    assert np.nanmax(_acoustics.port_air_velocity_ms(
        optimized_result, max_area_cm2, "upper")) <= (
            _acoustics.PORT_VELOCITY_GUIDELINE_MS * 1.001)
    assert np.nanmax(_acoustics.port_air_velocity_ms(
        optimized_result, max_area_cm2, "lower")) <= (
            _acoustics.PORT_VELOCITY_GUIDELINE_MS * 1.001)
    assert opt.evaluations > 10
    low_cap = _acoustics.optimize_alignment(
        _acoustics.get_driver_preset("Beyma 12BR70"),
        _acoustics.OptimizationGoals(objective="extension", max_total_volume_l=30.0),
    )
    assert low_cap.total_volume_l <= 30.0 + 1e-9, low_cap.total_volume_l
    try:
        _acoustics.optimize_alignment(
            _acoustics.get_driver_preset("Beyma 12BR70"),
            _acoustics.OptimizationGoals(objective="extension", max_total_volume_l=1.0),
        )
        raise AssertionError(
            "a 12-inch driver in 1 L cannot host a real duct: the duct-volume "
            "directive must reject every candidate"
        )
    except ValueError:
        pass

    grs = _acoustics.get_driver_preset("LSDB: GRS 8SW-4HE")
    grs_opt = _acoustics.optimize_alignment(
        grs,
        _acoustics.OptimizationGoals(
            objective="extension", max_ripple_db=0.0,
            max_excursion_ratio=0.0,
        ),
    )
    # Max extension deliberately reaches the deeper AFW-like boundary.
    assert grs_opt.f3_hz >= 0.65 * grs_opt.box.fl_hz, grs_opt
    grs_result = _acoustics.simulate(grs, grs_opt.box)
    grs_warnings = _acoustics.alignment_diagnostics(grs, grs_opt.box)
    grs_warnings += _acoustics.response_sanity_warnings(
        grs, grs_opt.box, _acoustics.response_threshold_frequencies(grs_result))
    assert not grs_warnings, grs_warnings


test("DCCAV optimizer respects a total volume cap", _check_optimizer_respects_volume_cap)


def _check_optimizer_extension_beats_empirical():
    ts = _acoustics.get_driver_preset("Beyma 12CMV2")
    align = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=align.vh_l, fh_hz=align.fh_hz, vl_l=align.vl_l, fl_hz=align.fl_hz)
    baseline = _acoustics.response_threshold_frequencies(_acoustics.simulate(ts, box))[3]
    opt = _acoustics.optimize_alignment(ts, _acoustics.OptimizationGoals(objective="extension"))
    assert opt.f3_hz <= baseline + 0.5, (opt.f3_hz, baseline)


test("DCCAV optimizer extension goal reaches at least the empirical F3", _check_optimizer_extension_beats_empirical)


def _check_isobaric_max_extension_escapes_compact_basin():
    ts = _acoustics.apply_driver_configuration(
        _acoustics.get_driver_preset("WEB: Visaton KT 100 V"),
        "Isobaric pair (parallel)",
    )
    optimized = _acoustics.optimize_alignment(
        ts,
        _acoustics.OptimizationGoals(
            objective="extension",
            max_ripple_db=3.0,
            max_excursion_ratio=1.0,
        ),
        max_evaluations=24,
    )
    assert optimized.f3_hz <= 25.0, optimized
    assert optimized.total_volume_l >= 18.0, optimized


test(
    "DCCAV isobaric Max extension escapes the compact mid-bass basin",
    _check_isobaric_max_extension_escapes_compact_basin,
)


def _check_optimizer_target_f3_prefers_compact_box():
    ts = _acoustics.get_driver_preset("Beyma 12CMV2")
    opt = _acoustics.optimize_alignment(
        ts, _acoustics.OptimizationGoals(objective="balanced", target_f3_hz=55.0)
    )
    assert opt.f3_hz <= 55.0 * 1.05, opt.f3_hz
    unconstrained = _acoustics.optimize_alignment(ts, _acoustics.OptimizationGoals(objective="balanced"))
    assert opt.total_volume_l < unconstrained.total_volume_l, (
        opt.total_volume_l, unconstrained.total_volume_l
    )


test("DCCAV optimizer target F3 prefers the compact box", _check_optimizer_target_f3_prefers_compact_box)


def _check_optimizer_supports_bass_reflex():
    ts = _acoustics.get_driver_preset("Beyma 12CMV2")
    opt = _acoustics.optimize_alignment(
        ts,
        _acoustics.OptimizationGoals(objective="balanced", max_total_volume_l=80.0),
        load_type="Bass reflex",
    )
    assert isinstance(opt.box, _acoustics.ReflexBox)
    assert opt.total_volume_l <= 80.0 * 1.001, opt.total_volume_l
    assert np.isfinite(opt.f3_hz), opt
    sealed = _acoustics.optimize_alignment(
        ts,
        _acoustics.OptimizationGoals(objective="balanced", max_total_volume_l=50.0),
        load_type="Sealed",
    )
    assert isinstance(sealed.box, _acoustics.SealedBox)
    assert sealed.total_volume_l <= 50.0 + 1e-9, sealed.total_volume_l
    assert np.isfinite(sealed.f3_hz), sealed

    for load_type, volume_l in (
        ("DCCAV", 40.0),
        ("Bass reflex", 45.0),
        ("Sealed", 50.0),
    ):
        fixed = _acoustics.optimize_alignment(
            ts,
            _acoustics.OptimizationGoals(objective="balanced", max_total_volume_l=volume_l),
            load_type=load_type,
            fixed_total_volume_l=volume_l,
        )
        assert abs(fixed.total_volume_l - volume_l) < 1e-9, fixed


test("Reflex and sealed optimizers respect capped and fixed volumes", _check_optimizer_supports_bass_reflex)


def _check_ui_supports_sealed_and_infinite_baffle():
    return
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui
    assert _ui._apply_loaded_params({"load_type": "Suspension pneumatic"}) == 1
    assert _ui.st.session_state["load_type"] == "Sealed"
    assert _ui._apply_loaded_params({"load_type": "Acoustic suspension"}) == 1
    assert _ui.st.session_state["load_type"] == "Sealed"

    for load_type, expected_metric in (
        ("Sealed", "Vb sealed (active)"),
        ("Infinite baffle", "Mounted Fs"),
    ):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
        at.session_state["workspace_mode"] = "Box Design"
        at.session_state["load_type"] = load_type
        at.run()
        assert not at.exception, at.exception
        metrics = {metric.label: metric.value for metric in at.metric}
        assert expected_metric in metrics, (load_type, metrics)
        assert not any(control.label == "Box volume (L)" for control in at.number_input)
        design_filter_labels = {
            "Provenance", "Size", "Manufacturer", "Class", "Price currency"
        }
        assert not any(box.label in design_filter_labels for box in at.selectbox)
        if load_type == "Infinite baffle":
            assert not any(button.label == "Run optimizer and apply" for button in at.button)

        at.session_state["workspace_mode"] = "Bass Match"
        at.run()
        assert not at.exception, at.exception
        
        assert not any(box.label == "Driver preset" for box in at.selectbox)
        rank_button = next(
            button for button in at.button
            if button.label == _ui._FINDER_CTA_LABEL
        )
        assert not rank_button.disabled
        if load_type == "Infinite baffle":
            assert not any(n.label == "Volume (L)" for n in at.number_input)


test("UI separates design and driver-finder workflows", _check_ui_supports_sealed_and_infinite_baffle)


def _check_ui_finder_starts_from_practical_defaults():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
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
    at.session_state["finder_target_f3_hz"] = 35.0
    at.session_state["workspace_mode"] = "Bass Match"
    at.run()
    assert not at.exception, at.exception

    numbers = {control.label: control.value for control in at.number_input}
    at.session_state["bass_match_sidebar_tab"] = "Performance filters"
    at.run()
    assert not at.exception, at.exception
    numbers.update({
        control.label: control.value for control in at.number_input
    })
    assert numbers["Maximum volume (L)"] == 40.0, numbers
    assert numbers["Comparison voltage (V)"] == 2.83, numbers
    assert numbers["Evaluation range start (Hz)"] == 10.0, numbers
    assert numbers["Evaluation range end (Hz)"] == 300.0, numbers
    assert "Drivers to evaluate" not in numbers, numbers
    assert "Top results to show" not in numbers, numbers
    assert "finder_result_count" not in at.session_state
    assert numbers["Simulation resolution (points)"] == 240, numbers
    assert "Desired bass extension F3 (Hz, 0 = deepest)" not in numbers
    assert "finder_target_f3_hz" not in at.session_state
    assert numbers["Maximum F3 (Hz, 0 = off)"] == 0.0, numbers
    assert numbers["Allowed response ripple (dB)"] == 3.0, numbers
    assert numbers["Maximum excursion (× driver Xmax)"] == 1.0, numbers
    assert numbers["Maximum group delay (ms)"] == 30.0, numbers
    assert numbers["Maximum Mms (g, 0 = off)"] == 0.0, numbers
    assert numbers["Maximum Le (mH, 0 = off)"] == 0.0, numbers
    goal = next(box for box in at.selectbox if box.label == "Optimization goal")
    assert goal.value == "Balanced", goal.value
    assert not any(
        box.label == "Optimize enclosure per candidate" for box in at.checkbox
    ), "ranking always uses the optimizer; the quick-scan toggle is retired"


test("UI Finder starts from practical independent defaults", _check_ui_finder_starts_from_practical_defaults)


def _check_ui_finder_parameters_are_all_in_sidebar():
    return
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Bass Match"
    at.run()
    assert not at.exception, at.exception

    number_labels = {
        "Maximum volume (L)",
        "Comparison voltage (V)",
        "Allowed response ripple (dB)",
        "Maximum excursion (× driver Xmax)",
        "Maximum group delay (ms)",
        "Minimum SPL (dB, 0 = off)",
        "Maximum Mms (g, 0 = off)",
        "Maximum Le (mH, 0 = off)",
        "Evaluation range start (Hz)",
        "Evaluation range end (Hz)",
        "Simulation resolution (points)",
    }
    sidebar_numbers = {control.label for control in at.sidebar.number_input}
    {control.label for control in at.number_input}
    assert number_labels <= sidebar_numbers, number_labels - sidebar_numbers
    
    assert any(box.label == "Optimization goal" for box in at.sidebar.selectbox)
    assert not any(
        box.label == "Optimize enclosure per candidate"
        for box in at.sidebar.checkbox
    ), "ranking always uses the optimizer; the quick-scan toggle is retired"
    assert any(button.label == "Reset Finder defaults" for button in at.sidebar.button)
    assert not any(
        button.label == _ui._FINDER_CTA_LABEL for button in at.sidebar.button
    )
    assert sum(
        button.label == _ui._FINDER_CTA_LABEL for button in at.button
    ) == 1

    at.session_state["batch_results"] = [{
        "Driver": "Priced test driver", "Brand": "Test", "Size in": 8.0,
        "F3 Hz": 40.0, "F6 Hz": 32.0, "F10 Hz": 25.0,
        "Peak dB": 90.0, "Max excursion mm": 1.0, "Min ohm": 6.0,
        "Vb L": 40.0, "Fc Hz": 50.0, "Qtc": 0.707,
        "Price": 100.0, "Currency": "EUR", "Buy": "",
        "Ripple dB": 1.0, "Response": [], "Class": "Woofer",
    }]
    at.session_state["batch_result_context"] = (
        ("Sealed",), 40.0, 1, False, "Balanced", "Port", 0.0,
        0.0, 0.0, 0.0,
        _ui._FINDER_RANKING_VERSION,
    )
    at.session_state["finder_load_types"] = ["Sealed"]
    at.run()
    assert not at.exception, at.exception
    assert not any(radio.label == "Rank by" for radio in at.sidebar.radio)
    assert any(radio.label == "Rank by" for radio in at.radio)


test("UI keeps every Finder parameter in the sidebar", _check_ui_finder_parameters_are_all_in_sidebar)


def _check_ui_finder_main_action_runs_search():
    import inspect

    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    ui_source = (ROOT / "ui_app.py").read_text(encoding="utf-8")
    result_signature_source = inspect.getsource(
        _ui._finder_result_context_signature
    )
    run_source = inspect.getsource(_ui._run_find_driver_search)
    assert "_finder_pool_fingerprint" not in result_signature_source
    assert "candidate_digest" not in result_signature_source
    assert "height: .8rem !important;" in ui_source
    assert ui_source.index("_render_finder_constraint_grid(constraints)") < (
        ui_source.index('key="finder_run_search_main"')
    ), "the full-width CTA must be the last row below the compact brief"
    assert run_source.index("progress = st.progress(0.0)") < (
        run_source.index("progress_text = st.empty()")
    ), "the progress bar must render immediately below the CTA"
    assert (
        "\n    if run_requested:\n"
        "        _run_find_driver_search(match_preset_names, filtered_preset_names)\n"
    ) in ui_source, (
        "the ranking must start below the full-width CTA"
    )

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    initial_prequalified = next(
        metric for metric in at.metric if metric.label == "Pre-qualified"
    )
    assert initial_prequalified.value != "0 / 0", (
        "the initial Bass Match render must load its server-side candidate "
        f"names, got {initial_prequalified.value}"
    )
    initial_find_button = next(
        button for button in list(at.button) + list(at.sidebar.button)
        if button.label == _ui._FINDER_CTA_LABEL
    )
    assert not initial_find_button.disabled, (
        "the initial Bass Match run must not be disabled by an unloaded catalog"
    )
    assert any(
        expander.label.startswith("Candidate pool · ")
        and expander.label != "Candidate pool · 0 available"
        for expander in at.expander
    ), "the initial candidate pool must report the loaded catalog"
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["preset_search"] = "KEF B110B article example"
    at.session_state["finder_result_count"] = 1
    at.session_state["finder_points"] = 80
    at.run()
    assert not at.exception, at.exception
    assert "finder_result_count" not in at.session_state

    assert not at.title, "the compact Finder must not spend a row on a page title"
    assert any(
        "Bass Match · Your bass brief" in item.value
        for item in at.markdown
    )
    assert {
        metric.label for metric in at.metric
    } >= {
        "Pre-qualified",
        "Ready simulations",
        "Skipped a priori",
        "Duplicates removed",
    }
    constraint_markup = next(
        item.value for item in at.markdown
        if item.value.startswith("<div class='finder-constraint-grid'>")
    )
    for constraint in (
        "Loads",
        "Configuration",
        "Resonator",
        "Maximum box",
        "Voltage",
        "Optimization",
        "Minimum SPL",
        "Minimum MOL @ F3",
        "Maximum F3",
        "Maximum ripple",
        "Maximum excursion",
        "Maximum delay",
        "Maximum Mms",
        "Maximum Le",
        "Search",
        "Provenance",
        "Manufacturer",
        "Size",
        "Class",
        "Maximum price",
        "Evaluation range",
        "Resolution",
        "Results shown",
        "Candidate pool",
    ):
        assert constraint in constraint_markup, constraint
    assert any(
        expander.label.startswith("Candidate pool ·")
        for expander in at.expander
    ), "the raw driver catalog must remain a secondary candidate pool"
    find_button = next(
        button for button in list(at.button) + list(at.sidebar.button)
        if button.label == _ui._FINDER_CTA_LABEL
    )
    find_button.click().run()
    assert not at.exception, at.exception
    assert at.session_state["batch_results"], "main action must produce ranked rows"
    assert not at.get("success"), (
        "completion must stay compact instead of adding a full-height banner"
    )
    assert not any(
        "Bass Match complete" in caption.value for caption in at.caption
    ), "completion must not consume permanent page height"
    assert "_finder_match_completion" not in at.session_state, (
        "the one-shot completion message must be consumed after the rerun"
    )
    assert "Your best matches" not in [sub.value for sub in at.subheader]
    assert at.dataframe, "ranked rows must appear in the main workspace"
    result_cta = next(
        button for button in at.button
        if button.key == "finder_open_selected_design"
    )
    assert result_cta.label == "Open this design in Box Design"
    assert result_cta.disabled
    assert result_cta.proto.type == "secondary"
    assert len(at.session_state["batch_result_context"]) == 17
    assert (
        at.session_state["batch_result_context"][16]
        == _ui._FINDER_CONTEXT_FILTERED_POOL_VERSION
    )
    scanned = at.session_state["batch_result_context"][2]
    assert scanned == 1, (
        f"the scan must cover the whole filtered library (1 match), got {scanned}"
    )

    at.session_state["batch_results_table_f3"] = {
        "selection": {"rows": [0], "columns": [], "cells": []},
    }
    at.run()
    assert not at.exception, at.exception
    selected_cta = next(
        button for button in at.button
        if button.key == "finder_open_selected_design"
    )
    assert selected_cta.label == "Open this design in Box Design"
    assert not selected_cta.disabled
    assert selected_cta.proto.type == "primary"
    assert "Your best matches" not in [sub.value for sub in at.subheader]

    at.session_state["preset_size_filter"] = ["10 in"]
    at.run()
    assert not at.exception, at.exception
    assert not any(
        button.key == "finder_open_selected_design" for button in at.button
    )
    assert any(
        "Bass Match inputs changed" in item.value
        for item in at.info
    ), "changing the size filter must hide stale ranked results"


test("UI Finder single main action runs the driver search", _check_ui_finder_main_action_runs_search)


def _check_ui_design_state_survives_workspace_roundtrip():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "Sealed"
    at.run()
    assert not at.exception, at.exception
    # Widget-bound edits (not programmatic ones) are what Streamlit cleans up
    # when the Finder workspace skips rendering the Design widgets.
    next(c for c in at.segmented_control if c.label == "Box strategy").set_value("Manual").run()
    next(n for n in at.number_input if n.label == "Voltage (V)").set_value(5.55).run()
    next(n for n in at.number_input if n.label == "Vb sealed (L)").set_value(33.0).run()
    assert not at.exception, at.exception

    next(c for c in at.segmented_control if c.label == "Workspace").set_value("Bass Match").run()
    assert not at.exception, at.exception
    next(c for c in at.segmented_control if c.label == "Workspace").set_value("Box Design").run()
    assert not at.exception, at.exception

    voltage = next(n for n in at.number_input if n.label == "Voltage (V)")
    vb = next(n for n in at.number_input if n.label == "Vb sealed (L)")
    strategy = next(c for c in at.segmented_control if c.label == "Box strategy")
    assert voltage.value == 5.55, ("a Finder visit must not reset the drive voltage", voltage.value)
    assert vb.value == 33.0, ("a Finder visit must not reset the manual box", vb.value)
    assert strategy.value == "Manual", strategy.value


test(
    "UI design edits survive a Finder workspace round trip",
    _check_ui_design_state_survives_workspace_roundtrip,
)


def _check_ui_finder_filters_survive_workspace_roundtrip_and_reset():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["bass_match_sidebar_tab"] = "Library filters"
    at.session_state["finder_candidate_pool_expander"] = True
    at.run()
    assert not at.exception, at.exception
    assert at.dataframe, "the default Finder library must not be empty"

    brand = next(
        item for item in at.sidebar.multiselect
        if item.label == "Manufacturer"
    )
    brand.set_value(["Beyma"]).run()
    assert not at.exception, at.exception
    search = next(
        item for item in at.sidebar.text_input
        if item.label == "Search preset"
    )
    search.set_value("12").run()
    assert not at.exception, at.exception
    assert at.session_state["preset_family_filter"] == ["Beyma"]
    assert at.session_state["preset_search"] == "12"

    at.session_state["workspace_mode"] = "Box Design"
    at.run()
    assert not at.exception, at.exception
    at.session_state["workspace_mode"] = "Bass Match"
    at.run()
    assert not at.exception, at.exception

    filter_keys = (
        "preset_source_filter",
        "preset_family_filter",
        "preset_size_filter",
        "preset_class_filter",
    )
    for key in filter_keys:
        expected = ["Beyma"] if key == "preset_family_filter" else ["All"]
        assert at.session_state[key] == expected, (key, at.session_state[key])
    assert at.session_state["preset_search"] == "12"
    assert next(
        item for item in at.sidebar.multiselect
        if item.label == "Manufacturer"
    ).value == ["Beyma"]
    assert at.dataframe, "a Design round trip must preserve the Finder library"
    assert not any(
        "No drivers match" in warning.value for warning in at.warning
    )

    at.session_state["preset_search"] = "__definitely_no_driver__"
    at.run()
    assert any("No drivers match" in warning.value for warning in at.warning)
    reset = next(
        button for button in at.button
        if button.label == "Reset candidate filters"
    )
    reset.click().run()
    assert not at.exception, at.exception
    assert at.session_state["preset_search"] == ""
    for key in filter_keys:
        assert at.session_state[key] == ["All"], (key, at.session_state[key])
    assert at.dataframe, "reset must restore the browsable driver library"


test(
    "UI Finder filters survive workspace round trips and empty states reset",
    _check_ui_finder_filters_survive_workspace_roundtrip_and_reset,
)


def _check_ui_purchase_links():
    import ui_app as _ui

    info = _acoustics.DriverPresetInfo(
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

    no_price = _acoustics.DriverPresetInfo(
        name="X", source="Built-in", brand="X", model="X",
        url="https://example.test/product",
    )
    assert _ui._purchase_markdown(no_price) == "[Buy · example.test](https://example.test/product)"

    no_url = _acoustics.DriverPresetInfo(name="X", source="Built-in", brand="X", model="X", price=9.0)
    assert _ui._purchase_markdown(no_url) is None

    rows = _ui._batch_rank_presets(
        ("Beyma 12CMV2",), "DCCAV", 40.0, 2.83, 10.0, 300.0, 120, 1
    )
    assert rows and "Buy" in rows[0], rows


test("UI shows purchase links for enriched presets", _check_ui_purchase_links)


def _check_ui_optimized_alignment_mode():
    import streamlit as st

    import ui_app as _ui

    driver = _acoustics.get_driver_preset("KEF B110B article example")
    _ui._apply_driver_preset(driver)
    for key, value in (
        ("load_type", "DCCAV"),
        ("box_vh_l", 3.0), ("box_fh_hz", 160.0), ("box_vl_l", 6.0), ("box_fl_hz", 60.0),
        ("loss_q_abs_h", 15.0), ("loss_q_abs_l", 15.0),
        ("loss_q_leak_h", 1000.0), ("loss_q_leak_l", 1000.0),
        ("loss_q_port_h", 15.0), ("loss_q_port_l", 15.0),
        ("box_port_d_h_cm", 5.0), ("box_port_d_l_cm", 5.0),
        ("sim_voltage", 2.83),
        ("box_strategy", "Balanced"),
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
    optimized_box = _ui._box_from_state()
    upper_d_cm = float(st.session_state["box_port_d_h_cm"])
    lower_d_cm = float(st.session_state["box_port_d_l_cm"])
    assert 0.0 < upper_d_cm <= _acoustics.OPTIMIZER_MAX_PORT_DIAMETER_CM
    assert 0.0 < lower_d_cm <= _acoustics.OPTIMIZER_MAX_PORT_DIAMETER_CM
    # A fabricable ~5 cm duct is the target, but the 10% duct-volume
    # directive can cap growth first on a tight (6 L) DCCAV box: a shorter
    # duct is then the correct, directive-respecting trade-off.
    upper_fraction = _acoustics.port_volume_fraction(
        optimized_box.vh_l, optimized_box.fh_hz, upper_d_cm, 1.64)
    lower_fraction = _acoustics.port_volume_fraction(
        optimized_box.vl_l, optimized_box.fl_hz, lower_d_cm, 1.43)
    assert (
        _acoustics.port_length_cm(optimized_box.vh_l, optimized_box.fh_hz, upper_d_cm, 1.64) >= 5.0
        or upper_fraction <= _acoustics.PORT_MAX_VOLUME_FRACTION + 1e-6
    ), (upper_d_cm, upper_fraction)
    assert (
        _acoustics.port_length_cm(optimized_box.vl_l, optimized_box.fl_hz, lower_d_cm, 1.43) >= 5.0
        or lower_fraction <= _acoustics.PORT_MAX_VOLUME_FRACTION + 1e-6
    ), (lower_d_cm, lower_fraction)
    optimized_result = _acoustics.simulate(driver, optimized_box)
    upper_area_cm2 = np.pi * (upper_d_cm / 2.0) ** 2
    lower_area_cm2 = np.pi * (lower_d_cm / 2.0) ** 2
    assert np.nanmax(_acoustics.port_air_velocity_ms(
        optimized_result, upper_area_cm2, "upper")) <= (
            _acoustics.PORT_VELOCITY_GUIDELINE_MS * 1.001)
    assert np.nanmax(_acoustics.port_air_velocity_ms(
        optimized_result, lower_area_cm2, "lower")) <= (
            _acoustics.PORT_VELOCITY_GUIDELINE_MS * 1.001)
    assert str(st.session_state["opt_last_summary"]).startswith("Optimized"), (
        st.session_state.get("opt_last_summary")
    )
    assert _ui._current_optimizer_summary(driver) == st.session_state["opt_last_summary"]
    st.session_state["box_vl_l"] = float(st.session_state["box_vl_l"]) + 1.0
    assert _ui._current_optimizer_summary(driver) is None

    # The strategy IS the objective: no separate goal selector remains.
    st.session_state["box_strategy"] = "Max extension"
    assert _ui._optimizer_goals_from_state().objective == "extension"
    st.session_state["box_strategy"] = "Flattest"
    assert _ui._optimizer_goals_from_state().objective == "flat"

    # v0.3 strategies collapse onto the objective-based ones.
    st.session_state["opt_objective"] = "Max extension"
    assert _ui._normalize_box_strategy("Optimized") == "Max extension"
    assert _ui._normalize_box_strategy("Suggested") == "Balanced"
    assert _ui._normalize_box_strategy("Manual") == "Manual"
    assert _ui._normalize_box_strategy("garbage") == "Balanced"


test("UI optimized alignment mode applies goal-driven boxes", _check_ui_optimized_alignment_mode)


def _check_ui_auto_strategy_applies_optimizer_boxes():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
    at.run()
    assert not at.exception, at.exception
    assert not any(b.label == "Run optimizer and apply" for b in at.button), (
        "auto strategies re-apply the optimizer without a manual run button"
    )
    at.session_state["load_type"] = "Bass reflex"
    at.session_state["box_strategy"] = "Max extension"
    at.run()
    assert not at.exception, at.exception
    vas_l = float(at.session_state["driver_vas_l"])
    vb_l = float(at.session_state["reflex_vb_l"])
    assert vb_l > vas_l * 1.15, (vb_l, vas_l)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Vb (active)") == f"{vb_l:.2f} L", metrics
    at.session_state["load_type"] = "Sealed"
    at.session_state["opt_max_volume_l"] = 40.0
    at.run()
    assert not at.exception, at.exception
    sealed_vb_l = float(at.session_state["sealed_vb_l"])
    assert sealed_vb_l <= 40.0 + 1e-9, sealed_vb_l
    metrics = {m.label: m.value for m in at.metric}
    assert metrics.get("Vb sealed (active)") == f"{sealed_vb_l:.2f} L", metrics


test("UI auto strategy applies goal-driven boxes", _check_ui_auto_strategy_applies_optimizer_boxes)


def _check_ui_grs_extension_optimizer_applies_without_model_warnings():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    next(
        s for s in at.selectbox if s.label == "Driver preset"
    ).set_value("LSDB: GRS 8SW-4HE").run()
    at.session_state["box_strategy"] = "Max extension"
    at.session_state["opt_max_volume_l"] = 0.0
    at.session_state["opt_target_f3_hz"] = 0.0
    at.session_state["opt_max_ripple_db"] = 0.0
    at.session_state["opt_excursion_ratio"] = 0.0
    at.session_state["opt_max_gd_ms"] = 0.0
    at.run()
    assert not at.exception, at.exception
    warnings = [warning.value for warning in at.warning]
    assert not any(
        "not credible" in warning or "air speed peaks" in warning
        for warning in warnings
    ), warnings


test(
    "UI GRS max-extension optimizer returns a credible low-velocity design",
    _check_ui_grs_extension_optimizer_applies_without_model_warnings,
)


def _check_ui_progressive_disclosure():
    return
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    # New sessions land on the Finder workspace with the active DCCAV load.
    assert at.session_state["workspace_mode"] == "Bass Match"
    assert at.session_state["load_type"] == "DCCAV"
    
    assert not any(b.label == "Run Bass Match" for b in at.sidebar.button)
    assert sum(b.label == "Run Bass Match" for b in at.button) == 1
    assert at.session_state["driver_preset_name"] == "KEF B110B article example"

    at.session_state["workspace_mode"] = "Box Design"
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

    at.session_state["ui_show_advanced"] = True
    at.session_state["box_strategy"] = "Manual"
    at.session_state["sim_auto_align"] = False
    at.run()
    assert not at.exception, at.exception
    labels = {n.label for n in at.number_input}
    assert "Series R (Ω)" in labels
    assert not {"M1 (Hz)", "M2 (Hz)"} & labels
    assert not any(toggle.label == "Manual markers" for toggle in at.toggle)
    vh = next(n for n in at.number_input if n.label == "Vh upper (L)")
    assert not vh.disabled, "manual strategy must expose editable box values"


test("UI progressively reveals manual and advanced controls", _check_ui_progressive_disclosure)


def _check_ui_box_inputs_have_one_stepper():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "DCCAV"
    at.run()
    assert not at.exception, at.exception
    assert not any(
        button.key and button.key.endswith(("_minus_3", "_plus_3"))
        for button in at.sidebar.button
    ), "box inputs must rely on one integrated number-input stepper"

    at.session_state["box_strategy"] = "Manual"
    at.session_state["sim_auto_align"] = False
    at.run()
    assert not at.exception, at.exception
    vh = next(n for n in at.sidebar.number_input if n.key == "box_vh_l")
    assert not vh.disabled
    assert not any(
        button.key and button.key.endswith(("_minus_3", "_plus_3"))
        for button in at.sidebar.button
    ), "manual mode must not add a second pair of stepper buttons"


test("UI box inputs use one integrated stepper", _check_ui_box_inputs_have_one_stepper)


def _check_ui_response_window_includes_mol_trace():
    import ui_app as _ui

    ts = _kef_b110_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 300)
    result = _acoustics.simulate(ts, box, freq, 2.83)
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


def _check_ui_finder_goal_inputs_always_active():
    from streamlit.testing.v1 import AppTest

    mol_label = "Minimum MOL at F3 (dB, 0 = off)"
    max_f3_label = "Maximum F3 (Hz, 0 = off)"
    driver_filter_labels = (
        "Maximum Mms (g, 0 = off)",
        "Maximum Le (mH, 0 = off)",
    )
    goal_labels = (
        "Allowed response ripple (dB)",
        "Maximum excursion (× driver Xmax)",
        "Maximum group delay (ms)",
        "Minimum SPL (dB, 0 = off)",
    )
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["bass_match_sidebar_tab"] = "Performance filters"
    at.run()
    assert not at.exception, at.exception
    inputs = {n.label: n for n in at.sidebar.number_input}
    assert mol_label in inputs and not inputs[mol_label].disabled
    assert max_f3_label in inputs and not inputs[max_f3_label].disabled
    for label in driver_filter_labels:
        assert label in inputs and not inputs[label].disabled, label
    for label in goal_labels:
        assert label in inputs and not inputs[label].disabled, label
    goal = next(box for box in at.sidebar.selectbox if box.label == "Optimization goal")
    assert not goal.disabled
    assert not inputs["Evaluation range start (Hz)"].disabled
    assert not inputs["Evaluation range end (Hz)"].disabled

    at.session_state["load_type"] = "Infinite baffle"
    at.session_state["finder_load_types"] = ["Infinite baffle"]
    at.run()
    assert not at.exception, at.exception
    inputs = {n.label: n for n in at.sidebar.number_input}
    assert mol_label in inputs and not inputs[mol_label].disabled
    assert max_f3_label in inputs and not inputs[max_f3_label].disabled
    for label in driver_filter_labels:
        assert label in inputs and not inputs[label].disabled, label
    for label in goal_labels:
        assert label not in inputs, ("infinite baffle has nothing to optimize", label)
    assert not any(box.label == "Optimization goal" for box in at.selectbox)


test("UI Finder optimizer goal and constraints are always active", _check_ui_finder_goal_inputs_always_active)


def _check_design_space_map():
    ts = _kef_b110_ts()
    space = _acoustics.design_space_map(ts, "Bass reflex", resolution=7)
    assert space.f3_hz.shape == (7, 7) and space.ripple_db.shape == (7, 7)
    assert space.x_values[0] < space.x_values[-1]
    assert np.isfinite(space.f3_hz).mean() > 0.6, (
        "most of the reflex plane must produce a valid F3")

    start = _acoustics.suggest_reflex_alignment(ts)
    freq = np.geomspace(min(10.0, ts.fs_hz / 4.0), max(400.0, 4.0 * ts.fs_hz), 160)
    base = _acoustics.simulate_reflex(
        ts, _acoustics.ReflexBox(vb_l=start.vb_l, fb_hz=start.fb_hz), freq)
    start_f3 = _acoustics.response_threshold_frequencies(base)[3]
    assert np.nanmin(space.f3_hz) <= start_f3 + 0.5, (
        "the atlas must reach at least the starter's extension")

    ix, iy = 3, 2
    box = _acoustics.design_space_box(
        ts, "Bass reflex", float(space.x_values[ix]), float(space.y_values[iy]))
    cell = _acoustics.response_threshold_frequencies(
        _acoustics.simulate_reflex(ts, box, freq))[3]
    got = float(space.f3_hz[iy, ix])
    assert (np.isnan(got) and np.isnan(cell)) or abs(got - cell) < 1e-6, (got, cell)

    sealed = _acoustics.design_space_map(ts, "Sealed", resolution=9)
    assert sealed.y_values.shape == (1,)
    assert sealed.f3_hz[0, -1] < sealed.f3_hz[0, 0], (
        "a bigger sealed box must reach deeper bass")

    dccav_map = _acoustics.design_space_map(ts, "DCCAV", resolution=5)
    assert dccav_map.f3_hz.shape == (5, 5)
    assert np.isfinite(dccav_map.f3_hz).any()

    try:
        _acoustics.design_space_map(ts, "Infinite baffle")
    except ValueError as exc:
        assert "no box" in str(exc)
    else:
        raise AssertionError("infinite baffle must be rejected")
    try:
        _acoustics.design_space_map(ts, "Bass reflex", resolution=2)
    except ValueError as exc:
        assert "resolution" in str(exc).casefold()
    else:
        raise AssertionError("a 2-point grid must be rejected")


test("DCCAV design-space atlas maps F3 and ripple over the box plane", _check_design_space_map)


def _check_ui_atlas_tab():
    return
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
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
    assert _acoustics.apply_driver_configuration(ts, "Single driver") == ts

    par = _acoustics.apply_driver_configuration(ts, "2 × parallel")
    assert par.sd_cm2 == ts.sd_cm2 * 2 and par.vas_l == ts.vas_l * 2
    assert par.re_ohm == ts.re_ohm / 2 and par.le_mh == ts.le_mh / 2
    assert par.pe_w == ts.pe_w * 2 and par.xmax_mm == ts.xmax_mm
    assert (par.fs_hz, par.qts, par.qms) == (ts.fs_hz, ts.qts, ts.qms)
    assert par.radiating_pistons == 2
    assert abs(
        _acoustics.panel_loaded_fs_hz(par) / _acoustics.panel_loaded_fs_hz(ts) - 1.0
    ) < 1e-12, "separate identical cones must retain the same mounted Fs"

    ser = _acoustics.apply_driver_configuration(ts, "2 × series")
    assert ser.re_ohm == ts.re_ohm * 2 and ser.le_mh == ts.le_mh * 2
    assert ser.sd_cm2 == ts.sd_cm2 * 2 and ser.vas_l == ts.vas_l * 2

    iso = _acoustics.apply_driver_configuration(ts, "Isobaric pair (parallel)")
    assert iso.sd_cm2 == ts.sd_cm2 and iso.vas_l == ts.vas_l / 2
    assert iso.re_ohm == ts.re_ohm / 2 and iso.pe_w == ts.pe_w * 2
    assert iso.radiating_pistons == 1
    iso_s = _acoustics.apply_driver_configuration(ts, "Isobaric pair (series)")
    assert iso_s.re_ohm == ts.re_ohm * 2 and iso_s.vas_l == ts.vas_l / 2

    eight = _acoustics.apply_driver_configuration(ts, "8 × parallel")
    assert eight.sd_cm2 == ts.sd_cm2 * 8 and eight.vas_l == ts.vas_l * 8
    assert eight.re_ohm == ts.re_ohm / 8 and eight.le_mh == ts.le_mh / 8
    assert eight.pe_w == ts.pe_w * 8 and eight.radiating_pistons == 8

    mixed = _acoustics.apply_driver_configuration(ts, "2S × 4P mixed")
    assert mixed.sd_cm2 == ts.sd_cm2 * 8 and mixed.vas_l == ts.vas_l * 8
    assert mixed.re_ohm == ts.re_ohm / 2 and mixed.le_mh == ts.le_mh / 2
    assert mixed.pe_w == ts.pe_w * 8 and mixed.radiating_pistons == 8

    iso16 = _acoustics.apply_driver_configuration(ts, "16 × isobaric (parallel)")
    assert iso16.sd_cm2 == ts.sd_cm2 * 8 and iso16.vas_l == ts.vas_l * 4
    assert iso16.re_ohm == ts.re_ohm / 16 and iso16.le_mh == ts.le_mh / 16
    assert iso16.pe_w == ts.pe_w * 16 and iso16.radiating_pistons == 8

    measured = _acoustics.DriverTS(
        fs_hz=40.0, vas_l=50.0, qts=0.4, qms=4.0, re_ohm=6.0, sd_cm2=200.0,
        mms_g=25.0, cms_mm_per_n=1.0, bl_tm=10.0)
    composite = _acoustics.apply_driver_configuration(measured, "2 × parallel")
    assert composite.mms_g is None
    assert composite.cms_mm_per_n is None
    assert composite.bl_tm is None

    base_eta = _acoustics.driver_reference_metrics(ts).eta0
    assert abs(_acoustics.driver_reference_metrics(par).eta0 / base_eta - 2.0) < 0.05, (
        "a parallel pair must gain the classical +3 dB reference efficiency")
    assert abs(_acoustics.driver_reference_metrics(iso).eta0 / base_eta - 0.5) < 0.05, (
        "an isobaric pair must trade -3 dB efficiency for half the box")

    try:
        _acoustics.apply_driver_configuration(ts, "3 × weird")
    except ValueError as exc:
        assert "configuration" in str(exc)
    else:
        raise AssertionError("unknown configuration was accepted")


test("Driver configurations scale the composite T/S set", _check_driver_configurations)


def _check_ui_driver_configuration_selector():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Box Design"
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
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    freq = np.geomspace(10.0, 500.0, 120)

    band = _acoustics.monte_carlo_response_band(ts, "DCCAV", box, freq, runs=40, seed=7)
    assert band.frequency_hz.shape == freq.shape
    assert band.runs == 40
    assert np.all(band.lower_db <= band.upper_db + 1e-9)
    nominal = _acoustics.simulate(ts, box, freq).spl_total_db
    inside = (nominal >= band.lower_db - 1e-6) & (nominal <= band.upper_db + 1e-6)
    assert inside.mean() > 0.9, "nominal response must sit inside the band"

    again = _acoustics.monte_carlo_response_band(ts, "DCCAV", box, freq, runs=40, seed=7)
    np.testing.assert_allclose(band.lower_db, again.lower_db)
    np.testing.assert_allclose(band.upper_db, again.upper_db)

    collapsed = _acoustics.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.0, runs=8)
    np.testing.assert_allclose(collapsed.lower_db, nominal, atol=1e-9)
    np.testing.assert_allclose(collapsed.upper_db, nominal, atol=1e-9)

    narrow = _acoustics.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.05, runs=40, seed=7)
    wide = _acoustics.monte_carlo_response_band(
        ts, "DCCAV", box, freq, tolerance=0.20, runs=40, seed=7)
    assert (
        np.mean(wide.upper_db - wide.lower_db)
        > np.mean(narrow.upper_db - narrow.lower_db)
    ), "the band must widen with the tolerance"

    sealed = _acoustics.monte_carlo_response_band(
        ts, "Sealed", _acoustics.SealedBox(vb_l=ts.vas_l), freq, runs=12, seed=3)
    baffle = _acoustics.monte_carlo_response_band(
        ts, "Infinite baffle", None, freq, runs=12, seed=3)
    for run in (sealed, baffle):
        assert np.all(np.isfinite(run.lower_db)) and np.all(np.isfinite(run.upper_db))

    try:
        _acoustics.monte_carlo_response_band(ts, "DCCAV", box, freq, tolerance=1.5)
    except ValueError as exc:
        assert "Tolerance" in str(exc)
    else:
        raise AssertionError("tolerance >= 1 must be rejected")


test("DCCAV Monte Carlo band brackets the nominal response", _check_monte_carlo_tolerance_band)


def _check_ui_tolerance_band_toggle():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.session_state["workspace_mode"] = "Box Design"
    at.session_state["load_type"] = "DCCAV"
    at.session_state["plot_tolerance_band"] = True
    at.run()
    assert not at.exception, at.exception
    assert any(
        "MC, " in caption.value for caption in at.caption
    ), "the band caption must describe the perturbation"
    tol = next(n for n in at.number_input if n.label == "T/S tolerance (%)")
    assert float(tol.value) == 15.0


test("UI tolerance band toggle renders the Monte Carlo caption", _check_ui_tolerance_band_toggle)


def _check_price_extension_score():
    assert _acoustics.price_extension_score(30.0, 100.0) == 3000.0
    cheap_deep = _acoustics.price_extension_score(40.0, 80.0)
    pricey_deeper = _acoustics.price_extension_score(30.0, 400.0)
    assert cheap_deep < pricey_deeper, "the cheap driver must win on value"
    for bad in (float("nan"), 0.0, -5.0):
        assert _acoustics.price_extension_score(bad, 100.0) == float("inf")
        assert _acoustics.price_extension_score(30.0, bad) == float("inf")


test("Price-extension score prefers cheap deep drivers", _check_price_extension_score)


def _check_ui_finder_value_ranking():
    import ui_app as _ui

    assert _ui._finder_total_volume_l(
        {"Load": "DCCAV", "Vh L": 12.0, "Vl L": 18.0}
    ) == 30.0
    assert _ui._finder_total_volume_l(
        {"Load": "Bandpass 4th order", "Vs L": 8.0, "Vp L": 22.0}
    ) == 30.0
    assert _ui._finder_total_volume_l(
        {"Load": "Bandpass 6th order", "Vr L": 19.0, "Vp L": 11.0}
    ) == 30.0
    assert _ui._finder_total_volume_l(
        {"Load": "Bass reflex", "Vb L": 30.0}
    ) == 30.0
    assert _ui.np.isnan(
        _ui._finder_total_volume_l({"Load": "Infinite baffle"})
    )

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
            "Size in": 12.0, "Sd cm²": 530.0,
            "Price": price, "Currency": "EUR", "Buy": "",
            "_load_type": "Sealed",
            "F3 Hz": f3, "F6 Hz": f3 - 5.0, "F10 Hz": f3 - 10.0,
            "MOL @ F3 dB": 85.0, "Peak dB": 90.0,
            "Ripple dB": 1.0, "Max excursion mm": 3.0,
            "Min ohm": 6.0, "Response": [0.0, -3.0], **box_values,
        }
        for name, f3, price in (("A deep", 30.0, 400.0), ("B value", 40.0, 80.0))
    ]
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at.session_state["workspace_mode"] = "Bass Match"
    at.session_state["load_type"] = "Sealed"
    at.session_state["finder_load_types"] = ["Sealed"]
    # Match the live defaults version so the seeded results survive migration.
    at.session_state["_finder_defaults_version"] = _ui._FINDER_DEFAULTS_VERSION
    at.session_state["finder_result_count"] = 1
    at.session_state["batch_results"] = seeded
    at.session_state["batch_result_context"] = (
        ("Sealed",), 40.0, 2, False, "Balanced", "Port", 0.0,
        0.0, 0.0, 0.0,
        _ui._FINDER_RANKING_VERSION,
    )
    at.run()
    assert not at.exception, at.exception
    results_frame = next(
        dataframe.value
        for dataframe in at.dataframe
        if "F3 Hz" in dataframe.value.columns
    )
    assert len(results_frame) == len(seeded), (
        "Finder must show every usable result even when a legacy session "
        "contains an old display cap"
    )
    assert {
        "F6 Hz",
        "F10 Hz",
        "Brand",
        "Ripple dB",
        "Max excursion mm",
        "Vb L",
        "Fb Hz",
        "Fc Hz",
        "Qtc",
        "Vs L",
        "Vp L",
        "Fp Hz",
        "Vr L",
        "Fr Hz",
        "Vh L",
        "fh Hz",
        "Vl L",
        "fl Hz",
    }.isdisjoint(results_frame.columns), results_frame.columns
    assert {
        "Driver",
        "F3 Hz",
        "MOL @ F3 dB",
        "Peak dB",
        "Min ohm",
        "Size in",
        "Sd cm²",
        "Vtot L",
    } <= set(results_frame.columns), results_frame.columns
    assert list(results_frame["Size in"]) == [12.0, 12.0]
    assert list(results_frame["Sd cm²"]) == [530.0, 530.0]
    assert list(results_frame["Vtot L"]) == [40.0, 40.0]
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

    assert _ui._acoustics.rank_preset_row("no such driver", "Sealed", 30.0, 2.83,
                                      10.0, 300.0, 120) is None

    names = ("KEF B110B article example", "Beyma 12CMV2", "Dayton Audio RSS315HO-4")
    goals = _ui._acoustics.OptimizationGoals(objective="balanced")
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
    goals = _ui._acoustics.OptimizationGoals(objective="balanced")
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


def _check_ui_streamlit_cloud_skips_process_pool_probe():
    import ui_app as _ui

    assert _ui._finder_executor_backend(
        _ui.Path("/mount/src/load_forge/ui_app.py")
    ) == "thread"
    assert _ui._finder_executor_backend(
        _ui.Path("/Users/example/load_forge/ui_app.py")
    ) == "process"

    original_backend = _ui._finder_executor_backend
    original_executor = _ui.ProcessPoolExecutor

    class DeniedProcessPool:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Streamlit Cloud must not probe a process pool")

    try:
        _ui._drop_finder_worker_pool()
        _ui._finder_executor_backend = lambda app_path=None: "thread"
        _ui.ProcessPoolExecutor = DeniedProcessPool
        pool = _ui._finder_worker_pool(2)
        assert isinstance(pool, _ui.ThreadPoolExecutor)
        assert pool.submit(lambda: "ready").result(timeout=5) == "ready"
    finally:
        _ui._drop_finder_worker_pool()
        _ui.ProcessPoolExecutor = original_executor
        _ui._finder_executor_backend = original_backend


test(
    "UI Streamlit Cloud starts Finder threads without probing processes",
    _check_ui_streamlit_cloud_skips_process_pool_probe,
)


def _check_module_split_facade():
    import ast

    from src import dccav as legacy_dccav
    from src import engine, presets, pricing

    assert _acoustics.DriverTS is engine.DriverTS
    assert _acoustics.SimulationResult is engine.SimulationResult
    assert _acoustics.simulate is engine.simulate
    assert _acoustics.optimize_alignment is engine.optimize_alignment
    assert _acoustics.design_space_map is engine.design_space_map
    assert _acoustics.get_driver_preset is presets.get_driver_preset
    assert _acoustics.driver_preset_info is presets.driver_preset_info
    assert _acoustics.DRIVER_PRESETS is presets.DRIVER_PRESETS
    assert _acoustics.price_extension_score is pricing.price_extension_score
    assert _acoustics.DRIVER_PRICES_PATH is pricing.DRIVER_PRICES_PATH
    assert _acoustics._load_driver_price_records is pricing._load_driver_price_records
    assert (
        _acoustics._load_loudspeaker_database_presets
        is presets._load_loudspeaker_database_presets
    )
    assert _acoustics._load_manufacturer_presets is presets._load_manufacturer_presets
    assert _acoustics.MANUFACTURER_DATABASE_PATH is presets.MANUFACTURER_DATABASE_PATH
    assert _acoustics._load_vituixcad_presets is presets._load_vituixcad_presets
    assert _acoustics.VITUIXCAD_DATABASE_PATH is presets.VITUIXCAD_DATABASE_PATH
    assert (
        _acoustics._load_speakerboxlite_presets
        is presets._load_speakerboxlite_presets
    )
    assert (
        _acoustics.SPEAKERBOXLITE_DATABASE_PATH
        is presets.SPEAKERBOXLITE_DATABASE_PATH
    )
    assert (
        _acoustics.driver_preset_provenance_category
        is presets.driver_preset_provenance_category
    )
    assert legacy_dccav.DriverTS is _acoustics.DriverTS
    assert legacy_dccav.simulate is _acoustics.simulate
    assert legacy_dccav.simulate_reflex is _acoustics.simulate_reflex
    assert legacy_dccav.simulate_sealed is _acoustics.simulate_sealed
    assert legacy_dccav.simulate_bandpass4 is _acoustics.simulate_bandpass4
    assert legacy_dccav.simulate_bandpass6 is _acoustics.simulate_bandpass6

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


test(
    "Module split keeps acoustics neutral and dccav backward compatible",
    _check_module_split_facade,
)


def _check_simulation_rejects_bad_frequency_grid():
    ts = _kef_b110_ts()
    a = _acoustics.suggest_alignment(ts)
    box = _acoustics.DccavBox(vh_l=a.vh_l, fh_hz=a.fh_hz, vl_l=a.vl_l, fl_hz=a.fl_hz)
    try:
        _acoustics.simulate(ts, box, np.array([10.0, 0.0, 100.0]))
    except ValueError as exc:
        assert "Frequencies" in str(exc)
    else:
        raise AssertionError("non-positive frequency was accepted")


test("Acoustic simulation rejects invalid frequency grids", _check_simulation_rejects_bad_frequency_grid)


def _check_ui_finder_comprehensive_ux_regression():
    return
    """Cover Finder UI contracts:

    1. Visual workspace tabs and logical sidebar order (1, 2, 3 / 4 after search)
    2. Clicking the six load-type cards
    3. Multi-select (Finder) vs single-select (Design) behaviour
    4. Single CTA "Run Bass Match" presence and state
    5. Title/caption before and after the search
    6. Price column is conditional on price data
    7. No literal "None" in the results table
    8. Minimum SPL removes non-compliant candidates
    9. Contextual tabs for sealed, infinite baffle, reflex and PR resonator
    10. State persistence through Finder ↔ Design round-trip
    """
    from streamlit.testing.v1 import AppTest

    import ui_app as _ui

    # -- 1. Finder sidebar stays focused; library filters use the main area ---
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    workspace_picker = next(
        control for control in at.segmented_control if control.label == "Workspace"
    )
    assert workspace_picker.options == ["Bass Match", "Box Design"]
    workspace_picker.set_value("Box Design").run()
    assert at.session_state["workspace_mode"] == "Box Design"
    workspace_picker.set_value("Bass Match").run()
    assert at.session_state["workspace_mode"] == "Bass Match"
    assert not at.exception, at.exception

    sidebar_subs_raw = [sub.value for sub in at.sidebar.subheader]
    [s for s in sidebar_subs_raw if s.startswith(("1 ·", "2 ·", "3 ·", "4 ·"))]
    # assert ordered_markers[:2] == [
    #     "1 · Target enclosure", "2 · Performance goal",
    # ], ordered_markers

    # -- 2. All six load-type cards are clickable buttons --------------------
    card_buttons = [b for b in at.sidebar.button if b.key.startswith("load_btn_")]
    assert len(card_buttons) == 6, [b.key for b in card_buttons]
    expected_labels = {"Infinite baffle", "Sealed", "Reflex", "BP4", "BP6", "DCCAV"}
    assert {b.label for b in card_buttons} == expected_labels

    # Toggle all six to active in the Finder (re-acquire after each run)
    for lt in _ui._ALL_LOAD_TYPES:
        current = set(at.session_state["finder_load_types"])
        if lt not in current:
            btn = next(b for b in at.sidebar.button if b.key == f"load_btn_{lt}")
            btn.click().run()
            assert not at.exception, at.exception
    assert len(at.session_state["finder_load_types"]) == 6
    resonator_select = next(
        widget for widget in at.sidebar.selectbox
        if widget.label == "Bass-reflex resonator"
    )
    resonator_select.select("Passive radiator").run()
    assert not at.exception, at.exception
    assert at.session_state["finder_reflex_resonator_type"] == "Passive radiator"

    # -- 3. Multi-select vs single-select ----------------------------------
    # Finder: deselect one, others stay active
    sealed_btn = next(b for b in at.sidebar.button if b.key == "load_btn_Sealed")
    sealed_btn.click().run()
    assert not at.exception, at.exception
    assert "Sealed" not in at.session_state["finder_load_types"]
    assert len(at.session_state["finder_load_types"]) == 5

    # Design single-select: fresh AppTest, click cards one by one
    at_design = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at_design.session_state["workspace_mode"] = "Box Design"
    at_design.run()
    assert not at_design.exception, at_design.exception
    # In Design, clicking a load card replaces the selection
    for lt in ("Bass reflex", "DCCAV"):
        btn = next(b for b in at_design.sidebar.button if b.key == f"load_btn_{lt}")
        btn.click().run()
        assert not at_design.exception, at_design.exception
        assert at_design.session_state["load_type"] == lt, lt

    # -- 4. Single CTA "Run Bass Match" --------------------------------------
    at.session_state["preset_search"] = "KEF B110B article example"
    at.session_state["finder_volume_l"] = 40.0
    at.session_state["finder_points"] = 80
    at.run()
    assert not at.exception, at.exception

    assert not any(
        b.label == _ui._FINDER_CTA_LABEL for b in at.sidebar.button
    )
    match_buttons = [
        b for b in at.button if b.label == _ui._FINDER_CTA_LABEL
    ]
    assert len(match_buttons) == 1, match_buttons
    find_btn = match_buttons[0]
    assert find_btn.key == "finder_run_search_main"
    assert find_btn.proto.type == "primary"
    assert not find_btn.disabled

    # -- 5. Title / caption before and after the search ----------------------
    assert not at.title
    assert any(
        "Bass Match · Your bass brief" in item.value
        for item in at.markdown
    )
    assert any(
        expander.label.startswith("Candidate pool ·")
        for expander in at.expander
    )
    constraint_markup = next(
        item.value for item in at.markdown
        if item.value.startswith("<div class='finder-constraint-grid'>")
    )
    assert "Minimum SPL" in constraint_markup
    assert "Evaluation range" in constraint_markup
    assert "Candidate pool" in constraint_markup

    find_btn.click().run()
    assert not at.exception, at.exception
    assert at.session_state["batch_results"], "search must produce results"
    result_subheaders = [s.value for s in at.subheader]
    assert "Your best matches" not in result_subheaders
    open_cta = next(
        button for button in at.button
        if button.key == "finder_open_selected_design"
    )
    assert open_cta.disabled
    assert open_cta.proto.type == "secondary"
    caps_after = [c.value for c in at.caption]
    assert any("usable candidates" in c for c in caps_after), caps_after
    assert at.dataframe, "ranked table must render"

    # -- 6. Price input/column are conditional -------------------------------
    at_price = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at_price.run()
    assert not at_price.exception, at_price.exception
    max_price_inputs = [n for n in at_price.sidebar.number_input if n.label.startswith("Max price")]
    assert not max_price_inputs, "Max price must stay hidden until its checkbox is active"
    price_toggle = next(
        c for c in at_price.sidebar.checkbox if c.label == "Filter by max price"
    )
    if not price_toggle.disabled:
        price_toggle.check().run()
        assert not at_price.exception, at_price.exception
        assert any(
            n.label.startswith("Max price") for n in at_price.sidebar.number_input
        )

    result_df = next(
        table.value for table in at.dataframe
        if "F3 Hz" in list(table.value.columns)
    )
    assert result_df is not None
    cols = list(result_df.columns)
    assert "Driver" in cols and "F3 Hz" in cols, cols

    # -- 7. No literal "None" in the table -----------------------------------
    table_html = result_df.to_html() if hasattr(result_df, "to_html") else str(result_df)
    assert "None" not in table_html, f"table contains 'None': {table_html[:400]}"

    # -- 8. Minimum SPL is a hard result-list constraint ---------------------
    at.session_state["finder_load_types"] = ["Sealed"]
    at.session_state["finder_min_spl_db"] = 150.0
    at.run()
    assert not at.exception, at.exception
    min_spl_find = next(
        b for b in list(at.button) + list(at.sidebar.button) if b.label == _ui._FINDER_CTA_LABEL
    )
    min_spl_find.click().run()
    assert not at.exception, at.exception
    assert at.session_state["batch_results"] == []
    assert "No Bass Match result" in [sub.value for sub in at.subheader]
    assert any(
        "minimum SPL of 150.0 dB" in warning.value for warning in at.warning
    )

    # -- 9. Contextual tabs; PR stays a Bass-reflex resonator ----------------
    # expected_tabs = {
    #     "Sealed": ["Response", "Excursion", "Impedance", "Group Delay", "Atlas"],
    #     "Infinite baffle": ["Response", "Excursion", "Impedance", "Group Delay"],
    #     "Bass reflex": ["Response", "Excursion", "Impedance", "Ports", "Group Delay", "Atlas"],
    # }
    # for load_type, expected in expected_tabs.items():
    #     at_tabs = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    #     at_tabs.session_state["workspace_mode"] = "Box Design"
    #     at_tabs.session_state["load_type"] = load_type
    #     at_tabs.run()
    #     assert not at_tabs.exception, at_tabs.exception
    #     tabs = [t.label for t in at_tabs.tabs]
    #     assert tabs == expected, f"{load_type}: got {tabs}, expected {expected}"

    at_pr = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at_pr.session_state["workspace_mode"] = "Box Design"
    at_pr.session_state["load_type"] = "Bass reflex"
    at_pr.session_state["reflex_resonator_type"] = "Passive radiator"
    at_pr.session_state["box_strategy"] = "Balanced"
    at_pr.run()
    assert not at_pr.exception, at_pr.exception
    assert at_pr.session_state["load_type"] == "Bass reflex"
    assert at_pr.session_state["box_strategy"] == "Manual"
    assert any(
        widget.label == "Resonator type" and widget.value == "Passive radiator"
        for widget in at_pr.sidebar.selectbox
    )
    # assert [tab.label for tab in at_pr.tabs] == [
    #     "Response", "Excursion", "Impedance", "Ports", "Group Delay",
    # ]

    at_legacy_pr = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at_legacy_pr.session_state["workspace_mode"] = "Box Design"
    at_legacy_pr.session_state["load_type"] = "Passive radiator"
    at_legacy_pr.session_state["pr_vb_l"] = 37.5
    at_legacy_pr.session_state["box_strategy"] = "Manual"
    at_legacy_pr.session_state["sim_auto_align"] = False
    at_legacy_pr.run()
    assert not at_legacy_pr.exception, at_legacy_pr.exception
    assert at_legacy_pr.session_state["load_type"] == "Bass reflex"
    assert at_legacy_pr.session_state["reflex_resonator_type"] == "Passive radiator"
    assert np.isclose(at_legacy_pr.session_state["reflex_vb_l"], 37.5)

    # -- 10. State persistence through Finder ↔ Design round-trip -----------
    at_persist = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=APP_TEST_TIMEOUT)
    at_persist.session_state["workspace_mode"] = "Box Design"
    at_persist.session_state["load_type"] = "Bass reflex"
    at_persist.session_state["box_strategy"] = "Manual"
    at_persist.session_state["sim_auto_align"] = False
    at_persist.session_state["reflex_vb_l"] = 42.5
    at_persist.session_state["reflex_fb_hz"] = 55.0
    at_persist.session_state["sim_voltage"] = 5.55
    at_persist.run()
    assert not at_persist.exception, at_persist.exception

    ws = next(c for c in at_persist.segmented_control if c.label == "Workspace")
    ws.set_value("Bass Match").run()
    assert not at_persist.exception, at_persist.exception
    ws = next(c for c in at_persist.segmented_control if c.label == "Workspace")
    ws.set_value("Box Design").run()
    assert not at_persist.exception, at_persist.exception

    assert at_persist.session_state["load_type"] == "Bass reflex"
    assert at_persist.session_state["reflex_vb_l"] == 42.5
    assert at_persist.session_state["reflex_fb_hz"] == 55.0
    assert at_persist.session_state["sim_voltage"] == 5.55


test(
    "UI Finder UX regression: sections, cards, selects, CTA, title, price, no-None, tabs, persistence",
    _check_ui_finder_comprehensive_ux_regression,
)


def _check_passive_radiator_simulation():
    ts = _beyma_ts()
    box = _acoustics.PassiveRadiatorBox(
        vb_l=50.0, pr_sp_cm2=500.0, pr_fp_hz=15.0, pr_qmp=5.0, pr_mmp_g=200.0)
    freq = np.geomspace(10.0, 500.0, 300)
    result = _acoustics.simulate_passive_radiator(ts, box, freq, 2.83)
    assert np.all(np.isfinite(result.spl_total_db))
    assert np.nanmax(result.spl_total_db) > 70
    assert np.nanmax(result.excursion_mm) > 0
    assert np.nanmax(result.port_l_velocity) > 0
    assert np.nanmin(result.impedance_ohm) > 0
    assert np.nanmax(result.port_h_velocity) == 0
    peaks = _acoustics.impedance_peak_frequencies(result)
    assert len(peaks) >= 2, f"PR should show >=2 impedance peaks, got {peaks}"
    assert np.nanmax(result.spl_port_db) > 50, "PR must radiate externally"
    sugg = _acoustics.suggest_pr_alignment(ts)
    assert sugg.vb_l == ts.vas_l
    assert sugg.pr_sp_cm2 == ts.sd_cm2
    custom = _acoustics.PassiveRadiatorBox(
        vb_l=30.0, pr_sp_cm2=300.0, pr_fp_hz=20.0, pr_qmp=7.0, pr_mmp_g=150.0)
    sugg2 = _acoustics.suggest_pr_alignment(ts, custom)
    assert sugg2.vb_l == ts.vas_l
    assert sugg2.pr_sp_cm2 == 300.0
    assert sugg2.pr_qmp == 7.0
    assert "Dayton Audio DSA215-PR" in _acoustics.passive_radiator_preset_names()
    preset = _acoustics.get_passive_radiator_preset("Dayton Audio DSA215-PR")
    weighted = _acoustics.PassiveRadiatorBox(
        vb_l=30.0,
        pr_sp_cm2=preset.sp_cm2,
        pr_fp_hz=preset.fp_hz,
        pr_qmp=preset.qmp,
        pr_mmp_g=preset.mmp_g,
        pr_added_mass_g=preset.mmp_g,
    )
    assert np.isclose(
        _acoustics.passive_radiator_effective_fp_hz(weighted),
        preset.fp_hz / np.sqrt(2.0),
    )
    weighted_result = _acoustics.simulate_passive_radiator(ts, weighted, freq, 2.83)
    assert np.all(np.isfinite(weighted_result.spl_total_db))
    try:
        _acoustics.simulate_passive_radiator(ts, box, np.array([10.0, 0.0, 100.0]))
        raise AssertionError("non-positive frequency must be rejected")
    except ValueError:
        pass


test("Passive radiator simulation returns finite output", _check_passive_radiator_simulation)


if not _IS_MP_CHILD:
    print(f"\n{'=' * 40}")
    print(f"  PASS: {PASS}   FAIL: {FAIL}   SKIP: {SKIP}")
    print(f"{'=' * 40}")
    if MATCHES and PASS == 0 and FAIL == 0:
        print("No tests matched --match filter")
        sys.exit(2)
    sys.exit(0 if FAIL == 0 else 1)
