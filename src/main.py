"""
Orchestrator — Horn Generator Pipeline.

  1. Profile generator → horn STL via direct function calls.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from profile_generator import (get_tractrix, get_salmon,
                                generate_3d_mesh_from_profile, resolve_profile)

logger = logging.getLogger(__name__)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tractrix Horn Generator Pipeline")
    p.add_argument("--throat", type=float, required=True)
    p.add_argument("--mouth", type=float, default=None)
    p.add_argument("--fc", type=float, default=None)
    p.add_argument("--length", type=float, default=None)
    p.add_argument("--profile", choices=["auto", "tractrix", "salmon"],
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
        name = resolve_profile(args)

        if name == "tractrix":
            if args.mouth is None:
                raise ValueError("--mouth required for tractrix")
            z, r = get_tractrix(args.throat, args.mouth, args.segments)
        elif name == "salmon":
            if args.fc is None or args.length is None:
                raise ValueError("--fc and --length required for salmon")
            z, r = get_salmon(args.throat, args.fc, args.length, args.segments)
        else:
            raise ValueError(f"Unknown profile: {name}")

        generate_3d_mesh_from_profile(
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
