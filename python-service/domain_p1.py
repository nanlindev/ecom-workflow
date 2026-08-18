"""P1 domain services: config, Shopify ingest, inventory sync, orders, returns, logs.

All writes go to ecom_postgres. Secrets never stored in PG.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from db import connect

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def get_config() -> dict[str, Any]:
    """Load all config_* tables into nested dicts plus flattened helpers."""
    with connect() as conn:
        with conn.cursor() as cur:
            tables = (
                "config_main",
                "config_inventory",
                "config_pricing",
                "config_marketing",
                "config_notifications",
            )
            result: dict[str, Any] = {}
            flat: dict[str, str] = {}
            for table in tables:
                cur.execute(f"SELECT key, value FROM {table}")
                rows = {r["key"]: r["value"] for r in cur.fetchall()}
                result[table] = rows
                flat.update(rows)
            mode = (flat.get("mode") or "test").lower()
            result["mode"] = mode
            result["flat"] = flat
            result["master_channel"] = (flat.get("master_channel") or "shopify").lower()
            result["slack_enabled"] = _truthy(flat.get("slack_enabled", "true"))
            result["slack_in_test"] = _truthy(flat.get("slack_in_test", "true"))
            return result


def _truthy(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _cfg(flat: dict[str, str], key: str, default: str = "") -> str:
    return flat.get(key, default)


def ensure_store(
    *,
    store_key: str,
    platform: str = "shopify",
    display_name: str | None = None,
    external_shop_id: str | None = None,
) -> dict[str, Any]:
    """Get or create a store by store_key."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM stores WHERE store_key = %s", (store_key,))
            row = cur.fetchone()
            if row:
                incoming = (external_shop_id or "").strip()
                current = (row.get("external_shop_id") or "").strip()
                # Shared Shopify+Woo store: Woo source URL must not stick as Admin handle.
                if (
                    incoming
                    and "myshopify.com" in incoming.lower()
                    and incoming != current
                    and "myshopify.com" not in current.lower()
                ):
                    cur.execute(
                        """
                        UPDATE stores
                        SET external_shop_id = %s, updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (incoming, row["id"]),
                    )
                    updated = cur.fetchone()
                    if updated:
                        return dict(updated)
                return dict(row)
            cur.execute(
                """
                INSERT INTO stores (store_key, display_name, platform, external_shop_id, enabled)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING *
                """,
                (
                    store_key,
                    display_name or store_key,
                    platform if platform in {"shopify", "woocommerce", "amazon", "other"} else "other",
                    external_shop_id,
                ),
            )
            return dict(cur.fetchone())


def write_audit(
    *,
    action: str,
    store_id: str | None = None,
    correlation_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (store_id, correlation_id, action, entity_type, entity_id, detail)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    store_id,
                    correlation_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(detail or {}),
                ),
            )


def write_error_log(
    *,
    workflow_name: str,
    node_name: str,
    error_message: str,
    correlation_id: str | None = None,
    store_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO error_logs (store_id, correlation_id, workflow_name, node_name, error_message, detail)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, created_at
                """,
                (
                    store_id,
                    correlation_id,
                    workflow_name,
                    node_name,
                    error_message[:4000],
                    json.dumps(detail or {}),
                ),
            )
            row = cur.fetchone()
            return {"id": str(row["id"]), "created_at": row["created_at"].isoformat()}


def _parse_body(raw_body: Any) -> dict[str, Any]:
    if isinstance(raw_body, dict):
        return raw_body
    if isinstance(raw_body, (bytes, bytearray)):
        raw_body = raw_body.decode("utf-8", errors="replace")
    if isinstance(raw_body, str):
        text = raw_body.strip()
        if not text:
            return {}
        if text.startswith("{") or text.startswith("["):
            return json.loads(text)
        # Woo Hookshot ping uses application/x-www-form-urlencoded (webhook_id=…).
        if "=" in text and not text.startswith("<"):
            from urllib.parse import parse_qs

            parsed = parse_qs(text, keep_blank_values=True)
            return {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
        return {}
    return {}


def _is_woo_webhook_ping(payload: dict[str, Any], headers: dict[str, Any]) -> bool:
    """True for WooCommerce Hookshot connectivity pings (not product/order events)."""
    if headers.get("x-wc-webhook-topic") or headers.get("x-shopify-topic"):
        return False
    if not isinstance(payload, dict):
        return False
    keys = {k for k in payload.keys() if not str(k).startswith("_")}
    return "webhook_id" in keys and keys <= {"webhook_id"}


def verify_shopify_hmac(raw_body: bytes | str, hmac_header: str | None) -> dict[str, Any]:
    """Verify X-Shopify-Hmac-Sha256. Empty secret skips (dev/demo)."""
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "").strip()
    if not secret:
        return {"valid": True, "skipped": True, "reason": "verification_skipped"}
    if not hmac_header:
        return {"valid": False, "skipped": False, "reason": "missing_signature"}
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    digest = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode()
    if hmac.compare_digest(digest, hmac_header.strip()):
        return {"valid": True, "skipped": False, "reason": "ok"}
    return {"valid": False, "skipped": False, "reason": "signature_mismatch"}


def ingest_shopify(
    *,
    raw_body: Any,
    headers: dict[str, Any] | None = None,
    store_key: str | None = None,
    correlation_id: str | None = None,
    skip_verify: bool = False,
) -> dict[str, Any]:
    """Verify Shopify webhook, normalize, idempotent upsert, return dispatch hints."""
    headers = {str(k).lower(): v for k, v in (headers or {}).items()}
    hmac_header = headers.get("x-shopify-hmac-sha256")
    topic = headers.get("x-shopify-topic") or headers.get("x-shopify-topic".lower()) or ""
    shop_domain = headers.get("x-shopify-shop-domain") or ""

    body_bytes: bytes | str
    if isinstance(raw_body, (bytes, bytearray)):
        body_bytes = bytes(raw_body)
        payload = _parse_body(body_bytes)
    elif isinstance(raw_body, str):
        body_bytes = raw_body
        payload = _parse_body(raw_body)
    else:
        payload = raw_body if isinstance(raw_body, dict) else {}
        body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    verify = {"valid": True, "skipped": True, "reason": "skip_verify_flag"} if skip_verify else verify_shopify_hmac(
        body_bytes, hmac_header
    )
    if not verify["valid"]:
        write_audit(
            action="webhook_signature_rejected",
            detail={"platform": "shopify", "reason": verify.get("reason"), "topic": topic},
        )
        return {
            "ok": False,
            "signature_valid": False,
            "verify": verify,
            "http_status": 401,
        }

    corr = correlation_id or headers.get("x-correlation-id") or _uuid()
    key = store_key or shop_domain.replace(".myshopify.com", "") or _cfg(
        get_config()["flat"], "demo_store_key", "demo-shopify"
    )
    store = ensure_store(store_key=key, platform="shopify", external_shop_id=shop_domain or None)
    store_id = str(store["id"])

    topic_l = (topic or payload.get("_topic") or "").lower()
    event_type = _classify_shopify_topic(topic_l, payload)
    entities: dict[str, Any] = {}

    if event_type in {"inventory", "product"}:
        entities = _upsert_shopify_inventory_or_product(store_id, payload, topic_l, corr)
    elif event_type == "order":
        entities = _upsert_shopify_order(store_id, payload, corr)
    elif event_type == "return":
        entities = _upsert_shopify_return_stub(store_id, payload, corr)
    else:
        write_audit(
            action="ingest_unhandled_topic",
            store_id=store_id,
            correlation_id=corr,
            detail={"topic": topic_l, "keys": list(payload.keys())[:20]},
        )
        event_type = "unknown"

    write_audit(
        action="ingest_upserted",
        store_id=store_id,
        correlation_id=corr,
        entity_type=event_type,
        entity_id=entities.get("primary_id"),
        detail={"topic": topic_l, "entities": {k: v for k, v in entities.items() if k != "raw"}},
    )

    dispatch = {
        "inventory": _should_dispatch_inventory(
            platform="shopify", event_type=event_type, sku=entities.get("sku")
        ),
        "order": event_type == "order",
        "returns": event_type == "return",
    }
    return {
        "ok": True,
        "signature_valid": True,
        "verify": verify,
        "http_status": 200,
        "correlation_id": corr,
        "store_id": store_id,
        "store_key": key,
        "platform": "shopify",
        "topic": topic_l,
        "event_type": event_type,
        "entities": entities,
        "dispatch": dispatch,
    }


def verify_woo_signature(raw_body: bytes | str, signature_header: str | None) -> dict[str, Any]:
    """Verify X-WC-Webhook-Signature (HMAC-SHA256 base64). Empty secret skips (dev/demo)."""
    secret = os.getenv("WOO_WEBHOOK_SECRET", "").strip()
    if not secret:
        return {"valid": True, "skipped": True, "reason": "verification_skipped"}
    if not signature_header:
        return {"valid": False, "skipped": False, "reason": "missing_signature"}
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    digest = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode()
    if hmac.compare_digest(digest, signature_header.strip()):
        return {"valid": True, "skipped": False, "reason": "ok"}
    return {"valid": False, "skipped": False, "reason": "signature_mismatch"}


def ingest_woocommerce(
    *,
    raw_body: Any,
    headers: dict[str, Any] | None = None,
    store_key: str | None = None,
    correlation_id: str | None = None,
    skip_verify: bool = False,
) -> dict[str, Any]:
    """Verify Woo webhook, normalize to same internal schema as Shopify, return dispatch hints."""
    headers = {str(k).lower(): v for k, v in (headers or {}).items()}
    sig = headers.get("x-wc-webhook-signature")
    topic = headers.get("x-wc-webhook-topic") or headers.get("x-wc-webhook-resource") or ""
    source = headers.get("x-wc-webhook-source") or ""

    body_bytes: bytes | str
    if isinstance(raw_body, (bytes, bytearray)):
        body_bytes = bytes(raw_body)
        payload = _parse_body(body_bytes)
    elif isinstance(raw_body, str):
        body_bytes = raw_body
        payload = _parse_body(raw_body)
    else:
        payload = raw_body if isinstance(raw_body, dict) else {}
        body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    # Hookshot connectivity ping — ack without HMAC / upsert (no business topic headers).
    if _is_woo_webhook_ping(payload, headers):
        corr = correlation_id or headers.get("x-correlation-id") or _uuid()
        write_audit(
            action="woo_webhook_ping",
            correlation_id=corr,
            detail={"webhook_id": payload.get("webhook_id"), "platform": "woocommerce"},
        )
        return {
            "ok": True,
            "signature_valid": True,
            "verify": {"valid": True, "skipped": True, "reason": "woo_hookshot_ping"},
            "http_status": 200,
            "correlation_id": corr,
            "store_id": None,
            "store_key": store_key,
            "platform": "woocommerce",
            "topic": "ping",
            "event_type": "ping",
            "entities": {"webhook_id": payload.get("webhook_id")},
            "dispatch": {"inventory": False, "order": False, "returns": False},
        }

    verify = (
        {"valid": True, "skipped": True, "reason": "skip_verify_flag"}
        if skip_verify
        else verify_woo_signature(body_bytes, sig)
    )
    if not verify["valid"]:
        write_audit(
            action="webhook_signature_rejected",
            detail={"platform": "woocommerce", "reason": verify.get("reason"), "topic": topic},
        )
        return {
            "ok": False,
            "signature_valid": False,
            "verify": verify,
            "http_status": 401,
        }

    corr = correlation_id or headers.get("x-correlation-id") or _uuid()
    # Shared store_key with Shopify for multi-channel SoT; channel is on listings/inventory_levels.
    # Do not persist Woo site URL as external_shop_id (breaks Shopify Admin deep links).
    key = store_key or _cfg(get_config()["flat"], "demo_store_key", "demo-shopify")
    shopify_source = source.strip() if source and "myshopify.com" in source.lower() else None
    store = ensure_store(store_key=key, platform="woocommerce", external_shop_id=shopify_source)
    store_id = str(store["id"])

    topic_l = (topic or payload.get("_topic") or "").lower()
    event_type = _classify_woo_topic(topic_l, payload)
    entities: dict[str, Any] = {}
    order_shaped_return = event_type == "return" and _woo_payload_is_order_shape(payload)

    if event_type in {"inventory", "product"}:
        entities = _upsert_woo_product(store_id, payload, topic_l, corr)
    elif event_type == "order":
        entities = _upsert_woo_order(store_id, payload, corr)
    elif event_type == "return":
        if order_shaped_return:
            order_entities = _upsert_woo_order(store_id, payload, corr)
            entities = _upsert_woo_return_stub(store_id, payload, corr)
            entities["order_id"] = order_entities.get("primary_id")
            entities["external_order_id"] = order_entities.get("external_order_id")
            entities["order_upserted"] = True
        else:
            entities = _upsert_woo_return_stub(store_id, payload, corr)
    else:
        write_audit(
            action="ingest_unhandled_topic",
            store_id=store_id,
            correlation_id=corr,
            detail={"platform": "woocommerce", "topic": topic_l, "keys": list(payload.keys())[:20]},
        )
        event_type = "unknown"

    write_audit(
        action="ingest_upserted",
        store_id=store_id,
        correlation_id=corr,
        entity_type=event_type,
        entity_id=entities.get("primary_id"),
        detail={"platform": "woocommerce", "topic": topic_l, "entities": {k: v for k, v in entities.items() if k != "raw"}},
    )

    dispatch = {
        # Slave channel ingest updates SoT only; master webhook fans out Inventory Sync.
        "inventory": _should_dispatch_inventory(
            platform="woocommerce", event_type=event_type, sku=entities.get("sku")
        ),
        # Also run Order Tracker when refund arrived via order.updated payload.
        "order": event_type == "order" or order_shaped_return,
        "returns": event_type == "return",
    }
    return {
        "ok": True,
        "signature_valid": True,
        "verify": verify,
        "http_status": 200,
        "correlation_id": corr,
        "store_id": store_id,
        "store_key": key,
        "platform": "woocommerce",
        "topic": topic_l,
        "event_type": event_type,
        "entities": entities,
        "dispatch": dispatch,
    }


def _woo_payload_is_order_shape(payload: dict[str, Any]) -> bool:
    """True when body looks like REST Order (webhook order.*), not Order Refunds resource."""
    if not isinstance(payload, dict):
        return False
    if payload.get("order_key") or payload.get("number") is not None:
        return True
    if payload.get("billing") or payload.get("shipping"):
        return True
    if payload.get("order_id") and payload.get("amount") is not None and not payload.get("status"):
        return False
    if payload.get("line_items") and payload.get("status") is not None:
        return True
    return False


def _woo_latest_refund_entry(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pick newest entry from Order.refunds[] (REST order shape)."""
    refunds = payload.get("refunds")
    if not isinstance(refunds, list) or not refunds:
        return None
    entries = [r for r in refunds if isinstance(r, dict)]
    if not entries:
        return None

    def _sort_key(r: dict[str, Any]) -> int:
        try:
            return int(r.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    return max(entries, key=_sort_key)


def _woo_payload_indicates_refund(payload: dict[str, Any]) -> bool:
    """Detect refund intent on an Order webhook body (core has no dedicated refunds webhook)."""
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").lower().replace("_", "-")
    if status in {"refunded", "partially-refunded"}:
        return True
    if _woo_latest_refund_entry(payload):
        return True
    # Some builds expose aggregate refunded total on the order.
    try:
        if float(payload.get("refunded_total") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _classify_woo_topic(topic: str, payload: dict[str, Any]) -> str:
    t = topic.lower()
    if "refund" in t or "return" in t:
        return "return"
    if "order" in t:
        if _woo_payload_indicates_refund(payload):
            return "return"
        return "order"
    if "product" in t or "stock" in t:
        return "product"
    if _woo_payload_indicates_refund(payload) and _woo_payload_is_order_shape(payload):
        return "return"
    if payload.get("line_items") or payload.get("number") or payload.get("order_key"):
        if _woo_payload_indicates_refund(payload):
            return "return"
        return "order"
    if payload.get("amount") is not None and (payload.get("reason") is not None or payload.get("order_id")):
        return "return"
    if payload.get("sku") is not None or payload.get("stock_quantity") is not None or payload.get("variations"):
        return "product"
    return "unknown"


def _upsert_woo_product(
    store_id: str,
    payload: dict[str, Any],
    topic: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Upsert Woo product/variation into products + listings + inventory_levels (platform=woocommerce)."""
    # Variations webhook may nest; simple products use top-level sku/stock_quantity.
    sku = (
        payload.get("sku")
        or _first_woo_variation_sku(payload)
        or f"woo-{payload.get('id') or 'unknown'}"
    )
    title = payload.get("name") or payload.get("title") or sku
    available = payload.get("stock_quantity")
    if available is None:
        available = sum(
            int(v.get("stock_quantity") or 0)
            for v in (payload.get("variations") or [])
            if isinstance(v, dict)
        )
    if available is None:
        available = 0
    external_id = str(payload.get("id") or sku)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products (store_id, sku, title, raw, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (store_id, sku) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, products.title),
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id
                """,
                (store_id, sku, title, json.dumps(payload)),
            )
            product_id = str(cur.fetchone()["id"])

            cur.execute(
                """
                INSERT INTO listings (store_id, platform, external_id, sku, product_id, raw, updated_at)
                VALUES (%s, 'woocommerce', %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (store_id, platform, external_id) DO UPDATE SET
                    sku = EXCLUDED.sku,
                    product_id = EXCLUDED.product_id,
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id
                """,
                (store_id, external_id, sku, product_id, json.dumps(payload)),
            )
            listing_id = str(cur.fetchone()["id"])

            cur.execute(
                """
                INSERT INTO inventory_levels (
                    store_id, sku, platform, location_key, available, last_synced_at, raw, updated_at
                )
                VALUES (%s, %s, 'woocommerce', 'default', %s, NOW(), %s::jsonb, NOW())
                ON CONFLICT (store_id, sku, platform, location_key) DO UPDATE SET
                    available = EXCLUDED.available,
                    last_synced_at = NOW(),
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id, available
                """,
                (store_id, sku, int(available), json.dumps(payload)),
            )
            inv = cur.fetchone()

    return {
        "primary_id": str(inv["id"]),
        "product_id": product_id,
        "listing_id": listing_id,
        "sku": sku,
        "available": int(inv["available"]),
        "correlation_id": correlation_id,
        "topic": topic,
        "external_product_id": external_id,
    }


def _first_woo_variation_sku(payload: dict[str, Any]) -> str | None:
    variations = payload.get("variations") or []
    for v in variations:
        if isinstance(v, dict) and v.get("sku"):
            return str(v["sku"])
    return None


def _upsert_woo_order(store_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    external_order_id = str(payload.get("id") or payload.get("number") or _uuid())
    status = str(payload.get("status") or "open")
    email = (payload.get("billing") or {}).get("email") or payload.get("email")
    email = (email or "").lower() or None
    currency = payload.get("currency") or "USD"
    totals = {
        "total_price": payload.get("total"),
        "subtotal_price": payload.get("subtotal") or payload.get("total"),
        "total_tax": payload.get("total_tax"),
    }
    line_items = payload.get("line_items") or []
    ordered_at = payload.get("date_created_gmt") or payload.get("date_created")

    with connect() as conn:
        with conn.cursor() as cur:
            if email:
                cur.execute(
                    """
                    INSERT INTO customers (store_id, email, raw, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (store_id, email) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    (store_id, email, json.dumps({"source": "woocommerce_order"})),
                )
                cur.fetchone()

            cur.execute(
                """
                INSERT INTO orders (
                    store_id, correlation_id, platform, external_order_id, status,
                    fulfillment_status, financial_status, customer_email, currency,
                    totals, line_items, raw, ordered_at, updated_at
                )
                VALUES (
                    %s, %s::uuid, 'woocommerce', %s, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb,
                    COALESCE(%s::timestamptz, NOW()), NOW()
                )
                ON CONFLICT (store_id, platform, external_order_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    financial_status = EXCLUDED.financial_status,
                    customer_email = COALESCE(EXCLUDED.customer_email, orders.customer_email),
                    totals = EXCLUDED.totals,
                    line_items = EXCLUDED.line_items,
                    raw = EXCLUDED.raw,
                    correlation_id = COALESCE(EXCLUDED.correlation_id, orders.correlation_id),
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    store_id,
                    correlation_id,
                    external_order_id,
                    status,
                    None,
                    status,
                    email,
                    currency,
                    json.dumps(totals),
                    json.dumps(line_items),
                    json.dumps(payload),
                    ordered_at,
                ),
            )
            order_id = str(cur.fetchone()["id"])
            for li in line_items:
                if not isinstance(li, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO order_items (
                        order_id, store_id, sku, external_line_id, title, quantity, unit_price, raw
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (order_id, external_line_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        raw = EXCLUDED.raw
                    """,
                    (
                        order_id,
                        store_id,
                        li.get("sku"),
                        str(li.get("id") or li.get("product_id") or _uuid()),
                        li.get("name"),
                        int(li.get("quantity") or 1),
                        li.get("price"),
                        json.dumps(li),
                    ),
                )

    return {
        "primary_id": order_id,
        "external_order_id": external_order_id,
        "status": status,
        "correlation_id": correlation_id,
    }


def _upsert_woo_return_stub(store_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Map Woo refund into returns table.

    Supports:
    - Order webhook body (order.updated): status=refunded and/or refunds[] (same as REST Order)
    - Order Refunds resource body (REST /orders/<id>/refunds): amount, reason, order_id
    """
    refund_entry = _woo_latest_refund_entry(payload)
    order_shaped = _woo_payload_is_order_shape(payload)

    if order_shaped:
        order_ext = str(payload.get("id") or payload.get("number") or "")
        if refund_entry:
            external_return_id = str(
                refund_entry.get("id") or f"woo-refund-{order_ext}-{refund_entry.get('total')}"
            )
            try:
                amount = float(refund_entry.get("total") or refund_entry.get("amount") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            reason = (
                refund_entry.get("reason")
                or payload.get("customer_note")
                or "woocommerce_order_refund"
            )
        else:
            external_return_id = f"woo-order-refunded-{order_ext or _uuid()}"
            try:
                amount = float(
                    payload.get("refunded_total")
                    or payload.get("total")
                    or 0
                )
            except (TypeError, ValueError):
                amount = 0.0
            reason = payload.get("customer_note") or f"woocommerce_status_{payload.get('status')}"
        currency = payload.get("currency") or "USD"
    else:
        order_ext = payload.get("order_id") or (payload.get("meta") or {}).get("order_id")
        order_ext = str(order_ext) if order_ext is not None else ""
        external_return_id = str(payload.get("id") or payload.get("refund_id") or _uuid())
        try:
            amount = float(payload.get("amount") or payload.get("total") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        reason = payload.get("reason") or "woocommerce_refund"
        currency = payload.get("currency") or "USD"

    with connect() as conn:
        with conn.cursor() as cur:
            linked_order_id = None
            if order_ext:
                cur.execute(
                    """
                    SELECT id FROM orders
                    WHERE store_id = %s AND platform = 'woocommerce' AND external_order_id = %s
                    """,
                    (store_id, str(order_ext)),
                )
                found = cur.fetchone()
                if found:
                    linked_order_id = str(found["id"])

            cur.execute(
                "SELECT id FROM returns WHERE store_id = %s AND external_return_id = %s",
                (store_id, external_return_id),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE returns
                    SET amount = %s, reason = COALESCE(%s, reason), raw = %s::jsonb,
                        order_id = COALESCE(%s, order_id),
                        correlation_id = COALESCE(%s, correlation_id), updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        amount,
                        reason,
                        json.dumps(payload),
                        linked_order_id,
                        correlation_id,
                        existing["id"],
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO returns (
                        store_id, order_id, external_return_id, decision, amount, currency, reason,
                        status, correlation_id, raw, updated_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s, %s, %s, 'open', %s, %s::jsonb, NOW())
                    RETURNING id
                    """,
                    (
                        store_id,
                        linked_order_id,
                        external_return_id,
                        amount,
                        currency,
                        reason,
                        correlation_id,
                        json.dumps(payload),
                    ),
                )
            rid = str(cur.fetchone()["id"])

    return {
        "primary_id": rid,
        "external_return_id": external_return_id,
        "external_order_id": order_ext or None,
        "amount": amount,
        "reason": reason,
        "correlation_id": correlation_id,
        "source_shape": "order" if order_shaped else "refund_resource",
    }


def _is_unresolved_sku(sku: Any) -> bool:
    """True for empty or synthetic ext-* SKUs invented from SKU-less inventory webhooks."""
    text = str(sku or "").strip()
    return (not text) or text.startswith("ext-")


def _should_dispatch_inventory(*, platform: str, event_type: str, sku: Any) -> bool:
    """Only the configured master channel may fan out Inventory Sync."""
    if event_type not in {"inventory", "product"}:
        return False
    if _is_unresolved_sku(sku):
        return False
    master = (get_config().get("master_channel") or "shopify").lower()
    return (platform or "").lower() == master


def _shopify_payload_sku(payload: dict[str, Any]) -> str | None:
    sku = (
        payload.get("sku")
        or (payload.get("variant") or {}).get("sku")
        or _first_variant_sku(payload)
    )
    text = str(sku).strip() if sku else ""
    if not text or text.startswith("ext-"):
        return None
    return text


def _shopify_inventory_item_id(payload: dict[str, Any]) -> Any:
    from channels.shopify_admin import extract_shopify_inventory_ids

    return extract_shopify_inventory_ids(payload).get("inventory_item_id")


def _classify_shopify_topic(topic: str, payload: dict[str, Any]) -> str:
    if "refund" in topic or "return" in topic:
        return "return"
    if "inventory" in topic:
        return "inventory"
    if "product" in topic:
        return "product"
    if "order" in topic:
        return "order"
    # Heuristic for demo payloads without topic header
    if "inventory_item_id" in payload or "available" in payload:
        return "inventory"
    if "line_items" in payload or "order_number" in payload:
        return "order"
    if "variants" in payload or "product_type" in payload:
        return "product"
    return "unknown"


def _upsert_shopify_inventory_or_product(
    store_id: str,
    payload: dict[str, Any],
    topic: str,
    correlation_id: str,
) -> dict[str, Any]:
    item_id = _shopify_inventory_item_id(payload)
    sku = _shopify_payload_sku(payload) or _sku_from_shopify_inventory_item(store_id, item_id)
    if not sku:
        sku = _sku_from_shopify_admin_inventory_item(item_id)

    if _is_unresolved_sku(sku):
        write_audit(
            action="ingest_unresolved_sku",
            store_id=store_id,
            correlation_id=correlation_id,
            entity_type="inventory",
            detail={
                "topic": topic,
                "inventory_item_id": item_id,
                "payload_keys": list(payload.keys())[:20],
            },
        )
        return {
            "primary_id": None,
            "sku": None,
            "unresolved_sku": True,
            "inventory_item_id": item_id,
            "available": payload.get("available"),
            "correlation_id": correlation_id,
            "topic": topic,
        }

    available = payload.get("available")
    if available is None and "variants" in payload:
        available = sum(int(v.get("inventory_quantity") or 0) for v in payload.get("variants") or [])
    if available is None:
        available = 0

    inventory_only = "inventory" in (topic or "") and "product" not in (topic or "")
    if inventory_only:
        return _upsert_shopify_inventory_level(
            store_id=store_id,
            sku=sku,
            available=int(available),
            payload=payload,
            topic=topic,
            correlation_id=correlation_id,
            inventory_item_id=item_id,
        )
    return _upsert_shopify_product_catalog(
        store_id=store_id,
        sku=sku,
        payload=payload,
        available=int(available),
        topic=topic,
        correlation_id=correlation_id,
    )


def _upsert_shopify_inventory_level(
    *,
    store_id: str,
    sku: str,
    available: int,
    payload: dict[str, Any],
    topic: str,
    correlation_id: str,
    inventory_item_id: Any,
) -> dict[str, Any]:
    """Update channel qty only. Do not replace products/listings.raw (product webhook owns that)."""
    title = payload.get("title") or payload.get("name") or sku
    listing_id = None
    product_id = None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products (store_id, sku, title, raw, updated_at)
                VALUES (%s, %s, %s, '{}'::jsonb, NOW())
                ON CONFLICT (store_id, sku) DO NOTHING
                """,
                (store_id, sku, title),
            )
            cur.execute(
                "SELECT id FROM products WHERE store_id = %s AND sku = %s",
                (store_id, sku),
            )
            prow = cur.fetchone()
            product_id = str(prow["id"]) if prow else None

            if inventory_item_id and product_id:
                cur.execute(
                    """
                    INSERT INTO listings (
                        store_id, platform, external_id, sku, product_id, raw, updated_at
                    )
                    VALUES (%s, 'shopify', %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (store_id, platform, external_id) DO UPDATE SET
                        sku = EXCLUDED.sku,
                        product_id = COALESCE(EXCLUDED.product_id, listings.product_id),
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        store_id,
                        str(inventory_item_id),
                        sku,
                        product_id,
                        json.dumps({"inventory_item_id": inventory_item_id, "source": "inventory_levels"}),
                    ),
                )
                row = cur.fetchone()
                listing_id = str(row["id"]) if row else None

            cur.execute(
                """
                INSERT INTO inventory_levels (
                    store_id, sku, platform, location_key, available, last_synced_at, raw, updated_at
                )
                VALUES (%s, %s, 'shopify', 'default', %s, NOW(), %s::jsonb, NOW())
                ON CONFLICT (store_id, sku, platform, location_key) DO UPDATE SET
                    available = EXCLUDED.available,
                    last_synced_at = NOW(),
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id, available
                """,
                (store_id, sku, available, json.dumps(payload)),
            )
            inv = cur.fetchone()

    return {
        "primary_id": str(inv["id"]),
        "product_id": product_id,
        "listing_id": listing_id,
        "sku": sku,
        "available": int(inv["available"]),
        "correlation_id": correlation_id,
        "topic": topic,
        "inventory_item_id": inventory_item_id,
    }


def _upsert_shopify_product_catalog(
    *,
    store_id: str,
    sku: str,
    payload: dict[str, Any],
    available: int,
    topic: str,
    correlation_id: str,
) -> dict[str, Any]:
    title = payload.get("title") or payload.get("name") or sku
    external_id = str(payload.get("admin_graphql_api_id") or payload.get("id") or sku)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products (store_id, sku, title, raw, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (store_id, sku) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, products.title),
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id
                """,
                (store_id, sku, title, json.dumps(payload)),
            )
            product_id = str(cur.fetchone()["id"])

            cur.execute(
                """
                INSERT INTO listings (store_id, platform, external_id, sku, product_id, raw, updated_at)
                VALUES (%s, 'shopify', %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (store_id, platform, external_id) DO UPDATE SET
                    sku = EXCLUDED.sku,
                    product_id = EXCLUDED.product_id,
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id
                """,
                (store_id, external_id, sku, product_id, json.dumps(payload)),
            )
            listing_id = str(cur.fetchone()["id"])

            cur.execute(
                """
                INSERT INTO inventory_levels (
                    store_id, sku, platform, location_key, available, last_synced_at, raw, updated_at
                )
                VALUES (%s, %s, 'shopify', 'default', %s, NOW(), %s::jsonb, NOW())
                ON CONFLICT (store_id, sku, platform, location_key) DO UPDATE SET
                    available = EXCLUDED.available,
                    last_synced_at = NOW(),
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id, available
                """,
                (store_id, sku, available, json.dumps(payload)),
            )
            inv = cur.fetchone()

    return {
        "primary_id": str(inv["id"]),
        "product_id": product_id,
        "listing_id": listing_id,
        "sku": sku,
        "available": int(inv["available"]),
        "correlation_id": correlation_id,
        "topic": topic,
    }


def _first_variant_sku(payload: dict[str, Any]) -> str | None:
    variants = payload.get("variants") or []
    if variants and isinstance(variants, list):
        sku = variants[0].get("sku")
        return str(sku) if sku else None
    return None


def _sku_from_shopify_inventory_item(store_id: str, inventory_item_id: Any) -> str | None:
    """Map inventory_levels/update inventory_item_id → SKU via prior product listing raw."""
    if inventory_item_id is None:
        return None
    needle = str(inventory_item_id).strip()
    if not needle:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sku FROM listings
                WHERE store_id = %s AND platform = 'shopify' AND sku IS NOT NULL AND sku <> ''
                  AND sku NOT LIKE 'ext-%%'
                  AND (
                    external_id = %s
                    OR raw->>'inventory_item_id' = %s
                    OR raw->'variant'->>'inventory_item_id' = %s
                    OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(COALESCE(raw->'variants', '[]'::jsonb)) AS v
                      WHERE v->>'inventory_item_id' = %s
                    )
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (store_id, needle, needle, needle, needle),
            )
            row = cur.fetchone()
    sku = (row or {}).get("sku") if row else None
    text = str(sku).strip() if sku else ""
    return None if _is_unresolved_sku(text) else text


def _sku_from_shopify_admin_inventory_item(inventory_item_id: Any) -> str | None:
    """Fallback when listings.raw has not seen this inventory_item_id yet."""
    if inventory_item_id is None:
        return None
    try:
        from channels.shopify_admin import ShopifyAdminClient

        sku = ShopifyAdminClient().get_inventory_item_sku(inventory_item_id)
    except Exception as exc:
        logger.warning("Admin inventory_item SKU lookup failed: %s", exc)
        return None
    text = str(sku).strip() if sku else ""
    return None if _is_unresolved_sku(text) else text


def _upsert_shopify_order(store_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    external_order_id = str(payload.get("id") or payload.get("order_id") or payload.get("name") or _uuid())
    status = str(payload.get("financial_status") or payload.get("status") or "open")
    fulfillment = payload.get("fulfillment_status")
    email = (payload.get("email") or (payload.get("customer") or {}).get("email") or "").lower() or None
    currency = payload.get("currency") or "USD"
    totals = {
        "total_price": payload.get("total_price"),
        "subtotal_price": payload.get("subtotal_price"),
        "total_tax": payload.get("total_tax"),
    }
    line_items = payload.get("line_items") or []

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (
                    store_id, correlation_id, platform, external_order_id, status,
                    fulfillment_status, financial_status, customer_email, currency,
                    totals, line_items, raw, ordered_at, updated_at
                )
                VALUES (
                    %s, %s, 'shopify', %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s, NOW()
                )
                ON CONFLICT (store_id, platform, external_order_id) DO UPDATE SET
                    correlation_id = COALESCE(EXCLUDED.correlation_id, orders.correlation_id),
                    status = EXCLUDED.status,
                    fulfillment_status = EXCLUDED.fulfillment_status,
                    financial_status = EXCLUDED.financial_status,
                    customer_email = COALESCE(EXCLUDED.customer_email, orders.customer_email),
                    totals = EXCLUDED.totals,
                    line_items = EXCLUDED.line_items,
                    raw = EXCLUDED.raw,
                    updated_at = NOW()
                RETURNING id, status, fulfillment_status
                """,
                (
                    store_id,
                    correlation_id,
                    external_order_id,
                    status,
                    fulfillment,
                    payload.get("financial_status"),
                    email,
                    currency,
                    json.dumps(totals),
                    json.dumps(line_items),
                    json.dumps(payload),
                    payload.get("created_at") or _now().isoformat(),
                ),
            )
            order = cur.fetchone()
            order_id = str(order["id"])

            for li in line_items:
                ext_line = str(li.get("id") or li.get("sku") or _uuid())
                cur.execute(
                    """
                    INSERT INTO order_items (
                        order_id, store_id, sku, external_line_id, title, quantity, unit_price, raw
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (order_id, external_line_id) DO UPDATE SET
                        sku = EXCLUDED.sku,
                        title = EXCLUDED.title,
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        raw = EXCLUDED.raw
                    """,
                    (
                        order_id,
                        store_id,
                        li.get("sku"),
                        ext_line,
                        li.get("title") or li.get("name"),
                        int(li.get("quantity") or 1),
                        li.get("price"),
                        json.dumps(li),
                    ),
                )

            if email:
                cur.execute(
                    """
                    INSERT INTO customers (store_id, email, external_id, display_name, raw, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (store_id, email) DO UPDATE SET
                        external_id = COALESCE(EXCLUDED.external_id, customers.external_id),
                        display_name = COALESCE(EXCLUDED.display_name, customers.display_name),
                        updated_at = NOW()
                    """,
                    (
                        store_id,
                        email,
                        str((payload.get("customer") or {}).get("id") or ""),
                        (payload.get("customer") or {}).get("first_name"),
                        json.dumps(payload.get("customer") or {}),
                    ),
                )

    return {
        "primary_id": order_id,
        "external_order_id": external_order_id,
        "status": order["status"],
        "fulfillment_status": order["fulfillment_status"],
        "customer_email": email,
        "correlation_id": correlation_id,
    }


def _upsert_shopify_return_stub(store_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    external_return_id = str(payload.get("id") or payload.get("refund_id") or _uuid())
    amount = float(payload.get("amount") or (payload.get("transactions") or [{}])[0].get("amount") or 0)
    reason = payload.get("note") or payload.get("reason")
    shopify_order_id = _extract_shopify_order_id(payload)
    with connect() as conn:
        with conn.cursor() as cur:
            linked_order_id = None
            if shopify_order_id:
                cur.execute(
                    """
                    SELECT id FROM orders
                    WHERE store_id = %s AND platform = 'shopify' AND external_order_id = %s
                    """,
                    (store_id, shopify_order_id),
                )
                found = cur.fetchone()
                if found:
                    linked_order_id = str(found["id"])

            cur.execute(
                "SELECT id FROM returns WHERE store_id = %s AND external_return_id = %s",
                (store_id, external_return_id),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE returns
                    SET amount = %s, reason = COALESCE(%s, reason), raw = %s::jsonb,
                        order_id = COALESCE(%s, order_id),
                        correlation_id = COALESCE(%s, correlation_id), updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        amount,
                        reason,
                        json.dumps(payload),
                        linked_order_id,
                        correlation_id,
                        existing["id"],
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO returns (
                        store_id, order_id, external_return_id, decision, amount, currency, reason,
                        status, correlation_id, raw, updated_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s, %s, %s, 'open', %s, %s::jsonb, NOW())
                    RETURNING id
                    """,
                    (
                        store_id,
                        linked_order_id,
                        external_return_id,
                        amount,
                        payload.get("currency") or "USD",
                        reason,
                        correlation_id,
                        json.dumps(payload),
                    ),
                )
            row = cur.fetchone()
    return {
        "primary_id": str(row["id"]) if row else None,
        "external_return_id": external_return_id,
        "amount": amount,
        "reason": reason,
        "shopify_order_id": shopify_order_id,
        "correlation_id": correlation_id,
    }


def _recent_inventory_writeback(
    store_id: str,
    *,
    sku: str,
    target: int,
    window_sec: int = 45,
) -> bool:
    """True if we already live-applied this SKU→target recently (duplicate Shopify/Woo webhooks)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT detail FROM audit_logs
                WHERE store_id = %s AND action = 'inventory_sync'
                  AND created_at >= NOW() - (%s || ' seconds')::interval
                ORDER BY created_at DESC
                LIMIT 12
                """,
                (store_id, str(window_sec)),
            )
            rows = list(cur.fetchall() or [])
    for row in rows:
        detail = row.get("detail") if isinstance(row, dict) else None
        if not isinstance(detail, dict):
            continue
        for wb in detail.get("channel_writebacks") or []:
            if not isinstance(wb, dict):
                continue
            if str(wb.get("sku")) != sku:
                continue
            if int(wb.get("target_available") or wb.get("master_available") or -1) != target:
                continue
            if wb.get("live_status") == "ok":
                return True
    return False


def _recent_same_inventory_alert(
    store_id: str,
    drifts: list[dict[str, Any]],
    *,
    window_sec: int = 45,
) -> bool:
    """Suppress Slack if the same SKU/qty drift was already alerted in the window."""
    sig = tuple(
        sorted(
            (str(d.get("sku")), int(d.get("master_available") or 0), d.get("slave_available"))
            for d in drifts
        )
    )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT detail FROM audit_logs
                WHERE store_id = %s AND action = 'inventory_sync'
                  AND created_at >= NOW() - (%s || ' seconds')::interval
                ORDER BY created_at DESC
                LIMIT 12
                """,
                (store_id, str(window_sec)),
            )
            rows = list(cur.fetchall() or [])
    for row in rows:
        detail = row.get("detail") if isinstance(row, dict) else None
        if not isinstance(detail, dict):
            continue
        prev = []
        for wb in detail.get("channel_writebacks") or []:
            if isinstance(wb, dict) and wb.get("sku"):
                prev.append(
                    (str(wb.get("sku")), int(wb.get("master_available") or 0), wb.get("slave_available"))
                )
        if tuple(sorted(prev)) == sig:
            return True
    return False


def inventory_sync(
    *,
    store_id: str | None = None,
    store_key: str | None = None,
    sku: str | None = None,
    correlation_id: str | None = None,
    slave_levels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge multi-channel levels; master wins; test skips writeback."""
    cfg = get_config()
    mode = cfg["mode"]
    master = cfg["master_channel"]
    corr = correlation_id or _uuid()
    slave_channels = [c.strip() for c in _cfg(cfg["flat"], "slave_channels", "woocommerce").split(",") if c.strip()]

    if not store_id:
        key = store_key or _cfg(cfg["flat"], "demo_store_key", "demo-shopify")
        store = ensure_store(store_key=key, platform="shopify")
        store_id = str(store["id"])

    if sku and _is_unresolved_sku(sku):
        write_audit(
            action="inventory_sync_skipped_unresolved_sku",
            store_id=store_id,
            correlation_id=corr,
            detail={"sku": sku},
        )
        return {
            "ok": True,
            "correlation_id": corr,
            "store_id": store_id,
            "mode": mode,
            "master_channel": master,
            "levels": [],
            "drifts": [],
            "has_drift": False,
            "writebacks": [],
            "writeback_status": "skipped_unresolved_sku",
            "channel_writebacks": [],
            "applied_writebacks": [],
            "should_alert_slack": False,
        }

    # Optional: inject observed slave levels before merge (from Merge node / Cron poll).
    if slave_levels:
        with connect() as conn:
            with conn.cursor() as cur:
                for level in slave_levels:
                    cur.execute(
                        """
                        INSERT INTO inventory_levels (
                            store_id, sku, platform, location_key, available, last_synced_at, raw, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, NOW(), %s::jsonb, NOW())
                        ON CONFLICT (store_id, sku, platform, location_key) DO UPDATE SET
                            available = EXCLUDED.available,
                            last_synced_at = NOW(),
                            raw = EXCLUDED.raw,
                            updated_at = NOW()
                        """,
                        (
                            store_id,
                            level["sku"],
                            level.get("platform") or "woocommerce",
                            level.get("location_key") or "default",
                            int(level.get("available") or 0),
                            json.dumps(level.get("raw") or level),
                        ),
                    )

    with connect() as conn:
        with conn.cursor() as cur:
            if sku:
                cur.execute(
                    """
                    SELECT sku, platform, location_key, available, last_synced_at
                    FROM inventory_levels
                    WHERE store_id = %s AND sku = %s
                    ORDER BY sku, platform
                    """,
                    (store_id, sku),
                )
            else:
                cur.execute(
                    """
                    SELECT sku, platform, location_key, available, last_synced_at
                    FROM inventory_levels
                    WHERE store_id = %s
                    ORDER BY sku, platform
                    """,
                    (store_id,),
                )
            rows = [dict(r) for r in cur.fetchall()]

    by_sku: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_sku.setdefault(row["sku"], {})
        bucket[row["platform"]] = row

    drifts: list[dict[str, Any]] = []
    writebacks: list[dict[str, Any]] = []
    applied_writebacks: list[dict[str, Any]] = []

    for sku_key, platforms in by_sku.items():
        if _is_unresolved_sku(sku_key):
            continue
        master_row = platforms.get(master)
        if not master_row:
            continue
        master_qty = int(master_row["available"])
        for channel in slave_channels:
            slave = platforms.get(channel)
            slave_qty = int(slave["available"]) if slave else None
            if slave_qty is None or slave_qty != master_qty:
                if slave_qty is None and not _slave_listing_exists(store_id, channel, sku_key):
                    continue
                drift = {
                    "sku": sku_key,
                    "master_channel": master,
                    "master_available": master_qty,
                    "slave_channel": channel,
                    "slave_available": slave_qty,
                }
                drifts.append(drift)
                writebacks.append(
                    {
                        **drift,
                        "target_available": master_qty,
                        "action": "set_inventory",
                    }
                )

    writeback_status = "none"
    channel_writebacks: list[dict[str, Any]] = []
    if writebacks:
        if mode != "production" or not _truthy(cfg["flat"].get("writeback_enabled", "true")):
            writeback_status = "skipped_test_mode" if mode != "production" else "skipped_disabled"
        else:
            # Live channel writeback when credentials present; then align SoT.
            align_sot = _truthy(cfg["flat"].get("writeback_align_sot", "true"))
            for wb in writebacks:
                if _recent_inventory_writeback(
                    store_id,
                    sku=str(wb["sku"]),
                    target=int(wb["target_available"]),
                    window_sec=45,
                ):
                    channel_writebacks.append({**wb, "live_status": "skipped_duplicate", "sot_aligned": False})
                    continue
                live = _apply_live_inventory_writeback(
                    store_id=store_id,
                    channel=wb["slave_channel"],
                    sku=wb["sku"],
                    target_available=int(wb["target_available"]),
                    correlation_id=corr,
                )
                channel_writebacks.append({**wb, **live})
                sot_ok = False
                if align_sot and live.get("live_status") in {"ok", "skipped_no_credentials", "sot_only"}:
                    sot_ok = _align_inventory_sot(
                        store_id=store_id,
                        sku=wb["sku"],
                        platform=wb["slave_channel"],
                        available=int(wb["target_available"]),
                        correlation_id=corr,
                        live=live,
                    )
                elif live.get("live_status") == "ok":
                    sot_ok = _align_inventory_sot(
                        store_id=store_id,
                        sku=wb["sku"],
                        platform=wb["slave_channel"],
                        available=int(wb["target_available"]),
                        correlation_id=corr,
                        live=live,
                    )
                channel_writebacks[-1]["sot_aligned"] = sot_ok
                if sot_ok or live.get("live_status") == "ok":
                    applied_writebacks.append({**wb, **live, "sot_aligned": sot_ok})

            live_statuses = [c.get("live_status") for c in channel_writebacks]
            okish = {"ok", "skipped_no_credentials", "sot_only", "skipped_duplicate"}
            if live_statuses and all(s == "skipped_duplicate" for s in live_statuses):
                writeback_status = "skipped_duplicate"
            elif any(s == "ok" for s in live_statuses) and all(s in okish for s in live_statuses):
                writeback_status = "applied" if any(s == "ok" for s in live_statuses) else "applied_sot_only"
            elif any(s == "ok" for s in live_statuses):
                writeback_status = "partial"
            elif all(s in {"skipped_no_credentials", "sot_only", "skipped_duplicate"} for s in live_statuses):
                writeback_status = "applied_sot_only"
            else:
                writeback_status = "failed" if any(s == "error" for s in live_statuses) else "applied_sot_only"

    slack_gate = (
        bool(drifts)
        and writeback_status != "skipped_duplicate"
        and cfg["slack_enabled"]
        and _truthy(cfg["flat"].get("inventory_drift_enabled", "true"))
        and (mode == "production" or cfg["slack_in_test"])
        and not _recent_same_inventory_alert(store_id, drifts, window_sec=45)
    )

    write_audit(
        action="inventory_sync",
        store_id=store_id,
        correlation_id=corr,
        detail={
            "mode": mode,
            "drift_count": len(drifts),
            "writeback_status": writeback_status,
            "channel_writebacks": channel_writebacks,
            "sku_filter": sku,
        },
    )

    return {
        "ok": True,
        "correlation_id": corr,
        "store_id": store_id,
        "mode": mode,
        "master_channel": master,
        "levels": rows,
        "drifts": drifts,
        "has_drift": len(drifts) > 0,
        "writebacks": writebacks,
        "writeback_status": writeback_status,
        "channel_writebacks": channel_writebacks,
        "applied_writebacks": applied_writebacks,
        "should_alert_slack": slack_gate,
    }


def _slave_listing_exists(store_id: str, platform: str, sku: str) -> bool:
    """True when the slave channel has a listing for this SKU (writeback can target it)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM listings
                WHERE store_id = %s AND platform = %s AND sku = %s
                LIMIT 1
                """,
                (store_id, platform, sku),
            )
            return cur.fetchone() is not None


def _lookup_listing_raw(store_id: str, platform: str, sku: str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_id, raw FROM listings
                WHERE store_id = %s AND platform = %s AND sku = %s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (store_id, platform, sku),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT available, raw FROM inventory_levels
                    WHERE store_id = %s AND platform = %s AND sku = %s
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (store_id, platform, sku),
                )
                inv = cur.fetchone()
                return {"external_id": None, "raw": dict(inv["raw"] or {}) if inv else {}}
            return {"external_id": row["external_id"], "raw": dict(row["raw"] or {})}


def _align_inventory_sot(
    *,
    store_id: str,
    sku: str,
    platform: str,
    available: int,
    correlation_id: str,
    live: dict[str, Any],
) -> bool:
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO inventory_levels (
                        store_id, sku, platform, location_key, available, last_synced_at, raw, updated_at
                    )
                    VALUES (%s, %s, %s, 'default', %s, NOW(), %s::jsonb, NOW())
                    ON CONFLICT (store_id, sku, platform, location_key) DO UPDATE SET
                        available = EXCLUDED.available,
                        last_synced_at = NOW(),
                        raw = EXCLUDED.raw,
                        updated_at = NOW()
                    """,
                    (
                        store_id,
                        sku,
                        platform,
                        available,
                        json.dumps(
                            {
                                "source": "master_writeback",
                                "correlation_id": correlation_id,
                                "live_status": live.get("live_status"),
                                "live": {k: v for k, v in live.items() if k != "raw"},
                            }
                        ),
                    ),
                )
        return True
    except Exception:
        logger.exception("SoT inventory align failed sku=%s platform=%s", sku, platform)
        return False


def _apply_live_inventory_writeback(
    *,
    store_id: str,
    channel: str,
    sku: str,
    target_available: int,
    correlation_id: str,
) -> dict[str, Any]:
    """Push master qty to a live slave channel API when credentials exist."""
    _ = correlation_id
    channel_l = (channel or "").lower()
    listing = _lookup_listing_raw(store_id, channel_l, sku)

    if channel_l in {"woocommerce", "woo"}:
        from channels.woocommerce import WooCommerceClient

        client = WooCommerceClient()
        if not client.configured:
            return {"live_status": "skipped_no_credentials", "channel": channel_l}
        result = client.set_stock_by_sku(
            sku,
            target_available,
            product_id=listing.get("external_id"),
        )
        result["channel"] = channel_l
        return result

    if channel_l == "shopify":
        from channels.shopify_admin import (
            ShopifyAdminClient,
            extract_shopify_inventory_ids,
        )

        client = ShopifyAdminClient()
        if not client.configured:
            return {"live_status": "skipped_no_credentials", "channel": channel_l}
        ids = extract_shopify_inventory_ids(listing.get("raw") or {})
        item_id = ids.get("inventory_item_id")
        if not item_id:
            return {
                "live_status": "error",
                "channel": channel_l,
                "error": "missing_inventory_item_id_in_listing_raw",
            }
        result = client.set_inventory_available(
            inventory_item_id=item_id,
            available=target_available,
            location_id=ids.get("location_id"),
        )
        result["channel"] = channel_l
        return result

    return {"live_status": "sot_only", "channel": channel_l, "error": "unsupported_channel"}


# Allowed order status transitions
_ORDER_TRANSITIONS = {
    "open": {"paid", "cancelled", "fulfilled", "partially_fulfilled", "on_hold"},
    "paid": {"fulfilled", "partially_fulfilled", "refunded", "cancelled"},
    "partially_fulfilled": {"fulfilled", "refunded"},
    "fulfilled": {"refunded"},
    "on_hold": {"open", "cancelled", "paid"},
    "cancelled": set(),
    "refunded": set(),
}


def track_order(
    *,
    store_id: str,
    external_order_id: str | None = None,
    order_id: str | None = None,
    new_status: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Load order, optionally transition status, flag anomalies."""
    cfg = get_config()
    mode = cfg["mode"]
    corr = correlation_id or _uuid()

    with connect() as conn:
        with conn.cursor() as cur:
            if order_id:
                cur.execute("SELECT * FROM orders WHERE id = %s AND store_id = %s", (order_id, store_id))
            elif external_order_id:
                cur.execute(
                    """
                    SELECT * FROM orders
                    WHERE store_id = %s AND platform = 'shopify' AND external_order_id = %s
                    """,
                    (store_id, external_order_id),
                )
            else:
                return {"ok": False, "error": "order_id_or_external_order_id_required"}
            order = cur.fetchone()
            if not order:
                return {"ok": False, "error": "order_not_found"}

            previous = order["status"]
            transition_ok = True
            anomaly_reasons: list[str] = []

            if new_status and new_status != previous:
                allowed = _ORDER_TRANSITIONS.get(previous, set())
                # Allow unknown/empty previous → any status.
                if new_status not in allowed and previous not in {"unknown", ""}:
                    transition_ok = False
                    anomaly_reasons.append(f"illegal_transition:{previous}->{new_status}")
                else:
                    cur.execute(
                        """
                        UPDATE orders
                        SET status = %s, correlation_id = COALESCE(%s, correlation_id), updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (new_status, corr, order["id"]),
                    )
                    order = cur.fetchone()

            totals = order["totals"] if isinstance(order["totals"], dict) else {}
            try:
                total_price = float(totals.get("total_price") or 0)
            except (TypeError, ValueError):
                total_price = 0.0
            if total_price < 0:
                anomaly_reasons.append("negative_total")
            if not order.get("customer_email") and order.get("status") in {"paid", "fulfilled"}:
                anomaly_reasons.append("missing_email_on_paid")
            if order.get("fulfillment_status") == "fulfilled" and order.get("status") == "cancelled":
                anomaly_reasons.append("fulfilled_but_cancelled")

            is_anomaly = len(anomaly_reasons) > 0 or not transition_ok
            slack_gate = (
                is_anomaly
                and cfg["slack_enabled"]
                and _truthy(cfg["flat"].get("order_anomaly_enabled", "true"))
                and (mode == "production" or cfg["slack_in_test"])
            )

            write_audit(
                action="order_tracked",
                store_id=store_id,
                correlation_id=corr,
                entity_type="order",
                entity_id=str(order["id"]),
                detail={
                    "previous_status": previous,
                    "status": order["status"],
                    "anomaly_reasons": anomaly_reasons,
                    "transition_ok": transition_ok,
                },
            )

            return {
                "ok": True,
                "correlation_id": corr,
                "store_id": store_id,
                "mode": mode,
                "order_id": str(order["id"]),
                "external_order_id": order["external_order_id"],
                "previous_status": previous,
                "status": order["status"],
                "fulfillment_status": order.get("fulfillment_status"),
                "customer_email": order.get("customer_email"),
                "transition_ok": transition_ok,
                "is_anomaly": is_anomaly,
                "anomaly_reasons": anomaly_reasons,
                "should_alert_slack": slack_gate,
            }


_SHOPIFY_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


def _shop_handle_from_domain(shop_domain: str | None) -> str:
    """Extract Admin store handle. Ignore Woo/http URLs that are not *.myshopify.com."""
    if not shop_domain:
        return ""
    raw = str(shop_domain).strip()
    if not raw:
        return ""
    from_url = "://" in raw or raw.lower().startswith("http")
    if from_url:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or "").lower()
    else:
        host = raw.lower().split("/")[0].split("?")[0]
    if host.endswith(".myshopify.com"):
        handle = host[: -len(".myshopify.com")]
        return handle if _SHOPIFY_HANDLE_RE.match(handle) else ""
    # Bare handle only (nans-automation-store). HTTP(S) Woo URLs never qualify.
    if not from_url and "." not in host and _SHOPIFY_HANDLE_RE.match(host):
        return host
    return ""


def shopify_admin_order_url(
    *,
    shop_domain: str | None,
    shopify_order_id: str | None,
    store_key: str | None = None,
) -> str | None:
    """Build Shopify Admin order URL from shop handle + order id."""
    handle = (
        _shop_handle_from_domain(shop_domain)
        or _shop_handle_from_domain(os.getenv("SHOPIFY_SHOP_DOMAIN"))
        or _shop_handle_from_domain(os.getenv("SHOPIFY_STORE_HANDLE"))
        or _shop_handle_from_domain(store_key)
    )
    oid = str(shopify_order_id or "").strip()
    if not handle:
        return None
    if oid:
        return f"https://admin.shopify.com/store/{handle}/orders/{oid}"
    return f"https://admin.shopify.com/store/{handle}/orders"


def _extract_shopify_order_id(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in ("order_id", "order_number", "orderId"):
        val = raw.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    order = raw.get("order")
    if isinstance(order, dict) and order.get("id") is not None:
        return str(order["id"]).strip()
    return None


def _returns_review_reason(decision: str, amt: float, days: int, max_amount: float, max_days: int) -> str:
    if decision == "manual_review":
        if amt > max_amount:
            return f"amount {amt} exceeds owner-review threshold {max_amount}"
        return "flagged for owner review"
    if decision == "reject":
        if amt <= 0:
            return "non-positive amount"
        if days > max_days:
            return f"days_since_order {days} exceeds max {max_days}"
        return "rejected by rules"
    return "within auto-approve policy"


def decide_return(
    *,
    store_id: str,
    external_return_id: str | None = None,
    return_id: str | None = None,
    amount: float | None = None,
    days_since_order: int | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, Any]:
    """Apply amount/time rules → auto_approve | manual_review | reject."""
    cfg = get_config()
    mode = cfg["mode"]
    corr = correlation_id or _uuid()
    max_amount = float(_cfg(cfg["flat"], "returns_max_auto_approve_amount", "50"))
    max_days = int(_cfg(cfg["flat"], "returns_max_days", "30"))

    shop_domain: str | None = None
    store_key_row: str | None = None
    shopify_order_id: str | None = None

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT external_shop_id, store_key FROM stores WHERE id = %s",
                (store_id,),
            )
            store_row = cur.fetchone()
            if store_row:
                shop_domain = store_row.get("external_shop_id")
                store_key_row = store_row.get("store_key")

            row = None
            if return_id:
                cur.execute("SELECT * FROM returns WHERE id = %s AND store_id = %s", (return_id, store_id))
                row = cur.fetchone()
            elif external_return_id:
                cur.execute(
                    "SELECT * FROM returns WHERE store_id = %s AND external_return_id = %s",
                    (store_id, external_return_id),
                )
                row = cur.fetchone()

            amt = float(amount if amount is not None else (row["amount"] if row else 0) or 0)
            days = int(days_since_order if days_since_order is not None else 0)
            why = reason or (row["reason"] if row else None) or ""

            raw = row["raw"] if row and isinstance(row.get("raw"), dict) else (row["raw"] if row else {}) or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            shopify_order_id = _extract_shopify_order_id(raw) if isinstance(raw, dict) else None

            # Ignore bogus order_id (e.g. parent mapped return primary_id into order_id).
            resolved_order_id = None
            if order_id:
                cur.execute(
                    "SELECT id, external_order_id FROM orders WHERE id = %s AND store_id = %s",
                    (order_id, store_id),
                )
                ord_row = cur.fetchone()
                if ord_row:
                    resolved_order_id = order_id
                    shopify_order_id = shopify_order_id or (
                        str(ord_row["external_order_id"]) if ord_row.get("external_order_id") else None
                    )
            # Link via Shopify order id from refund payload when internal FK missing.
            if not resolved_order_id and shopify_order_id:
                cur.execute(
                    """
                    SELECT id FROM orders
                    WHERE store_id = %s AND platform = 'shopify' AND external_order_id = %s
                    """,
                    (store_id, shopify_order_id),
                )
                found = cur.fetchone()
                if found:
                    resolved_order_id = str(found["id"])
            order_id = resolved_order_id

            if amt <= 0:
                decision = "reject"
            elif days > max_days:
                decision = "reject"
            elif amt <= max_amount and days <= max_days:
                decision = "auto_approve"
            else:
                decision = "manual_review"

            status = {
                "auto_approve": "approved",
                "reject": "rejected",
                "manual_review": "pending_review",
            }[decision]

            if row:
                cur.execute(
                    """
                    UPDATE returns
                    SET decision = %s, status = %s, amount = %s, reason = COALESCE(%s, reason),
                        order_id = COALESCE(%s, order_id), correlation_id = COALESCE(%s, correlation_id),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (decision, status, amt, why or None, order_id, corr, row["id"]),
                )
                row = cur.fetchone()
            else:
                ext = external_return_id or f"ret-{_uuid()[:8]}"
                cur.execute(
                    """
                    INSERT INTO returns (
                        store_id, order_id, external_return_id, decision, amount, reason,
                        status, correlation_id, raw, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, NOW())
                    RETURNING *
                    """,
                    (store_id, order_id, ext, decision, amt, why, status, corr),
                )
                row = cur.fetchone()

    needs_review = decision == "manual_review"
    slack_gate = (
        needs_review
        and cfg["slack_enabled"]
        and _truthy(cfg["flat"].get("returns_review_enabled", "true"))
        and (mode == "production" or cfg["slack_in_test"])
    )
    review_reason = _returns_review_reason(decision, amt, days, max_amount, max_days)
    admin_url = shopify_admin_order_url(
        shop_domain=shop_domain,
        shopify_order_id=shopify_order_id,
        store_key=store_key_row,
    )

    write_audit(
        action="return_decided",
        store_id=store_id,
        correlation_id=corr,
        entity_type="return",
        entity_id=str(row["id"]),
        detail={
            "decision": decision,
            "amount": amt,
            "days_since_order": days,
            "mode": mode,
            "review_reason": review_reason,
            "shopify_admin_url": admin_url,
        },
    )

    return {
        "ok": True,
        "correlation_id": corr,
        "store_id": store_id,
        "mode": mode,
        "return_id": str(row["id"]),
        "external_return_id": row.get("external_return_id"),
        "decision": decision,
        "status": row["status"],
        "amount": amt,
        "days_since_order": days,
        "reason": why or row.get("reason"),
        "review_reason": review_reason,
        "shop_domain": shop_domain,
        "shopify_order_id": shopify_order_id,
        "shopify_admin_url": admin_url,
        "merchant_action": "review_in_shopify",
        "needs_manual_review": needs_review,
        "should_alert_slack": slack_gate,
        # test: PG only; production: pending_provider (no Slack approve/reject)
        "external_refund_status": "skipped_test_mode" if mode != "production" else "pending_provider",
    }
