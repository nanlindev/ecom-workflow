#!/usr/bin/env python3
"""Seed demo store + inventory/order fixtures for P1 Scenario A.

Usage (with sidecar up, from repo root or python-service):
  DATABASE_URL=postgresql://ecom:ecom@localhost:5432/ecom  # if PG published
  # Or exec inside sidecar:
  docker compose -f docker/compose.yml exec ecom_python_ai python /app/../scripts/...
Prefer HTTP against sidecar when only 8003 is exposed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

# Allow importing domain when run inside container with /app on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-service"))

SIDECAR = os.getenv("ECOM_SIDECAR_URL", "http://localhost:8003")


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SIDECAR}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Correlation-Id": payload.get("correlation_id", "")},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    corr_inv = "00000000-0000-4000-8000-0000000000a1"
    corr_ord = "00000000-0000-4000-8000-0000000000a2"

    # Inventory / product upsert via ingest (skip HMAC for local demo)
    inv = post(
        "/ingest/shopify",
        {
            "store_key": "demo-shopify",
            "correlation_id": corr_inv,
            "skip_verify": True,
            "headers": {
                "x-shopify-topic": "inventory_levels/update",
                "x-shopify-shop-domain": "demo-shopify.myshopify.com",
            },
            "raw_body": {
                "id": 1001,
                "sku": "sku-managed-1",
                "title": "The Multi-managed Snowboard",
                "available": 42,
                "inventory_item_id": 9001,
            },
        },
    )
    print("inventory ingest:", json.dumps({k: inv.get(k) for k in ("ok", "store_id", "event_type", "entities")}, indent=2))

    # Seed a divergent Woo level so Inventory Sync reports drift (test → no writeback)
    store_id = inv["store_id"]
    sync = post(
        "/inventory/sync",
        {
            "store_id": store_id,
            "sku": "sku-managed-1",
            "correlation_id": corr_inv,
            "slave_levels": [
                {
                    "sku": "sku-managed-1",
                    "platform": "woocommerce",
                    "available": 40,
                    "location_key": "default",
                }
            ],
        },
    )
    print(
        "inventory sync:",
        json.dumps(
            {
                k: sync.get(k)
                for k in ("ok", "has_drift", "writeback_status", "mode", "drifts", "should_alert_slack")
            },
            indent=2,
        ),
    )

    order = post(
        "/ingest/shopify",
        {
            "store_key": "demo-shopify",
            "correlation_id": corr_ord,
            "skip_verify": True,
            "headers": {
                "x-shopify-topic": "orders/create",
                "x-shopify-shop-domain": "demo-shopify.myshopify.com",
            },
            "raw_body": {
                "id": 5001,
                "email": "buyer@example.com",
                "currency": "USD",
                "financial_status": "paid",
                "fulfillment_status": None,
                "status": "paid",
                "total_price": "2629.00",
                "subtotal_price": "2629.00",
                "line_items": [
                    {
                        "id": 1,
                        "sku": "sku-managed-1",
                        "title": "The Multi-managed Snowboard",
                        "quantity": 1,
                        "price": "2629.00",
                    }
                ],
                "customer": {"id": 77, "email": "buyer@example.com", "first_name": "Demo"},
            },
        },
    )
    print("order ingest:", json.dumps({k: order.get(k) for k in ("ok", "store_id", "event_type", "entities")}, indent=2))

    tracked = post(
        "/orders/track",
        {
            "store_id": store_id,
            "external_order_id": "5001",
            "correlation_id": corr_ord,
        },
    )
    print(
        "order track:",
        json.dumps({k: tracked.get(k) for k in ("ok", "status", "is_anomaly", "should_alert_slack")}, indent=2),
    )

    ret = post(
        "/returns/decide",
        {
            "store_id": store_id,
            "external_return_id": "R-9001",
            "amount": 120,
            "days_since_order": 5,
            "reason": "size",
            "correlation_id": corr_ord,
        },
    )
    print(
        "return decide:",
        json.dumps({k: ret.get(k) for k in ("ok", "decision", "needs_manual_review", "external_refund_status")}, indent=2),
    )

    print("\nDEMO Scenario A seed complete.")
    print(f"store_id={store_id}")
    print("Set ECOM_DEMO_STORE_ID for Inventory Cron if desired.")


if __name__ == "__main__":
    main()
