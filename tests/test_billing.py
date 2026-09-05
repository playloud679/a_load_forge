"""Tests for Stripe Billing and Subscription Infrastructure."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.saas import UserAccount, InMemoryUserAccountStore
import src.billing as billing


class TestBilling(unittest.TestCase):

    def test_stripe_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(billing.is_stripe_configured())

    def test_ensure_stripe_customer_existing(self):
        acc = UserAccount(
            uid="u1",
            email="test@example.com",
            name="Tester",
            plan="free",
            credits_balance=100,
            credits_monthly_quota=100,
            quota_reset_at=datetime.now(timezone.utc),
            total_simulations_run=0,
            is_admin=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            stripe_customer_id="cus_existing123",
        )
        cid = billing.ensure_stripe_customer(acc)
        self.assertEqual(cid, "cus_existing123")

    def test_ensure_stripe_customer_creation(self):
        acc = UserAccount(
            uid="u2",
            email="new@example.com",
            name="New User",
            plan="free",
            credits_balance=100,
            credits_monthly_quota=100,
            quota_reset_at=datetime.now(timezone.utc),
            total_simulations_run=0,
            is_admin=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_store = InMemoryUserAccountStore()
        mock_store.get_or_create_account(acc.uid, acc.email, acc.name)

        mock_customer = MagicMock(id="cus_created999")
        with patch("stripe.Customer.create", return_value=mock_customer), \
             patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"}):
            cid = billing.ensure_stripe_customer(acc, account_store=mock_store)
            self.assertEqual(cid, "cus_created999")
            self.assertEqual(acc.stripe_customer_id, "cus_created999")
            saved = mock_store.get_or_create_account(acc.uid, acc.email, acc.name)
            self.assertEqual(saved.stripe_customer_id, "cus_created999")

    def test_create_checkout_session(self):
        acc = UserAccount(
            uid="u3",
            email="checkout@example.com",
            name="Checkout User",
            plan="free",
            credits_balance=100,
            credits_monthly_quota=100,
            quota_reset_at=datetime.now(timezone.utc),
            total_simulations_run=0,
            is_admin=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            stripe_customer_id="cus_checkout123",
        )
        mock_session = MagicMock(url="https://checkout.stripe.com/pay/cs_test_abc")
        with patch("stripe.checkout.Session.create", return_value=mock_session), \
             patch.dict("os.environ", {
                 "STRIPE_SECRET_KEY": "sk_test_123",
                 "STRIPE_PRICE_PRO_MONTHLY": "price_pro_123",
             }):
            url = billing.create_checkout_session(acc, plan="pro", interval="monthly")
            self.assertEqual(url, "https://checkout.stripe.com/pay/cs_test_abc")

    def test_create_portal_session(self):
        acc = UserAccount(
            uid="u4",
            email="portal@example.com",
            name="Portal User",
            plan="pro",
            credits_balance=2500,
            credits_monthly_quota=2500,
            quota_reset_at=datetime.now(timezone.utc),
            total_simulations_run=0,
            is_admin=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            stripe_customer_id="cus_portal123",
        )
        mock_portal = MagicMock(url="https://billing.stripe.com/p/session/portal_xyz")
        with patch("stripe.billing_portal.Session.create", return_value=mock_portal), \
             patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"}):
            url = billing.create_customer_portal_session(acc)
            self.assertEqual(url, "https://billing.stripe.com/p/session/portal_xyz")

    def test_process_webhook_events_idempotency_and_sync(self):
        store = InMemoryUserAccountStore()
        user = store.get_or_create_account("u5", "sub@example.com", "Subscriber")
        self.assertEqual(user.plan, "free")

        # 1. Checkout session completed
        event_checkout = {
            "id": "evt_chk_1",
            "type": "checkout.session.completed",
            "created": 1700000000,
            "data": {
                "object": {
                    "id": "cs_1",
                    "client_reference_id": "u5",
                    "customer": "cus_sub5",
                    "subscription": "sub_active_1",
                    "metadata": {"tier": "pro", "email": "sub@example.com"},
                }
            }
        }

        with patch("stripe.Webhook.construct_event", return_value=event_checkout), \
             patch.dict("os.environ", {
                 "STRIPE_SECRET_KEY": "sk_test_123",
                 "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
             }):
            res = billing.process_webhook_event(b"dummy", "dummy_sig", account_store=store)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["action"], "checkout_completed")
            updated_user = store.get_or_create_account("u5", "sub@example.com", "Subscriber")
            self.assertEqual(updated_user.plan, "pro")
            self.assertEqual(updated_user.stripe_subscription_id, "sub_active_1")
            self.assertEqual(updated_user.subscription_status, "active")
            self.assertTrue(updated_user.has_pro_access())

        # 2. Subscription deleted
        event_deleted = {
            "id": "evt_del_2",
            "type": "customer.subscription.deleted",
            "created": 1700001000,
            "data": {
                "object": {
                    "id": "sub_active_1",
                    "customer": "cus_sub5",
                    "metadata": {"uid": "u5", "email": "sub@example.com"},
                }
            }
        }

        with patch("stripe.Webhook.construct_event", return_value=event_deleted), \
             patch.dict("os.environ", {
                 "STRIPE_SECRET_KEY": "sk_test_123",
                 "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
             }):
            res = billing.process_webhook_event(b"dummy", "dummy_sig", account_store=store)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["action"], "subscription_canceled")
            updated_user = store.get_or_create_account("u5", "sub@example.com", "Subscriber")
            self.assertEqual(updated_user.plan, "free")
            self.assertEqual(updated_user.subscription_status, "canceled")
            self.assertFalse(updated_user.has_pro_access())

    def test_webhook_fastapi_endpoints(self):
        from fastapi.testclient import TestClient
        with patch("google.cloud.firestore.Client"):
            import webhooks.main as wm
            client = TestClient(wm.app)
            r = client.get("/health")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "healthy")

            # Missing header -> 400
            r_post = client.post("/stripe/webhook", content=b"{}")
            self.assertEqual(r_post.status_code, 400)


if __name__ == "__main__":
    unittest.main()
