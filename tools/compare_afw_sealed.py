#!/usr/bin/env python3
"""Compare AFW v2 sealed/BP4/BP6 projects with Load Forge.

The read-only parser targets the first transducer slot.  Besides the original
sealed scalar comparison, it recognizes AFW load codes 3 (carico simmetrico,
fourth-order bandpass) and 4 (doppio reflex parallelo, sixth-order bandpass),
and can exercise every Load Forge identical-driver configuration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import engine as _engine  # noqa: E402


@dataclass(frozen=True)
class AfwDriver:
    name: str
    re_ohm: float
    fs_hz: float
    qms: float
    qes: float
    qts: float
    vas_l: float
    le_10khz_mh: float
    le_exponent: float
    le_phase_factor: float
    xmax_mm: float
    pe_w: float
    sd_cm2: float


@dataclass(frozen=True)
class AfwSealed:
    volume_l: float
    volume_factor: float
    resonance_hz: float
    qt: float
    q_loss: float


@dataclass(frozen=True)
class AfwBandpass:
    order: int
    rear_volume_l: float
    rear_volume_factor: float
    rear_frequency_hz: float
    front_volume_l: float
    front_volume_factor: float
    front_tuning_hz: float
    q_abs_rear: float
    q_leak_rear: float
    q_abs_front: float
    q_leak_front: float
    q_port_rear: float
    q_port_front: float


def _number(text: str) -> float:
    return float(text.strip())


def _find_driver_block(lines: list[str]) -> tuple[int, AfwDriver]:
    """Find the first embedded 201-point CRW block and its trailing T/S set."""
    for title_index, title in enumerate(lines):
        if not title.strip() or title.strip().lower().startswith("dummy"):
            continue
        try:
            _number(title)
        except ValueError:
            pass
        else:
            # A CRW title is textual. Without this guard a numeric curve value
            # can look like a valid shifted block because AFW pads unused slots
            # with long runs of zeroes.
            continue
        params_at = title_index + 1 + 201 * 5
        if params_at + 11 > len(lines):
            continue
        try:
            # All 1005 curve values must be numeric.  This excludes ordinary
            # AFW path/header text without relying on a driver-name convention.
            for value in lines[title_index + 1 : params_at]:
                _number(value)
            raw = [_number(value) for value in lines[params_at : params_at + 11]]
        except ValueError:
            continue

        re_ohm, fs_hz, qms, qes, vas_m3, le_h, exponent, phase, xmax_m, pe_w, sd_m2 = raw
        if not (
            0.1 <= re_ohm <= 100
            and 1 <= fs_hz <= 5000
            and qms > 0
            and qes > 0
            and 1e-6 <= vas_m3 <= 100
            and 1e-6 <= sd_m2 <= 1
        ):
            continue
        qts = qms * qes / (qms + qes)
        return title_index, AfwDriver(
            name=title.strip(),
            re_ohm=re_ohm,
            fs_hz=fs_hz,
            qms=qms,
            qes=qes,
            qts=qts,
            vas_l=vas_m3 * 1000.0,
            le_10khz_mh=le_h * 1000.0,
            le_exponent=exponent,
            le_phase_factor=phase,
            xmax_mm=xmax_m * 1000.0,
            pe_w=pe_w,
            sd_cm2=sd_m2 * 10_000.0,
        )
    raise ValueError("No embedded AFW/CRW driver block found")


def parse_afw_sealed(path: Path) -> tuple[AfwDriver, AfwSealed]:
    lines = path.read_text(encoding="latin-1").splitlines()
    driver_at, driver = _find_driver_block(lines)

    # AFW v2 stores the first transducer's sealed alignment 485 lines before
    # its embedded CRW title: Vb [m3], virtual-volume factor, Fc, Qt, Qloss.
    sealed_at = driver_at - 485
    if sealed_at < 0:
        raise ValueError("AFW project is too short for a slot-1 sealed block")
    try:
        volume_m3, factor, resonance, qt, q_loss = (
            _number(lines[sealed_at + offset]) for offset in range(5)
        )
    except ValueError as exc:
        raise ValueError("AFW slot-1 sealed block is not numeric") from exc
    if not (
        0.00005 <= volume_m3 <= 100
        and 1.0 <= factor <= 1.4
        and 1 <= resonance <= 5000
        and 0.01 <= qt <= 20
        and 1 <= q_loss <= 200
    ):
        raise ValueError("AFW slot-1 sealed block failed format validation")
    return driver, AfwSealed(
        volume_l=volume_m3 * 1000.0,
        volume_factor=factor,
        resonance_hz=resonance,
        qt=qt,
        q_loss=q_loss,
    )


def parse_afw_project(path: Path) -> tuple[AfwDriver, AfwSealed | AfwBandpass]:
    """Parse the active first-slot AFW sealed, BP4 or BP6 load."""
    lines = path.read_text(encoding="latin-1").splitlines()
    driver_at, driver = _find_driver_block(lines)
    code_at = driver_at - 490
    if code_at < 0:
        raise ValueError("AFW project is too short for a slot-1 load code")
    try:
        load_code = int(_number(lines[code_at]))
    except (ValueError, OverflowError) as exc:
        raise ValueError("AFW slot-1 load code is not numeric") from exc
    if load_code == 1:
        _, sealed = parse_afw_sealed(path)
        return driver, sealed
    if load_code not in {3, 4}:
        names = {2: "bass reflex", 6: "double-reflex series / DCAAV"}
        detail = names.get(load_code, "unknown")
        raise ValueError(
            f"AFW load code {load_code} ({detail}) is outside this comparator's "
            "sealed/BP4/BP6 scope"
        )

    block_at = driver_at - 230
    if block_at < 0 or block_at + 26 > len(lines):
        raise ValueError("AFW project is too short for a slot-1 bandpass block")
    try:
        raw = [_number(value) for value in lines[block_at : block_at + 26]]
    except ValueError as exc:
        raise ValueError("AFW slot-1 bandpass block is not numeric") from exc
    if not (
        0.00005 <= raw[0] <= 100
        and 0.00005 <= raw[5] <= 100
        and 1.0 <= raw[2] <= 1.4
        and 1.0 <= raw[7] <= 1.4
        and 1 <= raw[6] <= 5000
    ):
        raise ValueError("AFW slot-1 bandpass block failed format validation")
    return driver, AfwBandpass(
        order=4 if load_code == 3 else 6,
        rear_volume_l=raw[0] * 1000.0,
        rear_volume_factor=raw[2],
        rear_frequency_hz=raw[1],
        front_volume_l=raw[5] * 1000.0,
        front_volume_factor=raw[7],
        front_tuning_hz=raw[6],
        q_abs_rear=raw[3],
        q_leak_rear=raw[4],
        q_abs_front=raw[8],
        q_leak_front=raw[9],
        q_port_rear=raw[14],
        q_port_front=raw[25],
    )


def _driver_ts(driver: AfwDriver, configuration: str = "Single driver") -> _engine.DriverTS:
    ts = _engine.DriverTS(
        fs_hz=driver.fs_hz,
        vas_l=driver.vas_l,
        qts=driver.qts,
        qms=driver.qms,
        re_ohm=driver.re_ohm,
        sd_cm2=driver.sd_cm2,
        le_mh=driver.le_10khz_mh,
        xmax_mm=driver.xmax_mm,
        pe_w=driver.pe_w,
    )
    return _engine.apply_driver_configuration(ts, configuration)


def compare_bandpass(
    driver: AfwDriver,
    bandpass: AfwBandpass,
    configuration: str = "Single driver",
) -> dict[str, object]:
    """Simulate an AFW BP4/BP6 alignment and return reproducible diagnostics."""
    ts = _driver_ts(driver, configuration)
    rear_l = bandpass.rear_volume_l * bandpass.rear_volume_factor
    front_l = bandpass.front_volume_l * bandpass.front_volume_factor
    frequency_hz = np.geomspace(10.0, 1000.0, 4000)
    if bandpass.order == 4:
        box: _engine.Bandpass4Box | _engine.Bandpass6Box = _engine.Bandpass4Box(
            vs_l=rear_l,
            vp_l=front_l,
            fp_hz=bandpass.front_tuning_hz,
            q_abs_s=bandpass.q_abs_rear,
            q_leak_s=bandpass.q_leak_rear,
            q_abs_p=bandpass.q_abs_front,
            q_leak_p=bandpass.q_leak_front,
            q_port=bandpass.q_port_front,
        )
        result = _engine.simulate_bandpass4(ts, box, frequency_hz)
        suggested = _engine.suggest_bandpass4_alignment(ts)
        suggested_values = asdict(suggested)
    elif bandpass.order == 6:
        box = _engine.Bandpass6Box(
            vr_l=rear_l,
            fr_hz=bandpass.rear_frequency_hz,
            vp_l=front_l,
            fp_hz=bandpass.front_tuning_hz,
            q_abs_r=bandpass.q_abs_rear,
            q_leak_r=bandpass.q_leak_rear,
            q_abs_p=bandpass.q_abs_front,
            q_leak_p=bandpass.q_leak_front,
            q_port_r=bandpass.q_port_rear,
            q_port_p=bandpass.q_port_front,
        )
        result = _engine.simulate_bandpass6(ts, box, frequency_hz)
        suggested = _engine.suggest_bandpass6_alignment(ts)
        suggested_values = asdict(suggested)
    else:
        raise ValueError(f"Unsupported bandpass order: {bandpass.order}")

    peak_index = int(np.argmax(result.spl_total_db))
    target = float(result.spl_total_db[peak_index] - 3.0)
    low_f3 = _engine._low_side_crossing(
        result.frequency_hz[: peak_index + 1],
        result.spl_total_db[: peak_index + 1],
        target,
    )
    high_f3 = _engine._high_side_crossing(
        result.frequency_hz[peak_index:], result.spl_total_db[peak_index:], target
    )
    added_mass_g, mounted_fs_hz = _engine.panel_air_load_metrics(ts)
    return {
        "driver": asdict(driver),
        "driver_configuration": configuration,
        "composite_driver": asdict(ts),
        "afw_bandpass": asdict(bandpass),
        "load_forge_box": asdict(box),
        "load_forge_suggested": suggested_values,
        "load_forge_simulation": {
            "panel_added_mass_g": added_mass_g,
            "panel_loaded_fs_hz": mounted_fs_hz,
            "peak_spl_db": float(result.spl_total_db[peak_index]),
            "peak_frequency_hz": float(result.frequency_hz[peak_index]),
            "low_f3_hz": float(low_f3),
            "high_f3_hz": float(high_f3),
            "minimum_impedance_ohm": float(np.min(result.impedance_ohm)),
            "impedance_peaks_hz": _engine.impedance_peak_frequencies(result),
        },
    }


def compare(driver: AfwDriver, sealed: AfwSealed) -> dict[str, object]:
    virtual_volume_l = sealed.volume_l * sealed.volume_factor
    ratio = math.sqrt(1.0 + driver.vas_l / virtual_volume_l)
    lf_fc = driver.fs_hz * ratio
    lf_qtc_classical = driver.qts * ratio

    ts = _engine.DriverTS(
        fs_hz=driver.fs_hz,
        vas_l=driver.vas_l,
        qts=driver.qts,
        qms=driver.qms,
        re_ohm=driver.re_ohm,
        sd_cm2=driver.sd_cm2,
    )
    panel_added_mass_g, panel_loaded_fs_hz = _engine.panel_air_load_metrics(ts)
    panel_loaded_fc_hz, panel_loaded_qtc = _engine.sealed_system_metrics(
        ts, _engine.SealedBox(vb_l=virtual_volume_l)
    )

    # AFW combines the box/absorbent loss with the loaded mechanical Q.
    # This analytical value is reported separately because Load Forge's public
    # sealed_system_metrics() deliberately returns the classical lossless Qtc.
    qe_loaded = driver.qes * ratio
    qm_loaded = driver.qms * ratio
    qm_with_loss = 1.0 / (1.0 / qm_loaded + 1.0 / sealed.q_loss)
    qtc_with_loss = 1.0 / (1.0 / qe_loaded + 1.0 / qm_with_loss)

    def delta_percent(load_forge: float, afw: float) -> float:
        return 100.0 * (load_forge / afw - 1.0)

    return {
        "driver": asdict(driver),
        "afw_sealed": asdict(sealed),
        "load_forge": {
            "classical_fc_hz": lf_fc,
            "classical_qtc": lf_qtc_classical,
            "loss_aware_qtc": qtc_with_loss,
            "panel_coupling": ts.panel_coupling,
            "panel_added_mass_g": panel_added_mass_g,
            "panel_loaded_fs_hz": panel_loaded_fs_hz,
            "panel_loaded_fc_hz": panel_loaded_fc_hz,
            "panel_loaded_qtc": panel_loaded_qtc,
        },
        "delta_percent": {
            "classical_fc_vs_afw": delta_percent(lf_fc, sealed.resonance_hz),
            "panel_loaded_fc_vs_afw": delta_percent(
                panel_loaded_fc_hz, sealed.resonance_hz
            ),
            "classical_qtc_vs_afw": delta_percent(lf_qtc_classical, sealed.qt),
            "loss_aware_qtc_vs_afw": delta_percent(qtc_with_loss, sealed.qt),
        },
    }


def _print_report(report: dict[str, object]) -> None:
    driver = report["driver"]
    afw = report["afw_sealed"]
    lf = report["load_forge"]
    delta = report["delta_percent"]
    assert isinstance(driver, dict)
    assert isinstance(afw, dict)
    assert isinstance(lf, dict)
    assert isinstance(delta, dict)
    print(f"Driver: {driver['name']}")
    print(
        "T/S: "
        f"Fs {driver['fs_hz']:.4g} Hz | Vas {driver['vas_l']:.4g} L | "
        f"Qts {driver['qts']:.6f}"
    )
    print(
        "AFW sealed: "
        f"Vb {afw['volume_l']:.4g} L | factor {afw['volume_factor']:.4g} | "
        f"Fc {afw['resonance_hz']:.4f} Hz | Qt {afw['qt']:.6f} | "
        f"Qloss {afw['q_loss']:.4g}"
    )
    print(
        "Load Forge classical: "
        f"classical Fc {lf['classical_fc_hz']:.4f} Hz | "
        f"classical Qtc {lf['classical_qtc']:.6f} | "
        f"loss-aware Qtc {lf['loss_aware_qtc']:.6f}"
    )
    print(
        "Load Forge panel-loaded: "
        f"coupling {lf['panel_coupling']:.2f} | "
        f"added mass {lf['panel_added_mass_g']:.4f} g | "
        f"mounted Fs {lf['panel_loaded_fs_hz']:.4f} Hz | "
        f"Fc {lf['panel_loaded_fc_hz']:.4f} Hz"
    )
    print(
        "Delta vs AFW: "
        f"classical Fc {delta['classical_fc_vs_afw']:+.3f}% | "
        f"panel-loaded Fc {delta['panel_loaded_fc_vs_afw']:+.3f}% | "
        f"classical Qtc {delta['classical_qtc_vs_afw']:+.3f}% | "
        f"loss-aware Qtc {delta['loss_aware_qtc_vs_afw']:+.3f}%"
    )


def _print_bandpass_report(report: dict[str, object]) -> None:
    driver = report["driver"]
    afw = report["afw_bandpass"]
    box = report["load_forge_box"]
    simulation = report["load_forge_simulation"]
    assert all(isinstance(item, dict) for item in (driver, afw, box, simulation))
    order = int(afw["order"])
    print(f"Driver: {driver['name']} | {report['driver_configuration']}")
    print(
        f"AFW BP{order}: rear {box['vr_l' if order == 6 else 'vs_l']:.4g} L"
        + (f" / {box['fr_hz']:.4g} Hz" if order == 6 else " sealed")
        + f" | front {box['vp_l']:.4g} L / {box['fp_hz']:.4g} Hz"
    )
    peaks = ", ".join(f"{value:.2f}" for value in simulation["impedance_peaks_hz"])
    print(
        "Load Forge: "
        f"mounted Fs {simulation['panel_loaded_fs_hz']:.3f} Hz | "
        f"peak {simulation['peak_spl_db']:.2f} dB @ "
        f"{simulation['peak_frequency_hz']:.2f} Hz | "
        f"F3 {simulation['low_f3_hz']:.2f}--{simulation['high_f3_hz']:.2f} Hz"
    )
    print(f"Impedance peaks: {peaks} Hz")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="AFW v2 .afw project")
    parser.add_argument(
        "--configuration",
        choices=_engine.DRIVER_CONFIGURATIONS,
        default="Single driver",
        help="identical-driver configuration exercised by Load Forge",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    driver, load = parse_afw_project(args.project)
    if isinstance(load, AfwSealed):
        if args.configuration != "Single driver":
            parser.error("multi-driver projection is currently available for BP4/BP6")
        report = compare(driver, load)
    else:
        report = compare_bandpass(driver, load, args.configuration)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if isinstance(load, AfwSealed):
            _print_report(report)
        else:
            _print_bandpass_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
