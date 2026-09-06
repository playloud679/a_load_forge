"""Load Forge Stripe Billing & Subscription Infrastructure.

Implements zero-liability, hosted payment flows via Stripe Checkout and Stripe
Customer Portal, paired with robust, idempotent webhook synchronization to
Firestore user accounts.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from src.saas import UserAccount, PLAN_ENTITLEMENTS

logger = logging.getLogger("load_forge.billing")

# Defaults and URLs
DEFAULT_APP_URL = "https://load-forge-665148536194.europe-west1.run.app"

CREDIT_PACKS: dict[str, dict[str, Any]] = {
    "pack_100000": {
        "credits": 100_000,
        "name": "100,000 Credits",
        "price_eur": 5.0,
        "badge": "Starter",
        "description": "Ideal for focused sweeps, deep comparisons and custom driver runs",
        "env_var": "STRIPE_PRICE_CREDITS_100000",
    },
    "pack_300000": {
        "credits": 300_000,
        "name": "300,000 Credits",
        "price_eur": 12.0,
        "badge": "Popular",
        "description": "Multi-topology comparative scans across extensive candidate pools",
        "env_var": "STRIPE_PRICE_CREDITS_300000",
    },
    "pack_1000000": {
        "credits": 1_000_000,
        "name": "1,000,000 Credits",
        "price_eur": 29.0,
        "badge": "Power / Best Value",
        "description": "Exhaustive scans across our full 9,800+ driver catalog with zero limits",
        "env_var": "STRIPE_PRICE_CREDITS_1000000",
    },
}


def get_stripe_setting(key: str, default: str = "") -> str:
    """Retrieve a Stripe configuration parameter from env or Streamlit secrets."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "stripe" in st.secrets:
            s_val = st.secrets["stripe"].get(key.lower().replace("stripe_", ""), "")
            if s_val:
                return str(s_val).strip()
    except Exception:
        pass
    return default


def get_stripe_secret_key() -> str:
    return get_stripe_setting("STRIPE_SECRET_KEY")


def get_stripe_publishable_key() -> str:
    return get_stripe_setting("STRIPE_PUBLISHABLE_KEY")


def get_stripe_webhook_secret() -> str:
    return get_stripe_setting("STRIPE_WEBHOOK_SECRET")


def get_stripe_price_id(plan: str = "pro", interval: str = "monthly") -> str:
    """Return the Stripe Price ID for the requested tier and billing interval."""
    plan_norm = plan.strip().casefold()
    int_norm = interval.strip().casefold()
    key = f"STRIPE_PRICE_{plan_norm.upper()}_{int_norm.upper()}"
    val = get_stripe_setting(key)
    if val:
        return val
    # Fallback to defaults created in Stripe
    if plan_norm == "hobby" and int_norm == "monthly":
        return get_stripe_setting("STRIPE_PRICE_HOBBY_MONTHLY", "price_1UCbuiPgXf9081cTKLOukCkX")
    elif plan_norm == "hobby" and int_norm == "yearly":
        return get_stripe_setting("STRIPE_PRICE_HOBBY_YEARLY", "price_1UCbuiPgXf9081cTRWTHAWuF")
    elif plan_norm == "pro" and int_norm == "monthly":
        return get_stripe_setting("STRIPE_PRICE_PRO_MONTHLY", "price_1UCbujPgXf9081cTtlwN0KcB")
    elif plan_norm == "pro" and int_norm == "yearly":
        return get_stripe_setting("STRIPE_PRICE_PRO_YEARLY", "price_1UCbujPgXf9081cTx2YEy0my")
    elif plan_norm == "team":
        return get_stripe_setting("STRIPE_PRICE_TEAM_MONTHLY", "price_team_monthly_default")
    return ""


def get_app_url() -> str:
    return os.environ.get("LOAD_FORGE_APP_URL", "").strip() or DEFAULT_APP_URL


def is_stripe_configured() -> bool:
    """Return True if a Stripe Secret Key is provisioned."""
    return bool(get_stripe_secret_key())


def _init_stripe() -> Any:
    """Initialize and return the Stripe SDK client module."""
    try:
        import stripe
    except ImportError as exc:
        raise RuntimeError("The 'stripe' Python package is required for billing operations.") from exc
    key = get_stripe_secret_key()
    if not key:
        raise ValueError("STRIPE_SECRET_KEY is not configured.")
    stripe.api_key = key
    return stripe


def ensure_stripe_customer(account: UserAccount, account_store: Any = None) -> str:
    """Ensure a Stripe Customer object exists for this user and return its ID."""
    if account.stripe_customer_id:
        return account.stripe_customer_id

    stripe = _init_stripe()
    customer = stripe.Customer.create(
        email=account.email,
        name=account.name or account.email,
        metadata={
            "uid": account.uid,
            "email": account.email,
        },
    )
    customer_id = str(customer.id)
    account.stripe_customer_id = customer_id
    if account_store is not None:
        try:
            account_store.update_billing_info(
                account.email or account.uid,
                stripe_customer_id=customer_id,
            )
        except Exception:
            logger.exception("Failed to persist stripe_customer_id to account store")
    return customer_id


def create_checkout_session(
    account: UserAccount,
    *,
    plan: str = "pro",
    interval: str = "monthly",
    price_id: str | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
    account_store: Any = None,
) -> str:
    """Create a Stripe Checkout Session for subscription upgrade and return its hosted URL."""
    stripe = _init_stripe()
    customer_id = ensure_stripe_customer(account, account_store=account_store)
    active_price = price_id or get_stripe_price_id(plan, interval)
    if not active_price:
        raise ValueError(f"No Stripe Price ID configured for {plan} ({interval}).")

    app_url = get_app_url()
    s_url = success_url or f"{app_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    c_url = cancel_url or f"{app_url}/?checkout=canceled"

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": active_price, "quantity": 1}],
        success_url=s_url,
        cancel_url=c_url,
        client_reference_id=account.uid,
        subscription_data={
            "metadata": {
                "uid": account.uid,
                "email": account.email,
                "tier": plan,
                "interval": interval,
            }
        },
        metadata={
            "uid": account.uid,
            "email": account.email,
            "tier": plan,
        },
        allow_promotion_codes=True,
    )
    return str(session.url)


def create_customer_portal_session(
    account: UserAccount,
    *,
    return_url: str | None = None,
    account_store: Any = None,
) -> str:
    """Create a self-service Stripe Customer Portal session and return its URL."""
    stripe = _init_stripe()
    customer_id = ensure_stripe_customer(account, account_store=account_store)
    app_url = get_app_url()
    ret_url = return_url or app_url

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=ret_url,
    )
    return str(session.url)


def create_credit_pack_checkout_session(
    account: UserAccount,
    pack_key: str = "pack_300000",
    *,
    success_url: str | None = None,
    cancel_url: str | None = None,
    account_store: Any = None,
) -> str:
    """Create a one-time Stripe Checkout Session to buy simulation credit packs."""
    if pack_key not in CREDIT_PACKS:
        raise ValueError(f"Unknown credit pack: {pack_key}")
    pack = CREDIT_PACKS[pack_key]
    stripe = _init_stripe()
    customer_id = ensure_stripe_customer(account, account_store=account_store)

    app_url = get_app_url()
    s_url = success_url or f"{app_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&pack={pack_key}"
    c_url = cancel_url or f"{app_url}/?checkout=canceled"

    price_id = get_stripe_setting(pack["env_var"])
    if price_id:
        line_items = [{"price": price_id, "quantity": 1}]
    else:
        line_items = [{
            "price_data": {
                "currency": "eur",
                "unit_amount": int(pack["price_eur"] * 100),
                "product_data": {
                    "name": f"Load Forge - {pack['name']}",
                    "description": pack["description"],
                },
            },
            "quantity": 1,
        }]

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=line_items,
        success_url=s_url,
        cancel_url=c_url,
        client_reference_id=account.uid,
        metadata={
            "uid": account.uid,
            "email": account.email,
            "type": "credit_pack",
            "pack_key": pack_key,
            "credits": str(pack["credits"]),
        },
    )
    return str(session.url)


def sync_checkout_session(session_id: str, account_store: Any = None) -> dict[str, Any]:
    """Retrieve a completed checkout session directly from Stripe and sync account state immediately."""
    stripe = _init_stripe()
    session = stripe.checkout.Session.retrieve(session_id)
    mode = session.get("mode")
    meta = session.get("metadata") or {}
    uid = session.get("client_reference_id") or meta.get("uid", "")
    email = meta.get("email", "")
    target = email or uid
    res: dict[str, Any] = {"status": "ok", "mode": mode, "type": meta.get("type", "subscription")}

    if target and account_store:
        if mode == "payment" and meta.get("type") == "credit_pack":
            credits_to_add = int(meta.get("credits", 0))
            if credits_to_add > 0:
                account_store.adjust_credits(target, credits_to_add)
                res["credits"] = credits_to_add
        elif mode == "subscription":
            sub_id = session.get("subscription")
            tier = meta.get("tier", "pro")
            account_store.update_billing_info(
                target,
                stripe_customer_id=session.get("customer"),
                stripe_subscription_id=sub_id,
                subscription_status="active",
                plan=tier,
            )
            res["plan"] = tier
    return res


def process_webhook_event(
    payload: bytes,
    sig_header: str,
    *,
    account_store: Any = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Verify and process an incoming Stripe webhook event idempotently."""
    stripe = _init_stripe()
    webhook_secret = get_stripe_webhook_secret()
    if not webhook_secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured.")

    event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    event_id = str(event["id"])
    event_type = str(event["type"])
    data_obj = event["data"]["object"]

    # Idempotency check via Firestore if available
    if firestore_client is not None:
        try:
            event_ref = firestore_client.collection("stripe_events").document(event_id)
            if event_ref.get().exists:
                logger.info("Stripe event %s (%s) already processed; skipping.", event_id, event_type)
                return {"status": "already_processed", "event_id": event_id}
        except Exception:
            logger.exception("Idempotency check failed for event %s", event_id)

    logger.info("Processing Stripe webhook event: %s (%s)", event_id, event_type)

    def extract_uid(obj: dict[str, Any]) -> str:
        if obj.get("client_reference_id"):
            return str(obj["client_reference_id"])
        meta = obj.get("metadata") or {}
        if meta.get("uid"):
            return str(meta["uid"])
        cust_id = obj.get("customer")
        if cust_id and isinstance(cust_id, str):
            try:
                c_obj = stripe.Customer.retrieve(cust_id)
                if c_obj and hasattr(c_obj, "metadata") and c_obj.metadata.get("uid"):
                    return str(c_obj.metadata["uid"])
            except Exception:
                pass
        return ""

    def extract_email(obj: dict[str, Any]) -> str:
        meta = obj.get("metadata") or {}
        if meta.get("email"):
            return str(meta["email"])
        cust_id = obj.get("customer")
        if cust_id and isinstance(cust_id, str):
            try:
                c_obj = stripe.Customer.retrieve(cust_id)
                if c_obj and hasattr(c_obj, "email") and c_obj.email:
                    return str(c_obj.email)
            except Exception:
                pass
        cust_details = obj.get("customer_details") or {}
        if cust_details.get("email"):
            return str(cust_details["email"])
        return ""

    result_summary: dict[str, Any] = {"status": "success", "event_id": event_id, "type": event_type}

    if event_type == "checkout.session.completed":
        sub_id = data_obj.get("subscription")
        uid = extract_uid(data_obj)
        email = extract_email(data_obj)
        customer_id = data_obj.get("customer")
        target = email or uid
        mode = data_obj.get("mode")
        meta = data_obj.get("metadata") or {}

        if mode == "payment" and meta.get("type") == "credit_pack":
            credits_to_add = int(meta.get("credits", 0))
            if target and account_store and credits_to_add > 0:
                account_store.adjust_credits(target, credits_to_add)
            result_summary["action"] = f"added_{credits_to_add}_credits"
            result_summary["credits"] = credits_to_add
        else:
            tier = meta.get("tier", "pro")
            if target and account_store:
                account_store.update_billing_info(
                    target,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=sub_id,
                    subscription_status="active",
                    plan=tier,
                )
            result_summary["action"] = "checkout_completed"

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub_id = data_obj.get("id")
        status = data_obj.get("status")  # active, trialing, past_due, canceled
        customer_id = data_obj.get("customer")
        current_period_end_ts = data_obj.get("current_period_end")
        period_end = (
            datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
            if current_period_end_ts
            else None
        )
        cancel_at_period_end = bool(data_obj.get("cancel_at_period_end", False))
        meta = data_obj.get("metadata") or {}
        tier = meta.get("tier", "pro") if status in ("active", "trialing", "past_due") else "free"
        uid = extract_uid(data_obj)
        email = extract_email(data_obj)
        target = email or uid
        if target and account_store:
            account_store.update_billing_info(
                target,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                subscription_status=status,
                current_period_end=period_end,
                cancel_at_period_end=cancel_at_period_end,
                plan=tier,
            )
        # Store subscription audit document in Firestore if client provided
        if firestore_client is not None and sub_id:
            try:
                firestore_client.collection("subscriptions").document(sub_id).set({
                    "subscription_id": sub_id,
                    "stripe_customer_id": customer_id,
                    "uid": uid,
                    "email": email,
                    "status": status,
                    "tier": tier,
                    "current_period_end": period_end.isoformat() if period_end else None,
                    "cancel_at_period_end": cancel_at_period_end,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, merge=True)
            except Exception:
                logger.exception("Failed to write subscriptions audit document")
        result_summary["action"] = "subscription_synced"

    elif event_type == "customer.subscription.deleted":
        sub_id = data_obj.get("id")
        uid = extract_uid(data_obj)
        email = extract_email(data_obj)
        target = email or uid
        if target and account_store:
            account_store.update_billing_info(
                target,
                subscription_status="canceled",
                plan="free",
                cancel_at_period_end=False,
            )
        if firestore_client is not None and sub_id:
            try:
                firestore_client.collection("subscriptions").document(sub_id).set({
                    "status": "canceled",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, merge=True)
            except Exception:
                pass
        result_summary["action"] = "subscription_canceled"

    elif event_type == "invoice.payment_failed":
        sub_id = data_obj.get("subscription")
        uid = extract_uid(data_obj)
        email = extract_email(data_obj)
        target = email or uid
        if target and account_store:
            account_store.update_billing_info(
                target,
                subscription_status="past_due",
            )
        result_summary["action"] = "payment_failed_past_due"

    elif event_type == "invoice.payment_succeeded":
        sub_id = data_obj.get("subscription")
        uid = extract_uid(data_obj)
        email = extract_email(data_obj)
        target = email or uid
        if target and account_store:
            account_store.update_billing_info(
                target,
                subscription_status="active",
            )
        result_summary["action"] = "payment_succeeded_active"

    # Commit event to stripe_events collection for idempotency
    if firestore_client is not None:
        try:
            firestore_client.collection("stripe_events").document(event_id).set({
                "event_id": event_id,
                "event_type": event_type,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "created_at": event.get("created"),
            })
        except Exception:
            logger.exception("Failed to commit event %s to stripe_events collection", event_id)

    return result_summary
