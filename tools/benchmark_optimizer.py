"""Offline benchmark harness for Load Forge Finder V2."""
import sys
import time
import numpy as np
sys.path.insert(0, ".")
from src import acoustics, engine

BENCHMARK_DRIVERS = [
    "Beyma 12CMV2",
    "Beyma 12BR70",
    "Beyma 12G40",
    "LSDB: FaitalPRO 8PR150 8Ω",
    "WEB: Visaton AL 130 - 8 Ohm",
]

TOPOLOGIES = [
    "Sealed",
    "Bass reflex",
    "Bandpass 4th order",
    "Bandpass 6th order",
    "DCCAV",
    "Bandpass 8th order",
]

def run_benchmark(max_evaluations: int = 30):
    results = {}
    for top in TOPOLOGIES:
        results[top] = []
        for drv_name in BENCHMARK_DRIVERS:
            ts = acoustics.get_driver_preset(drv_name)
            goals = acoustics.OptimizationGoals(objective="balanced")
            t0 = time.perf_counter()
            opt = engine.optimize_alignment(
                ts,
                goals=goals,
                load_type=top,
                max_evaluations=max_evaluations,
                frequency_points=30,
                refine_f3_points=20,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            results[top].append({
                "driver": drv_name,
                "score": opt.score,
                "f3_hz": opt.f3_hz,
                "total_volume_l": opt.total_volume_l,
                "elapsed_ms": elapsed_ms,
                "feasible": np.isfinite(opt.score) and opt.score < 1e5,
            })
    return results

if __name__ == "__main__":
    res = run_benchmark()
    for top, rows in res.items():
        avg_score = np.mean([r["score"] for r in rows if r["feasible"]])
        avg_f3 = np.mean([r["f3_hz"] for r in rows if r["feasible"]])
        avg_ms = np.mean([r["elapsed_ms"] for r in rows])
        feas = sum(1 for r in rows if r["feasible"])
        print(f"[{top:18}] Feasible: {feas}/{len(rows)} | Avg Score: {avg_score:8.4f} | Avg F3: {avg_f3:5.1f}Hz | Avg time: {avg_ms:5.1f}ms")
