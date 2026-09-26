"""Auth gate, SaaS account store and entitlement helpers."""

from __future__ import annotations

import json
import multiprocessing
import os
import time
from pathlib import Path
from typing import Any

import streamlit as st

import saas as _saas
import storage as _storage
import storage.private_store as _private_store
import storage.public_store as _public_store

from . import constants as _constants
from . import runtime as _runtime
from . import navigation as _navigation
from . import usage as _usage


def _remember_local_account(user: _saas.SaaSUser) -> None:
    st.session_state["_projects_after_login"] = True
    st.session_state[_constants._LOCAL_ACCOUNT_SESSION_KEY] = {
        "sub": user.uid,
        "email": user.email,
        "name": user.name,
        "tenant_id": user.tenant_id,
        "plan": user.plan,
    }

def _render_auth_hero_and_badges(title: str, subtitle: str) -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            background: rgba(18, 24, 38, 0.85) !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 14px !important;
            padding: 1.6rem 1.8rem !important;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45) !important;
            backdrop-filter: blur(16px) !important;
        }
        div[data-testid="stForm"] input {
            background-color: rgba(10, 14, 23, 0.85) !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            color: #f3f4f6 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stForm"] input:focus {
            border-color: #10b981 !important;
            box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.25) !important;
        }
        div[data-testid="stRadio"] > div {
            justify-content: center;
            background: rgba(255, 255, 255, 0.05);
            padding: 0.25rem 0.5rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    brand_path = _constants._BRAND_APP_IMAGE if _constants._BRAND_APP_IMAGE.exists() else _constants._BRAND_IMAGE
    if brand_path.exists():
        st.image(str(brand_path), width="stretch")
    else:
        st.title("Load Forge")
    st.markdown(
        f"""
        <div style="text-align: center; margin-top: 0.6rem; margin-bottom: 1.3rem;">
            <h2 style="font-size: 1.35rem; font-weight: 600; color: #f9fafb; margin: 0 0 0.35rem 0; letter-spacing: -0.01em;">{title}</h2>
            <p style="font-size: 0.875rem; color: rgba(255, 255, 255, 0.55); margin: 0; line-height: 1.45;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_local_account_gate(*, render_hero: bool = True) -> None:
    """Render the local registration/login form."""
    if render_hero:
        _, col_center, _ = st.columns([1, 3.2, 1])
        container = col_center
    else:
        import contextlib
        container = contextlib.nullcontext()
    with container:
        if render_hero:
            _render_auth_hero_and_badges(
                title="Sign in to Load Forge",
                subtitle="Sign in or create an account to save and manage your box designs.",
            )
        account_mode = st.radio(
            "Account",
            ("Sign in", "Create account"),
            horizontal=True,
            label_visibility="collapsed",
            key="_local_account_mode",
        )
        accounts = _saas.create_credential_store(_runtime._SAAS_SETTINGS)
        if account_mode == "Sign in":
            with st.form("local_saas_sign_in"):
                email = st.text_input(
                    "Email",
                    placeholder="name@example.com",
                    autocomplete="email",
                    key="_local_sign_in_email",
                )
                password = st.text_input(
                    "Password",
                    placeholder="••••••••••••",
                    type="password",
                    autocomplete="current-password",
                    key="_local_sign_in_password",
                )
                submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    width="stretch",
                )
            if submitted and _is_admin_address(email):
                st.error(_ADMIN_PASSWORD_REFUSAL)
            elif submitted:
                try:
                    user = accounts.authenticate(email, password)
                except _saas.InvalidCredentialsError as exc:
                    st.error(str(exc))
                else:
                    _remember_local_account(user)
                    st.rerun()
        else:
            with st.form("local_saas_registration"):
                name = st.text_input(
                    "Name",
                    placeholder="Your Name",
                    autocomplete="name",
                    key="_local_register_name",
                )
                email = st.text_input(
                    "Email",
                    placeholder="name@example.com",
                    autocomplete="email",
                    key="_local_register_email",
                )
                password = st.text_input(
                    "Password",
                    placeholder="At least 10 characters",
                    type="password",
                    autocomplete="new-password",
                    help="Use at least 10 characters.",
                    key="_local_register_password",
                )
                confirmation = st.text_input(
                    "Confirm password",
                    placeholder="Repeat password",
                    type="password",
                    autocomplete="new-password",
                    key="_local_register_confirmation",
                )
                submitted = st.form_submit_button(
                    "Create account",
                    type="primary",
                    width="stretch",
                )
            if submitted and _is_admin_address(email):
                st.error(_ADMIN_PASSWORD_REFUSAL)
            elif submitted:
                if password != confirmation:
                    st.error("Passwords do not match")
                else:
                    try:
                        user = accounts.create_account(name, email, password)
                    except (ValueError, _saas.AccountExistsError) as exc:
                        st.error(str(exc))
                    else:
                        _remember_local_account(user)
                        st.rerun()
        st.markdown(
            """
            <div style="text-align: center; margin-top: 0.8rem; font-size: 0.8rem; color: rgba(255,255,255,0.6);">
                Registrazione libera con email: nessun codice invito richiesto.
            </div>
            <div style="text-align: center; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.75rem; color: rgba(255,255,255,0.40); line-height: 1.4;">
                Local storage · Encrypted credentials (PBKDF2) · Autosaved projects
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

def _sign_out_saas() -> None:
    st.session_state.pop(_constants._LOCAL_ACCOUNT_SESSION_KEY, None)
    st.session_state.pop("_saas_projects_identity", None)
    st.session_state.pop("_saas_project_summaries", None)
    st.session_state.pop("_cached_user_account", None)
    st.session_state.pop("workspace_mode", None)
    st.session_state.pop("manage_projects_tab", None)
    st.session_state.pop("_cloud_project_summaries", None)
    st.session_state.pop("_cloud_project_summaries_at", None)
    settings = _runtime._SAAS_SETTINGS
    # Local accounts have no OAuth session to redirect. OIDC sessions must
    # return directly after st.logout(): a rerun here can replace Streamlit's
    # auth redirect with the old authenticated page.
    local_session = bool(
        settings is not None
        and (settings.local_accounts or settings.auth_bypass)
    )
    if settings is not None and settings.auth_bypass:
        # Development bypass would otherwise recreate the demo identity on
        # every rerun, making the visible Sign out action appear ineffective.
        st.session_state["_auth_bypass_signed_out"] = True
    if local_session:
        try:
            st.rerun()
        except Exception:
            pass
    else:
        try:
            st.logout()
        except Exception:
            try:
                st.rerun()
            except Exception:
                pass
    st.stop()


def _render_auth_bypass_signed_out() -> None:
    """Show a deterministic signed-out state for development auth bypasses."""
    _, center, _ = st.columns([1, 3.2, 1])
    with center:
        _render_auth_hero_and_badges(
            title="You are signed out",
            subtitle="Development authentication bypass is paused for this session.",
        )
        st.info("No account data is active in this browser session.")
        if st.button("Sign in again", type="primary", width="stretch"):
            st.session_state.pop("_auth_bypass_signed_out", None)
            st.rerun()
    st.stop()

def _patch_websocket_session_manager() -> None:
    """Ensure reconnected sessions update _user_info from incoming cookies.

    In Streamlit >=1.57 (Starlette WebSocket), WebsocketSessionManager.connect_session
    reconnects existing sessions without updating their AppSession._user_info
    from the newly parsed cookie. This patch ensures that whenever a client
    reconnects, the active session's _user_info is synchronized with user_info.
    """
    try:
        from streamlit.runtime.websocket_session_manager import WebsocketSessionManager
        if getattr(WebsocketSessionManager, "_load_forge_user_info_patched", False):
            return

        orig_connect = WebsocketSessionManager.connect_session

        def _patched_connect(self, client, script_data, user_info, existing_session_id=None, session_id_override=None):
            session_id = orig_connect(
                self, client, script_data, user_info,
                existing_session_id=existing_session_id,
                session_id_override=session_id_override,
            )
            if user_info and session_id in self._active_session_info_by_id:
                active_session_info = self._active_session_info_by_id[session_id]
                active_session_info.session._user_info.update(user_info)
            return session_id

        WebsocketSessionManager.connect_session = _patched_connect
        WebsocketSessionManager._load_forge_user_info_patched = True
    except Exception:
        pass


_patch_websocket_session_manager()


def _sync_user_info_from_cookie() -> dict[str, Any] | None:
    """Recover authenticated identity from signed Streamlit OIDC cookie.

    Acts as an immediate fallback during script execution if a session was
    reconnected before _user_info could be populated.
    """
    try:
        if not hasattr(st, "context") or not hasattr(st.context, "cookies"):
            return None
        cookies = dict(st.context.cookies)
        if not any(k.startswith("_streamlit_user") for k in cookies):
            return None

        from streamlit.web.server.starlette.starlette_websocket import (
            USER_COOKIE_NAME,
            _get_signed_cookie_with_chunks,
        )
        from streamlit.web.server.starlette.starlette_auth_routes import get_cookie_secret

        secret = get_cookie_secret()
        if not secret:
            return None

        raw = _get_signed_cookie_with_chunks(cookies, USER_COOKIE_NAME)
        if not raw:
            return None

        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not payload.get("is_logged_in", False):
            return None

        user_info = dict(payload)
        user_info.pop("origin", None)

        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx is not None:
            ctx.user_info.update(user_info)
            try:
                from streamlit.runtime import Runtime
                runtime_instance = Runtime.instance()
                if runtime_instance is not None:
                    session_info = runtime_instance._session_mgr.get_active_session_info(ctx.session_id)
                    if session_info is not None:
                        session_info.session._user_info.update(user_info)
            except Exception:
                pass

        return user_info
    except Exception:
        return None


_SIGN_IN_REASON_KEY = "_guest_sign_in_reason"
_SIGN_IN_COPY = {
    "save": ("Sign in to save your design", "Your design comes with you: it is saved to your account right after you sign in."),
    "bass_match": ("Sign in to run Bass Match", "Bass Match ranks all catalog drivers for your box. Free plan, no card required."),
    "projects": ("Sign in to see your projects", "Your saved designs live in your account."),
    "account": ("Sign in to Load Forge", "Save designs, run Bass Match across the whole catalog. Free plan, no card required."),
}


def request_sign_in(reason: str) -> None:
    """Send a guest to the sign-in page (button callback).

    For ``save`` the current design and name ride the URL (``d``/``name``), and
    therefore the 10-minute return cookie, across the Google redirect; the new
    session loads them and autosaves the project.
    """
    from . import state as _state

    st.session_state[_SIGN_IN_REASON_KEY] = reason
    st.session_state.pop(_GUEST_INVITE_KEY, None)
    # The sign-in page renders no design widgets, and Streamlit drops the state
    # of widgets a run does not render: keep a copy to restore on return.
    _state._snapshot_design_state()
    if reason == "save":
        from . import projects as _projects

        token = _projects._encode_share_payload()
        # Already the guest's own state: do not re-apply it if they come back.
        st.session_state["_applied_share_token"] = token
        st.query_params["d"] = token
        st.query_params["name"] = str(st.session_state.get("project_name", ""))[:80]
        st.query_params["view"] = "box-design"


_GUEST_INVITE_KEY = "_guest_invite_reason"


def invite_guest(reason: str) -> None:
    """Guest asked for an account-only area: stay in Box Design, show the invite."""
    st.session_state[_GUEST_INVITE_KEY] = reason
    st.session_state["workspace_mode"] = "Box Design"


def render_guest_sign_in_invite() -> None:
    """Non-blocking card above Box Design; the design widgets keep rendering."""
    reason = st.session_state.get(_GUEST_INVITE_KEY)
    if not (_runtime._GUEST and reason in _SIGN_IN_COPY):
        return
    title, subtitle = _SIGN_IN_COPY[reason]
    _usage.track("sign_in_invite_view", {"reason": reason}, once=f"invite:{reason}")
    with st.container(border=True, key="guest_sign_in_invite"):
        c_text, c_sign, c_close = st.columns([5, 1.6, 1.2], vertical_alignment="center")
        c_text.markdown(f"**{title}** · {subtitle}")
        c_sign.button("Sign in — free", type="primary", width="stretch",
                      key=f"guest_invite_sign_in_{reason}", on_click=request_sign_in, args=(reason,))
        c_close.button("Not now", width="stretch", key=f"guest_invite_close_{reason}",
                       on_click=lambda: st.session_state.pop(_GUEST_INVITE_KEY, None))


def _continue_as_guest() -> None:
    from . import state as _state

    st.session_state.pop(_SIGN_IN_REASON_KEY, None)
    _state._restore_design_state()


def _resolve_saas_user() -> _saas.SaaSUser | None:
    """Resolve the authenticated user when either auth or SaaS is enabled."""
    _runtime._GUEST = False
    # Finder workers re-import this module under multiprocessing spawn/forkserver
    # without a Streamlit request context. They only execute pure ranking helpers
    # and must never enter an account flow or touch project persistence.
    if multiprocessing.current_process().name != "MainProcess":
        return None
    if not _runtime._SAAS_SETTINGS.auth_required:
        return None
    if _runtime._SAAS_SETTINGS.auth_bypass:
        if st.session_state.get("_auth_bypass_signed_out", False):
            _render_auth_bypass_signed_out()
        claims = _runtime._SAAS_SETTINGS.development_claims()
    elif _runtime._SAAS_SETTINGS.local_accounts:
        claims = st.session_state.get(_constants._LOCAL_ACCOUNT_SESSION_KEY)
        if not isinstance(claims, dict):
            _render_local_account_gate()
    else:
        claims = st.session_state.get(_constants._LOCAL_ACCOUNT_SESSION_KEY)
        if not isinstance(claims, dict):
            try:
                logged_in = bool(st.user.is_logged_in)
            except (AttributeError, RuntimeError):
                logged_in = False
            if not logged_in:
                recovered_claims = _sync_user_info_from_cookie()
                if recovered_claims:
                    logged_in = True
                    claims = recovered_claims
            reason = st.session_state.get(_SIGN_IN_REASON_KEY)
            if not logged_in and _runtime._SAAS_SETTINGS.guest_access and not reason:
                _runtime._GUEST = True
                _usage.track(
                    "guest_session",
                    {key: str(st.query_params.get(key, "")) for key in ("view", "preset")},
                    once="guest",
                )
                return None
            if not logged_in:
                _usage.track(
                    "auth_gate_view",
                    {"reason": reason or "wall",
                     **{key: str(st.query_params.get(key, "")) for key in ("view", "preset")}},
                    once=f"gate:{reason}",
                )
                _usage.remember_anon_id_for_sign_in()
                _navigation.remember_auth_destination()
                _, col_center, _ = st.columns([1, 3.2, 1])
                with col_center:
                    title, subtitle = _SIGN_IN_COPY.get(reason, (
                        "Sign in to Load Forge",
                        "Sign in to save and manage your box designs, simulations, and driver catalog.",
                    ))
                    _render_auth_hero_and_badges(title=title, subtitle=subtitle)
                    if reason:
                        st.button("← Back to my design (continue as guest)", key="continue_as_guest",
                                  on_click=_continue_as_guest)
                    try:
                        auth_configured = "auth" in st.secrets
                    except (FileNotFoundError, RuntimeError):
                        auth_configured = False
                    if auth_configured:
                        if st.button("Sign in with Google", type="primary", width="stretch"):
                            if _runtime._SAAS_SETTINGS.oidc_provider:
                                st.login(_runtime._SAAS_SETTINGS.oidc_provider)
                            else:
                                st.login()
                            st.stop()
                        st.markdown(
                            """
                            <div style="display: flex; align-items: center; text-align: center; margin: 1.2rem 0; color: rgba(255,255,255,0.35); font-size: 0.8rem;">
                                <div style="flex: 1; border-bottom: 1px solid rgba(255,255,255,0.12);"></div>
                                <span style="padding: 0 0.8rem; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em;">oppure</span>
                                <div style="flex: 1; border-bottom: 1px solid rgba(255,255,255,0.12);"></div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    _render_local_account_gate(render_hero=False)
                    st.stop()
            if not isinstance(claims, dict):
                claims = st.user.to_dict()

    expires_at = claims.get("exp")
    if expires_at is not None:
        try:
            expired = float(expires_at) <= time.time()
        except (TypeError, ValueError):
            expired = False
        if expired:
            st.logout()
            st.stop()
    try:
        user = _saas.user_from_claims(claims)
    except _saas.SaaSConfigurationError as exc:
        st.error(f"The identity provider returned an unusable account: {exc}")
        if st.button("Sign out", key="invalid_identity_sign_out"):
            st.logout()
        st.stop()
    if not _runtime._SAAS_SETTINGS.allows_email(user.email):
        _, col_center, _ = st.columns([1, 3.2, 1])
        with col_center:
            _render_auth_hero_and_badges(
                title="Access Restricted",
                subtitle="Your account is not authorized to access this Load Forge workspace.",
            )
            st.error("This email address is not authorized to use Load Forge.")
            st.caption(user.email or "The identity provider did not return an email.")
            if st.button("Sign out", key="unauthorized_identity_sign_out", width="stretch"):
                st.logout()
        st.stop()
    return user

@st.cache_resource(show_spinner=False)
def _cached_account_store(
    settings: _saas.SaaSSettings,
    source_token: tuple[int, int],
):
    """Cache an account store only for the active SaaS module revision."""
    del source_token
    return _storage.create_private_store(settings)

def _get_account_store():
    return _cached_account_store(
        _runtime._SAAS_SETTINGS,
        (_runtime._SAAS_SOURCE_TOKEN, Path(_private_store.__file__).stat().st_mtime_ns),
    )

@st.cache_resource(show_spinner=False)
def _cached_project_store(
    settings: _saas.SaaSSettings,
    source_token: int,
):
    """Cache a project store only for the active SaaS module revision."""
    del source_token
    return _saas.create_project_store(settings)

def _get_project_store():
    return _cached_project_store(_runtime._SAAS_SETTINGS, _runtime._SAAS_SOURCE_TOKEN)

@st.cache_resource(show_spinner=False)
def _cached_public_store(
    settings: _saas.SaaSSettings,
    source_token: int,
):
    """Cache a public store only for the active SaaS module revision."""
    del source_token
    return _storage.create_public_store(settings)

def _get_public_store():
    source_token = _runtime._SAAS_SOURCE_TOKEN ^ Path(_public_store.__file__).stat().st_mtime_ns
    return _cached_public_store(_runtime._SAAS_SETTINGS, source_token)

_ADMIN_PASSWORD_REFUSAL = "This address signs in with Google only."


def _configured_admin_emails() -> frozenset[str]:
    email = os.getenv("LOAD_FORGE_ADMIN_EMAIL", "playloud79@gmail.com").strip().casefold()
    return frozenset({email} - {""})


def _is_admin_address(email: str) -> bool:
    return str(email or "").strip().casefold() in _configured_admin_emails()


def _is_password_session() -> bool:
    """True when this session signed in with the email/password form in a
    production-style deployment (not the local-accounts or bypass dev modes).

    Such accounts are not email-verified: anyone can register any address.
    They must never be administrators, whatever the email says.
    """
    settings = _runtime._SAAS_SETTINGS
    if settings is None or settings.local_accounts or settings.auth_bypass:
        return False
    return isinstance(st.session_state.get(_constants._LOCAL_ACCOUNT_SESSION_KEY), dict)


def _account_admin_emails() -> frozenset[str]:
    """Administration is configured separately from the login allowlist.

    Only OIDC (Google) sessions can be admin: an email/password session gets
    no admin emails, so a self-registered copy of the admin address is inert.
    """
    if _is_password_session():
        return frozenset()
    email = os.getenv("LOAD_FORGE_ADMIN_EMAIL", "playloud79@gmail.com").strip().casefold()
    emails = {email} if email else set()
    uid = os.getenv("LOAD_FORGE_ADMIN_UID", "").strip()
    if uid and _runtime._CURRENT_SAAS_USER is not None and _runtime._CURRENT_SAAS_USER.uid == uid:
        emails.add(_runtime._CURRENT_SAAS_USER.email.strip().casefold())
    return frozenset(emails - {""})

_CURRENT_ACCOUNT_KEY = "_lf_current_account"
_NO_ACCOUNT = object()


def _get_current_user_account() -> _saas.UserAccount | None:
    """Reuse one account read within this script run, never across sessions.

    The memo lives in ``st.session_state`` (per browser session); a process-wide
    ``functools.cache`` would hand one user's account to another concurrent
    session. ``app.main`` clears it at the start of every run.
    """
    cached = st.session_state.get(_CURRENT_ACCOUNT_KEY, _NO_ACCOUNT)
    if cached is not _NO_ACCOUNT:
        return cached
    acc = _load_current_user_account()
    st.session_state[_CURRENT_ACCOUNT_KEY] = acc
    return acc


def _clear_current_user_account() -> None:
    st.session_state.pop(_CURRENT_ACCOUNT_KEY, None)


# Existing call sites use the functools-style name.
_get_current_user_account.cache_clear = _clear_current_user_account


def _load_current_user_account() -> _saas.UserAccount | None:
    if _runtime._CURRENT_SAAS_USER is None:
        if _runtime._GUEST:
            return None  # guests never share the local demo account or its credits
        # Default local session account for demo/offline use with full trial balance
        acc = _runtime._ACCOUNT_STORE.get_or_create_account(
            uid="local-user",
            email="local@loadforge.app",
            name="Load Forge User",
            admin_emails=_account_admin_emails(),
        )
        if acc.credits_balance < 2500:
            acc.credits_balance = 2500
            acc.credits_monthly_quota = 2500
        return acc
    acc = _runtime._ACCOUNT_STORE.get_or_create_account(
        uid=_runtime._CURRENT_SAAS_USER.uid,
        email=_runtime._CURRENT_SAAS_USER.email,
        name=_runtime._CURRENT_SAAS_USER.name,
        admin_emails=_account_admin_emails(),
    )
    return acc
