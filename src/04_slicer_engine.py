"""
Slicer Engine (CuraEngine CLI Wrapper).

Stage 4 of the Acoustic Horn pipeline.
Invokes CuraEngine as a subprocess to slice an .stl mesh into .gcode.

Usage:
    python -m src.04_slicer_engine --input io/horn_final.stl --output io/horn.gcode \
        --config configs/slicing_profiles/default.def.json
"""

import argparse
import logging
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

CURA_ENGINE_CMD = "CuraEngine"


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Slice a meshed .stl file using CuraEngine."
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input .stl mesh file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output .gcode file path.",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the Cura slicing definition (.def.json).",
    )
    return parser.parse_args(args)


def slice_mesh(input_path: str, output_path: str, config_path: str) -> None:
    """Run CuraEngine as a subprocess and raise on failure."""
    if not shutil.which(CURA_ENGINE_CMD):
        raise RuntimeError(
            f"'{CURA_ENGINE_CMD}' not found on PATH. "
            "Install CuraEngine or add it to PATH."
        )

    cmd = [
        CURA_ENGINE_CMD,
        "slice",
        "-v",
        "-j", config_path,
        "-o", output_path,
        "-l", input_path,
    ]

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("CuraEngine stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"CuraEngine failed with exit code {result.returncode}."
        )

    logger.info("Slicing successful: %s", output_path)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        slice_mesh(args.input, args.output, args.config)
    except Exception as exc:
        logger.exception("Slicing failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
