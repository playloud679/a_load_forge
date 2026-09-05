# Load Forge — Stripe Payments & Billing Infrastructure

Guide for configuring, testing, and deploying the Stripe hosted billing and webhook synchronization infrastructure for Load Forge.

---

## 1. Architecture Overview

Load Forge adopts a **zero-liability, hosted billing architecture**:

1. **Stripe Checkout**: Generates hosted checkout sessions for Pro subscriptions (monthly or yearly). No credit card or PCI data touches Load Forge servers.
2. **Stripe Customer Portal**: Self-service management for active subscribers to update payment methods, download invoices/receipts, or cancel subscriptions.
3. **Dedicated Webhook Service (`load-forge-webhooks`)**: A lightweight FastAPI microservice deployed on Google Cloud Run that cryptographically validates Stripe webhook payloads (`stripe.Webhook.construct_event`), enforces idempotency using the Firestore `stripe_events` collection, and atomically syncs `users/{uid}` and `subscriptions/{sub_id}` documents.
4. **Firestore Storage**: Single source of truth for app entitlements (`tier: "pro"`, `subscription_status: "active"`).

---

## 2. Configuration Parameters

The billing system reads configuration from environment variables or Streamlit secrets (`[stripe]` section):

| Environment Variable | Description | Example |
|---|---|---|
| `STRIPE_SECRET_KEY` | Stripe API Secret Key (test or live) | `sk_test_...` / `sk_live_...` |
| `STRIPE_PUBLISHABLE_KEY` | Stripe Publishable Key | `pk_test_...` / `pk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Secret signing key from Stripe Webhook console | `whsec_...` |
| `STRIPE_PRICE_PRO_MONTHLY` | Stripe Price ID for Pro Monthly plan | `price_1P...` |
| `STRIPE_PRICE_PRO_YEARLY` | Stripe Price ID for Pro Yearly plan | `price_1P...` |
| `STRIPE_PRICE_TEAM_MONTHLY` | Stripe Price ID for Team plan (optional) | `price_1P...` |
| `LOAD_FORGE_APP_URL` | Public production URL of the Streamlit app | `https://load-forge-665148536194.europe-west1.run.app` |

---

## 3. Stripe Dashboard Setup

1. **Create Product**:
   - Name: `Load Forge Pro`
   - Description: `Advanced acoustic loudspeaker load design & optimizer with 2,500 credits and unlimited cloud projects.`
2. **Add Prices**:
   - **Monthly**: Recurring, €9.00 EUR / month.
   - **Yearly**: Recurring, €79.00 EUR / year.
3. **Configure Customer Portal**:
   - In Stripe Dashboard -> Settings -> Billing -> Customer Portal:
     - Enable "Allow customers to switch plans" or "Allow customers to cancel subscriptions" (set to cancel at end of billing cycle).
     - Enable "Allow customers to update payment methods".
     - Enable "Invoice history".

---

## 4. Deploying the Webhook Service to Google Cloud Run

The webhook microservice lives in `webhooks/` with its own `Dockerfile` and `requirements.txt`.

### Step 1: Deploy with gcloud
```bash
gcloud run deploy load-forge-webhooks \
  --source . \
  --dockerfile webhooks/Dockerfile \
  --project civic-radio-502611-i8 \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars LOAD_FORGE_GCP_PROJECT=civic-radio-502611-i8,LOAD_FORGE_FIRESTORE_DATABASE=(default)
```

### Step 2: Configure Secrets in Cloud Run
Set the Stripe secret keys in Google Secret Manager or directly as Cloud Run secrets:
```bash
gcloud run services update load-forge-webhooks \
  --project civic-radio-502611-i8 \
  --region europe-west1 \
  --set-secrets STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest
```

---

## 5. Registering the Webhook Endpoint in Stripe

1. Go to **Stripe Dashboard -> Developers -> Webhooks -> Add endpoint**.
2. Endpoint URL:
   `https://load-forge-webhooks-665148536194.europe-west1.run.app/stripe/webhook`
3. Select events to listen to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Copy the **Signing secret** (`whsec_...`) and store it as `STRIPE_WEBHOOK_SECRET`.

---

## 6. Local Testing with Stripe CLI

To test the entire flow locally before going live:

```bash
# 1. Start the webhook server locally
.venv/bin/uvicorn webhooks.main:app --port 8080

# 2. In another terminal, forward Stripe events
stripe listen --forward-to localhost:8080/stripe/webhook

# 3. Trigger test events
stripe trigger checkout.session.completed
stripe trigger customer.subscription.updated
```
