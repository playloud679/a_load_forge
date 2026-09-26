"""Streamlit glue for product usage events (see docs/usage_analytics.md).

``track(event, props, once=...)`` records one event for the current visitor,
best-effort: a storage failure is logged and never reaches the user. ``once``
deduplicates within the Streamlit session so reruns (every widget change) do
not multiply writes.

The anonymous id ``lf_aid`` comes from the portal handoff query (``/app?lf_aid=``)
or is minted here. It is kept only in the session; at the sign-in wall it is
added to the URL so the existing 10-minute return-destination cookie carries it
across the Google redirect, and it is dropped from the URL once signed in.
"""
from __future__ import annotations

import multiprocessing
import re
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

import usage_analytics as _usage_analytics

from . import runtime as _runtime

_ANON_PARAM = "lf_aid"
_ANON_KEY = "_lf_usage_anon_id"
_ONCE_KEY = "_lf_usage_once"
_ANON_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
_SIGNUP_WINDOW = timedelta(minutes=15)


@st.cache_resource(show_spinner=False)
def _cached_usage_store(settings: Any) -> Any:
    return _usage_analytics.create_usage_store(settings)


def get_usage_store() -> Any:
    return _cached_usage_store(_runtime._SAAS_SETTINGS)


def anon_id() -> str:
    """Return this visit's anonymous id (portal ``lf_aid`` or a new one).

    No long-lived analytics cookie is set: the id lives in the session and
    crosses the sign-in redirect only through the 10-minute return-destination
    cookie (``navigation.DESTINATION_KEYS``).
    """
    cached = st.session_state.get(_ANON_KEY)
    if cached:
        return cached
    candidate = str(st.query_params.get(_ANON_PARAM, "") or "")
    if not _ANON_RE.match(candidate):
        candidate = "a_" + secrets.token_hex(6)
    st.session_state[_ANON_KEY] = candidate
    return candidate


def remember_anon_id_for_sign_in() -> None:
    """Put the id in the URL so ``remember_auth_destination`` carries it."""
    st.query_params[_ANON_PARAM] = anon_id()


def track(event: str, props: Mapping[str, Any] | None = None, *, once: str | None = None) -> None:
    """Record ``event`` for the current visitor; never raises."""
    if multiprocessing.current_process().name != "MainProcess":
        return
    try:
        seen = st.session_state.setdefault(_ONCE_KEY, set())
        if once is not None:
            key = f"{event}:{once}"
            if key in seen:
                return
            seen.add(key)
        user = _runtime._CURRENT_SAAS_USER
        document = _usage_analytics.build_event(
            event,
            uid=getattr(user, "uid", ""),
            email=getattr(user, "email", ""),
            anon_id=anon_id(),
            props=props,
        )
        get_usage_store().append(document)
    except Exception:  # analytics must never break the product
        _runtime.logger.warning("usage event %s not recorded", event, exc_info=True)


def track_session(account: Any) -> None:
    """Emit ``session_start`` once per session and ``signup_completed`` for new accounts."""
    if account is None or _runtime._CURRENT_SAAS_USER is None:
        return
    view = str(st.query_params.get("view", "") or "")
    track("session_start", {"view": view, "plan": account.plan}, once="session")
    created = account.created_at if account.created_at.tzinfo else account.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created <= _SIGNUP_WINDOW:
        track("signup_completed", {"view": view}, once="signup")
    # Keep the id out of URLs a signed-in user might copy and share.
    st.query_params.pop(_ANON_PARAM, None)
