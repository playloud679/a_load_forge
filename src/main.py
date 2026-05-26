"""
Orchestrator — Tractrix Horn Generator Pipeline.

  1. Profile generator   (numpy-stl → tractrix_horn.stl)
  2. Blender boolean ops (mounting flange → final .stl)  [optional]
  3. CuraEngine slicing   (.stl → .gcode)                [optional]
  4. OctoPrint upload     (.gcode → printer)             [optional]
"""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_python_module(module: str, cli_args: list[str]) -> None:
    cmd = [sys.executable, "-m", module, *cli_args]
    logger.info("Running: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    for line in (r.stdout or "").strip().splitlines():
        logger.info("[%s] %s", module, line)
    for line in (r.stderr or "").strip().splitlines():
        logger.warning("[%s] %s", module, line)
    if r.returncode != 0:
        raise RuntimeError(f"Module '{module}' failed (exit {r.returncode}).")


def _run_blender(script: str, cli_args: list[str]) -> None:
    cmd = ["blender", "-b", "-P", script, "--", *cli_args]
    logger.info("Running: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    for line in (r.stdout or "").strip().splitlines():
        logger.info("[blender] %s", line)
    for line in (r.stderr or "").strip().splitlines():
        logger.warning("[blender] %s", line)
    if r.returncode != 0:
        raise RuntimeError(f"Blender script failed (exit {r.returncode}).")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tractrix Horn Generator Pipeline")
    p.add_argument("--throat", type=float, required=True)
    p.add_argument("--mouth", type=float, default=None,
                   help="Mouth diameter (tractrix / iwata mode)")
    p.add_argument("--fc", type=float, default=None,
                   help="Cutoff frequency in Hz (Le Cléac'h mode)")
    p.add_argument("--length", type=float, default=None,
                   help="Axial length in mm (iwata mode)")
    p.add_argument("--profile", choices=["auto", "tractrix", "lecleach", "iwata"],
                   default="auto")
    p.add_argument("--thickness", type=float, default=4.0)
    p.add_argument("--segments", type=int, default=300)
    p.add_argument("--rings", type=int, default=64)
    p.add_argument("--work-dir", type=str, default="io")
    p.add_argument(
        "--slicing-config", type=str,
        default="configs/slicing_profiles/default.def.json",
    )
    p.add_argument("--printer-host", type=str, default=None)
    p.add_argument("--printer-api-key", type=str, default=None)
    p.add_argument(
        "--blender-script", type=str,
        default="blender_scripts/03_boolean_operations.py",
    )
    p.add_argument("--skip-blender", action="store_true")
    p.add_argument("--skip-slicer", action="store_true")
    return p.parse_args(args)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    base_stl = work / "horn_base.stl"
    final_stl = work / "horn.stl"
    gcode = work / "horn.gcode"

    try:
        # ----- Stage 1: Tractrix STL generation -----
        logger.info("=== Stage 1: Tractrix Generator ===")
        gen_args = [
            "--throat", str(args.throat),
            "--thickness", str(args.thickness),
            "--segments", str(args.segments),
            "--rings", str(args.rings),
            "--output", str(base_stl),
            "--profile", args.profile,
        ]
        if args.mouth is not None:
            gen_args += ["--mouth", str(args.mouth)]
        if args.fc is not None:
            gen_args += ["--fc", str(args.fc)]
        if args.length is not None:
            gen_args += ["--length", str(args.length)]
        _run_python_module("src.01_profile_generator", gen_args)

        # ----- Stage 2: Blender boolean ops (optional) -----
        blender_ok = shutil.which("blender") is not None
        if args.skip_blender or not blender_ok:
            if not blender_ok:
                logger.warning("blender not found — using base STL as final.")
            shutil.copy2(str(base_stl), str(final_stl))
        else:
            logger.info("=== Stage 2: Blender Boolean Operations ===")
            _run_blender(
                args.blender_script,
                [
                    "--input", str(base_stl),
                    "--output", str(final_stl),
                    "--throat", str(args.throat),
                ],
            )

        # ----- Stage 3: CuraEngine slicing (optional) -----
        cura_ok = shutil.which("CuraEngine") is not None
        if not cura_ok or args.skip_slicer:
            if not cura_ok:
                logger.warning("CuraEngine not found — skipping slice.")
        else:
            logger.info("=== Stage 3: Slicing ===")
            _run_python_module(
                "src.04_slicer_engine",
                [
                    "--input", str(final_stl),
                    "--output", str(gcode),
                    "--config", args.slicing_config,
                ],
            )

        # ----- Stage 4: Printer upload (optional) -----
        if args.printer_host:
            logger.info("=== Stage 4: Printer Upload ===")
            _run_python_module(
                "src.05_printer_api",
                [
                    "--gcode", str(gcode),
                    "--host", args.printer_host,
                    "--api-key", args.printer_api_key,
                ],
            )

        logger.info("Pipeline completed successfully.")

    except Exception as exc:
        logger.exception("Pipeline aborted: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
