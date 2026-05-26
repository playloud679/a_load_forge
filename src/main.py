"""
Orchestrator — Horn Generator Pipeline.

  1. Profile generator   (numpy-stl → horn STL)
"""

import argparse
import logging
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
    return p.parse_args(args)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    base_stl = work / "horn.stl"

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

        logger.info("Pipeline completed successfully.")

    except Exception as exc:
        logger.exception("Pipeline aborted: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
