"""
Orchestrator — Horn Generator Pipeline.

  1. Profile generator → horn STL via direct function calls.
"""

import argparse
import importlib.machinery
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_module(path: Path) -> object:
    loader = importlib.machinery.SourceFileLoader("_core", str(path))
    spec = importlib.util.spec_from_loader("_core", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


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
        logger.info("=== Stage 1: Profile Generator ===")

        core = _load_module(Path(__file__).parent / "01_profile_generator.py")

        name = core.resolve_profile(args)

        if name == "tractrix":
            if args.mouth is None:
                raise ValueError("--mouth required for tractrix")
            z, r = core.get_tractrix(args.throat, args.mouth, args.segments)
        elif name == "lecleach":
            if args.fc is None:
                raise ValueError("--fc required for Le Cléac'h")
            z, r = core.get_lecleach(args.throat, args.fc, args.segments)
        elif name == "iwata":
            if args.fc is None or args.length is None:
                raise ValueError("--fc and --length required for iwata")
            z, r = core.get_iwata(args.throat, args.fc, args.length, args.segments)
        else:
            raise ValueError(f"Unknown profile: {name}")

        core.generate_3d_mesh_from_profile(
            z, r,
            thickness=args.thickness,
            rings=args.rings,
            output_path=str(base_stl),
        )

        logger.info("Pipeline completed successfully.")

    except Exception as exc:
        logger.exception("Pipeline aborted: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
