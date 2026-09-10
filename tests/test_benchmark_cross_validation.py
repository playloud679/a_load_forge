"""Automated test verifying Load Forge simulation congruence against WinISD and VituixCAD."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from benchmark_cross_validation import run_benchmark_suite


def test_acoustic_cross_validation_against_external_software():
    """Verify that Load Forge simulation output matches WinISD & VituixCAD within strict tolerance."""
    all_passed, report_str, results = run_benchmark_suite(generate_plots=False)
    assert all_passed, f"Cross-validation against external benchmarks failed:\n{report_str}"
    
    # Assert minimum aggregate quality standards
    for r in results:
        assert r["r2"] >= 0.994, f"{r['name']} correlation {r['r2']:.4f} fell below 0.994"
        assert r["mae_db"] <= 0.35, f"{r['name']} MAE {r['mae_db']:.2f}dB exceeded 0.35 dB"
