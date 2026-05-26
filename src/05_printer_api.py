"""
Printer API (OctoPrint REST Payload Builder).

Stage 5 of the Acoustic Horn pipeline.
Constructs and sends an HTTP request to OctoPrint to upload and start printing
a .gcode file.

Usage:
    python -m src.05_printer_api --gcode io/horn.gcode \
        --host 192.168.1.100 --api-key <SECRET>
"""

import argparse
import logging
import sys

import requests

logger = logging.getLogger(__name__)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a .gcode file to OctoPrint and start a print job."
    )
    parser.add_argument(
        "--gcode",
        type=str,
        required=True,
        help="Path to the .gcode file to print.",
    )
    parser.add_argument(
        "--host",
        type=str,
        required=True,
        help="OctoPrint hostname or IP address.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        required=True,
        help="OctoPrint API key.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="OctoPrint HTTP port (default: 80).",
    )
    return parser.parse_args(args)


def send_to_printer(gcode_path: str, host: str, api_key: str, port: int = 80) -> None:
    """Upload a file to OctoPrint and queue it for printing."""
    base_url = f"http://{host}:{port}"

    headers = {"X-Api-Key": api_key}

    with open(gcode_path, "rb") as fh:
        files = {"file": (gcode_path, fh, "application/octet-stream")}
        params = {"select": "true", "print": "true"}

        logger.info("Uploading %s to %s ...", gcode_path, base_url)
        resp = requests.post(
            f"{base_url}/api/files/local",
            headers=headers,
            files=files,
            params=params,
            timeout=300,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"OctoPrint upload failed (HTTP {resp.status_code}): {resp.text}"
        )

    logger.info("Print job submitted successfully.")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        send_to_printer(args.gcode, args.host, args.api_key, args.port)
    except Exception as exc:
        logger.exception("Printer API call failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
