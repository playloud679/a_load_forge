"""Auth gate, SaaS account store and entitlement helpers."""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path
import multiprocessing
import os
import time

import streamlit as st

import saas as _saas
import storage as _storage
import storage.private_store as _private_store

from . import constants as _constants
from . import runtime as _runtime


def _remember_local_account(user: _saas.SaaSUser) -> None:
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
        accounts = _saas.LocalAccountStore(_runtime._SAAS_SETTINGS.local_account_database)
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
            if submitted:
                try:
                    user = accounts.authenticate(email, password)
                except _saas.InvalidCredentialsError as exc:
                    st.error(str(exc))
                else:
                    _remember_local_account(user)
                    st.rerun()
        else:
            prefilled_token = ""
            try:
                if "token" in st.query_params:
                    prefilled_token = str(st.query_params["token"]).strip()
                elif hasattr(st, "context") and hasattr(st.context, "cookies"):
                    prefilled_token = str(st.context.cookies.get("lf_alpha_token", "")).strip()
            except Exception:
                pass

            with st.form("local_saas_registration"):
                alpha_code = st.text_input(
                    "Alpha Invite Code",
                    value=prefilled_token,
                    placeholder="FORGE-XXXX-XXXX",
                    help="Load Forge Studio è in Private Closed Alpha. È richiesto un codice invito valido per registrarsi.",
                    key="_local_register_alpha_code",
                )
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
            if submitted:
                from src.invites import verify_and_redeem_token
                is_valid_code, code_err = verify_and_redeem_token(alpha_code)
                if not is_valid_code:
                    st.error(f"⛔ Codice Invito non valido ({code_err}). Richiedi l'accesso su https://load-forge.com/alpha-gate")
                elif password != confirmation:
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
                Non hai ancora un codice invito? <a href="https://load-forge.com/alpha-gate" target="_blank" style="color: #10b981; font-weight: 500;">Richiedi l'accesso alla Closed Alpha</a>
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
    try:
        st.logout()
    except Exception:
        pass
    try:
        st.rerun()
    except Exception:
        pass
    st.stop()

def _resolve_saas_user() -> _saas.SaaSUser | None:
    """Resolve the authenticated user when either auth or SaaS is enabled."""
    # Finder workers re-import this module under multiprocessing spawn/forkserver
    # without a Streamlit request context. They only execute pure ranking helpers
    # and must never enter an account flow or touch project persistence.
    if multiprocessing.current_process().name != "MainProcess":
        return None
    if not _runtime._SAAS_SETTINGS.auth_required:
        return None
    if _runtime._SAAS_SETTINGS.auth_bypass:
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
                _, col_center, _ = st.columns([1, 3.2, 1])
                with col_center:
                    _render_auth_hero_and_badges(
                        title="Sign in to Load Forge",
                        subtitle="Sign in to save and manage your box designs, simulations, and driver catalog.",
                    )
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
    return _cached_public_store(_runtime._SAAS_SETTINGS, _runtime._SAAS_SOURCE_TOKEN)

def _account_admin_emails() -> frozenset[str]:
    """Administration is configured separately from the login allowlist."""
    email = os.getenv("LOAD_FORGE_ADMIN_EMAIL", "playloud79@gmail.com").strip().casefold()
    emails = {email} if email else set()
    uid = os.getenv("LOAD_FORGE_ADMIN_UID", "").strip()
    if uid and _runtime._CURRENT_SAAS_USER is not None and _runtime._CURRENT_SAAS_USER.uid == uid:
        emails.add(_runtime._CURRENT_SAAS_USER.email.strip().casefold())
    return frozenset(emails - {""})

@cache
def _get_current_user_account() -> _saas.UserAccount | None:
    """Reuse one account read within this script run, never across sessions."""
    if _runtime._CURRENT_SAAS_USER is None:
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
