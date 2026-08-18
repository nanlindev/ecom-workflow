#!/usr/bin/env python3
"""Seed / smoke P3: Woo product ingest + inventory sync writeback statuses.

Usage (sidecar up on :8003):
  python3 scripts/seed_demo_scenario_p3.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid

BASE = os.getenv("ECOM_SIDECAR_URL", "http://127.0.0.1:8003")
STORE_KEY = os.getenv("ECOM_DEMO_STORE_KEY", "demo-shopify")
STORE_ID = os.getenv("ECOM_DEMO_STORE_ID", "").strip() or None


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Correlation-Id": str(uuid.uuid4())},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    corr = str(uuid.uuid4())
    print("== Woo product ingest ==")
    woo = post(
        "/ingest/woocommerce",
        {
            "raw_body": {
                "id": 88001,
                "name": "The Multi-managed Snowboard",
                "sku": "sku-managed-1",
                "stock_quantity": 37,
                "_topic": "product.updated",
            },
            "headers": {"x-wc-webhook-topic": "product.updated"},
            "store_key": STORE_KEY,
            "correlation_id": corr,
            "skip_verify": True,
        },
    )
    print({k: woo.get(k) for k in ("ok", "platform", "event_type", "store_id", "dispatch")})
    # dispatch.inventory is false while Shopify is master; this script calls /inventory/sync next.
    if not woo.get("ok"):
        return 1

    store_id = STORE_ID or woo["store_id"]
    print("== Inventory sync (expect drift vs Shopify master if present) ==")
    sync = post(
        "/inventory/sync",
        {"store_id": store_id, "sku": "sku-managed-1", "correlation_id": corr},
    )
    print(
        {
            k: sync.get(k)
            for k in (
                "ok",
                "mode",
                "has_drift",
                "writeback_status",
                "channel_writebacks",
                "should_alert_slack",
            )
        }
    )

    print("== Ops summary daily ==")
    summary = post("/ops/summary", {"period": "daily", "store_id": store_id, "correlation_id": corr})
    print({k: summary.get(k) for k in ("ok", "orders_count", "should_alert_slack", "period")})

    print("== Keepalive ==")
    keep = post("/ops/keepalive", {"correlation_id": corr, "ping_channels": True})
    print({k: keep.get(k) for k in ("ok", "database", "channel_pings", "should_alert_slack")})
    return 0 if sync.get("ok") and summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
