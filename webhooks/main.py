"""Load Forge Stripe Webhook Microservice.

Lightweight FastAPI service for Google Cloud Run to process incoming Stripe
webhook events with cryptographic verification, idempotency tracking, and
Firestore atomic updates.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import src.saas and src.billing
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

from src.billing import process_webhook_event
from src.saas import FirestoreUserAccountStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("load_forge.webhooks")

app = FastAPI(title="Load Forge Webhook Service", version="1.0.0")

# Initialize Firestore clients
GCP_PROJECT = os.environ.get("LOAD_FORGE_GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "civic-radio-502611-i8"
FIRESTORE_DB = os.environ.get("LOAD_FORGE_FIRESTORE_DATABASE", "(default)")

db = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DB)
account_store = FirestoreUserAccountStore(client=db)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "load-forge-webhooks",
        "project": GCP_PROJECT,
        "database": FIRESTORE_DB,
    }


@app.post("/stripe/webhook")
async def handle_stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        logger.warning("Missing stripe-signature header")
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        result = process_webhook_event(
            payload,
            sig_header,
            account_store=account_store,
            firestore_client=db,
        )
        return result
    except ValueError as exc:
        logger.warning("Invalid webhook payload or secret: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Error processing webhook")
        # Returning 500 signals Stripe to retry via exponential backoff
        raise HTTPException(status_code=500, detail="Internal server error")
