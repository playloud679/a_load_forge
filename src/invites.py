"""
Load Forge Alpha Invite Management System.
Handles generation, redemption tracking, rate limiting, and persistence of invite tokens.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import string
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

APP_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INVITES_FILE = APP_DATA_DIR / "invites.json"
MASTER_TOKEN = os.getenv("LOAD_FORGE_ALPHA_TOKEN", "forge-alpha-2026")

_lock = threading.Lock()


def _ensure_data_dir() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INVITES_FILE.exists():
        with open(INVITES_FILE, "w", encoding="utf-8") as f:
            json.dump({"invites": []}, f, indent=2)


def _load_invites() -> list[dict]:
    _ensure_data_dir()
    invites_by_code: dict[str, dict] = {}

    # 1. From local file
    try:
        with open(INVITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("invites", []):
                if "code" in item:
                    invites_by_code[item["code"].upper()] = item
    except Exception:
        pass

    # 2. From environment variable (for serverless Cloud Run syncing)
    env_data = os.getenv("LOAD_FORGE_INVITES_DATA", "").strip()
    if not env_data and os.getenv("LOAD_FORGE_INVITES_B64"):
        try:
            import base64
            env_data = base64.b64decode(os.getenv("LOAD_FORGE_INVITES_B64")).decode("utf-8")
        except Exception:
            pass
    if env_data:
        try:
            parsed = json.loads(env_data)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and "invites" in parsed:
                items = parsed["invites"]
            else:
                items = []
            for item in items:
                code_key = item.get("code", "").upper()
                if code_key and code_key not in invites_by_code:
                    invites_by_code[code_key] = item
        except Exception:
            pass

    return list(invites_by_code.values())


def _save_invites(invites: list[dict]) -> None:
    _ensure_data_dir()
    temp_file = INVITES_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump({"invites": invites}, f, indent=2)
    temp_file.replace(INVITES_FILE)


def generate_code_slug(name: str) -> str:
    """Generate a clean code slug like FORGE-MARCO-A92B."""
    clean_name = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:8]
    if not clean_name:
        clean_name = "VIP"
    rand_chars = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"FORGE-{clean_name}-{rand_chars}"


def create_invite(
    recipient: str,
    max_uses: int = 1,
    role: str = "Beta Tester",
    custom_code: Optional[str] = None,
) -> dict:
    """Create a new trackable invite."""
    with _lock:
        invites = _load_invites()

        if custom_code:
            code = custom_code.strip().upper()
        else:
            code = generate_code_slug(recipient)

        # Check uniqueness
        if any(inv["code"] == code for inv in invites) or code == MASTER_TOKEN.upper():
            code = generate_code_slug(recipient + secrets.choice(string.ascii_uppercase))

        record = {
            "code": code,
            "recipient": recipient.strip(),
            "role": role.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "max_uses": max(1, int(max_uses)),
            "uses_count": 0,
            "active": True,
            "redemptions": [],
        }

        invites.append(record)
        _save_invites(invites)
        return record


def verify_and_redeem_token(token: str, client_ip: str = "unknown") -> tuple[bool, str]:
    """
    Validates token and logs redemption.
    Returns (is_valid, message_or_recipient).
    """
    token_clean = token.strip()
    if not token_clean:
        return False, "Token cannot be empty."

    # 1. Master token is always valid
    if token_clean == MASTER_TOKEN or token_clean.lower() == MASTER_TOKEN.lower():
        return True, "Master Admin Token"

    with _lock:
        invites = _load_invites()
        for inv in invites:
            if inv["code"].upper() == token_clean.upper():
                if not inv.get("active", True):
                    return False, "Invite code has been deactivated."

                if inv["uses_count"] >= inv["max_uses"]:
                    return False, f"Invite code has already reached its maximum usage limit ({inv['max_uses']})."

                # Redeem
                inv["uses_count"] += 1
                inv.setdefault("redemptions", []).append({
                    "redeemed_at": datetime.now(timezone.utc).isoformat(),
                    "ip": client_ip,
                })
                _save_invites(invites)
                return True, inv["recipient"]

    return False, "Invalid invite code."


def is_token_authorized(token: str) -> bool:
    """
    Non-destructive check for existing cookies or tokens without incrementing count.
    Used for subsequent page loads and session validation.
    """
    token_clean = token.strip()
    if not token_clean:
        return False

    if token_clean == MASTER_TOKEN or token_clean.lower() == MASTER_TOKEN.lower():
        return True

    invites = _load_invites()
    for inv in invites:
        if inv["code"].upper() == token_clean.upper():
            return bool(inv.get("active", True))

    return False


def list_invites() -> list[dict]:
    """Return all invite records."""
    return _load_invites()


def revoke_invite(code: str) -> bool:
    """Deactivate an invite code."""
    code_clean = code.strip().upper()
    with _lock:
        invites = _load_invites()
        found = False
        for inv in invites:
            if inv["code"].upper() == code_clean:
                inv["active"] = False
                found = True
                break
        if found:
            _save_invites(invites)
        return found
