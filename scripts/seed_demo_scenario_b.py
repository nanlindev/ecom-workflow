#!/usr/bin/env python3
"""Seed DEMO Scenario B: competitor snapshot → pricing recommend → abandon enroll/advance (no email).

Usage (sidecar on :8003):
  export ECOM_SIDECAR_URL=http://127.0.0.1:8003
  export ECOM_DEMO_STORE_ID=<uuid from Scenario A>
  # If shell has HTTP_PROXY, either unset it or rely on this script's no-proxy opener.
  python3 scripts/seed_demo_scenario_b.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Prefer 127.0.0.1 so local proxy tools are less likely to intercept "localhost".
SIDECAR = os.getenv("ECOM_SIDECAR_URL", "http://127.0.0.1:8003").rstrip("/")
STORE_ID = os.getenv("ECOM_DEMO_STORE_ID", "").strip()

# Never send sidecar calls through HTTP(S)_PROXY (common WSL Clash 502 source).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _call(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> dict:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        headers["X-Correlation-Id"] = str(payload.get("correlation_id") or "")
    req = urllib.request.Request(f"{SIDECAR}{path}", data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:800]
        raise SystemExit(f"HTTP {e.code} {method} {SIDECAR}{path}\n{body}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"URL error {method} {SIDECAR}{path}: {e}") from None


def post(path: str, payload: dict) -> dict:
    return _call("POST", path, payload)


def get(path: str) -> dict:
    return _call("GET", path, None, timeout=30)


def main() -> None:
    global STORE_ID
    print(f"sidecar={SIDECAR} (proxy bypassed)")
    health = get("/health")
    if health.get("status") not in {"healthy", "degraded"}:
        print("sidecar unhealthy", health, file=sys.stderr)
        sys.exit(1)

    if not STORE_ID:
        print("Set ECOM_DEMO_STORE_ID (from Scenario A store_id). Trying targets…")
        targets = get("/competitors/targets")
        STORE_ID = (targets.get("store_id") or "").strip()
        if not STORE_ID:
            print("ERROR: export ECOM_DEMO_STORE_ID=<uuid>", file=sys.stderr)
            sys.exit(1)

    corr = "00000000-0000-4000-8000-0000000000b1"
    parsed = post(
        "/competitors/parse",
        {
            "store_id": STORE_ID,
            "url": "https://example.com/products/tee-black-m",
            "raw_content": "<html><body><h1>Competitor Tee</h1><p>Price: $84.00</p></body></html>",
            "sku": "TEE-BLACK-M",
            "source_name": "example-comp",
            "correlation_id": corr,
        },
    )
    print(
        "competitor parse:",
        json.dumps({k: parsed.get(k) for k in ("ok", "price", "snapshot_id", "fallback_used")}, indent=2),
    )

    rec = post(
        "/pricing/recommend",
        {
            "store_id": STORE_ID,
            "sku": "TEE-BLACK-M",
            "current_price": 89,
            "cost": 35,
            "correlation_id": "00000000-0000-4000-8000-0000000000b2",
        },
    )
    print(
        "pricing recommend:",
        json.dumps(
            {
                k: rec.get(k)
                for k in (
                    "ok",
                    "recommendation_id",
                    "current_price",
                    "recommended_price",
                    "should_alert_slack",
                    "fallback_used",
                    "status",
                )
            },
            indent=2,
        ),
    )

    rfm = post("/insights/rfm", {"store_id": STORE_ID, "correlation_id": "00000000-0000-4000-8000-0000000000b3"})
    churn = post("/insights/churn", {"store_id": STORE_ID, "correlation_id": "00000000-0000-4000-8000-0000000000b4"})
    print(
        "insights:",
        json.dumps({"rfm": rfm.get("customers_updated"), "churn": churn.get("customers_updated")}, indent=2),
    )

    enroll = post(
        "/marketing/enroll",
        {
            "store_id": STORE_ID,
            "email": "buyer@example.com",
            "campaign_key": "abandon_cart_default",
            "campaign_type": "abandon_cart",
            "correlation_id": "00000000-0000-4000-8000-0000000000b5",
        },
    )
    print(
        "enroll:",
        json.dumps({k: enroll.get(k) for k in ("ok", "enrollment_id", "status", "send_status")}, indent=2),
    )

    adv = post(
        "/marketing/advance",
        {
            "store_id": STORE_ID,
            "limit": 10,
            "correlation_id": "00000000-0000-4000-8000-0000000000b6",
        },
    )
    print(
        "advance:",
        json.dumps(
            {
                "ok": adv.get("ok"),
                "count": adv.get("count"),
                "allow_send": adv.get("allow_send"),
                "mode": adv.get("mode"),
                "first_send_status": (adv.get("advanced") or [{}])[0].get("send_status"),
            },
            indent=2,
        ),
    )

    print("\nDEMO Scenario B seed complete.")
    print(f"store_id={STORE_ID}")
    print(f"recommendation_id={rec.get('recommendation_id')}")
    print("Import P2 workflows; Pricing Slack should show Approve/Reject; marketing stays skipped_test_mode.")


if __name__ == "__main__":
    main()
