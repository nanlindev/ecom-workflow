"""P3 domain: ops daily/weekly summaries + deep health for keepalive."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from db import connect, ping_db
from domain_p1 import _cfg, _truthy, _uuid, ensure_store, get_config, write_audit

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ops_summary(
    *,
    period: str = "daily",
    store_id: str | None = None,
    store_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate orders / drifts / errors / pricing for Slack digests."""
    cfg = get_config()
    corr = correlation_id or _uuid()
    period_l = (period or "daily").lower()
    if period_l not in {"daily", "weekly"}:
        return {"ok": False, "error": "period_must_be_daily_or_weekly"}

    key = (store_key or "").strip() or _cfg(cfg["flat"], "demo_store_key", "demo-shopify")
    sid = (store_id or "").strip() or None
    if sid:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id::text AS id FROM stores WHERE id = %s::uuid", (sid,))
                row = cur.fetchone()
        if not row:
            # Stale ECOM_DEMO_STORE_ID (e.g. copied from another env) — fall back to store_key.
            logger.warning("ops_summary: store_id %s not found; resolving via store_key=%s", sid, key)
            sid = None
    if not sid:
        store = ensure_store(store_key=key, platform="shopify")
        sid = str(store["id"])
    store_id = sid

    now = _now()
    window_hours = 24 if period_l == "daily" else 24 * 7
    since = now - timedelta(hours=window_hours)

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM orders
                    WHERE store_id = %s::uuid AND created_at >= %s
                    """,
                    (store_id, since),
                )
                orders_count = int(cur.fetchone()["c"])

                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM returns
                    WHERE store_id = %s::uuid AND created_at >= %s
                    """,
                    (store_id, since),
                )
                returns_count = int(cur.fetchone()["c"])

                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM pricing_recommendations
                    WHERE store_id = %s::uuid AND created_at >= %s
                    """,
                    (store_id, since),
                )
                pricing_count = int(cur.fetchone()["c"])

                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM error_logs
                    WHERE created_at >= %s
                      AND (store_id IS NULL OR store_id = %s::uuid)
                    """,
                    (since, store_id),
                )
                errors_count = int(cur.fetchone()["c"])

                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM audit_logs
                    WHERE created_at >= %s
                      AND action = 'inventory_sync'
                      AND (store_id IS NULL OR store_id = %s::uuid)
                      AND COALESCE(
                        CASE
                          WHEN (detail->>'drift_count') ~ '^[0-9]+$'
                          THEN (detail->>'drift_count')::int
                          ELSE 0
                        END,
                        0
                      ) > 0
                    """,
                    (since, store_id),
                )
                drift_events = int(cur.fetchone()["c"])

                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM campaign_enrollments e
                    JOIN campaigns c ON c.id = e.campaign_id
                    WHERE c.store_id = %s::uuid AND e.created_at >= %s
                    """,
                    (store_id, since),
                )
                enrollments = int(cur.fetchone()["c"])
    except Exception as exc:
        logger.exception("ops_summary query failed store_id=%s", store_id)
        return {
            "ok": False,
            "error": "ops_summary_query_failed",
            "error_message": str(exc)[:500],
            "correlation_id": corr,
            "store_id": store_id,
            "period": period_l,
            "should_alert_slack": False,
        }

    flag_key = "daily_summary_enabled" if period_l == "daily" else "weekly_summary_enabled"
    gate = (
        cfg["mode"] == "production"
        and cfg["slack_enabled"]
        and _truthy(cfg["flat"].get(flag_key, "true"))
    )

    summary = {
        "ok": True,
        "correlation_id": corr,
        "period": period_l,
        "store_id": store_id,
        "mode": cfg["mode"],
        "window_hours": window_hours,
        "since": since.isoformat(),
        "orders_count": orders_count,
        "returns_count": returns_count,
        "pricing_recommendations": pricing_count,
        "inventory_drift_events": drift_events,
        "error_logs": errors_count,
        "marketing_enrollments": enrollments,
        "should_alert_slack": gate,
        "slack_text": "\n".join(
            [
                f"{'📊' if period_l == 'daily' else '📈'} Ecom {period_l.title()} Summary",
                f"Store: {store_id}",
                f"Window: last {window_hours}h",
                f"Orders: {orders_count}",
                f"Returns: {returns_count}",
                f"Pricing recs: {pricing_count}",
                f"Inventory drift events: {drift_events}",
                f"Marketing enrollments: {enrollments}",
                f"Errors: {errors_count}",
                f"Correlation: {corr}",
            ]
        ),
    }

    try:
        write_audit(
            action=f"{period_l}_summary",
            store_id=store_id,
            correlation_id=corr,
            detail={k: summary[k] for k in ("orders_count", "returns_count", "error_logs", "should_alert_slack")},
        )
    except Exception:
        logger.exception("ops_summary audit write failed store_id=%s", store_id)

    return summary


def _channel_fail_reason(channel_pings: dict[str, Any], channel_failures: list[str]) -> str:
    parts: list[str] = []
    for name in channel_failures:
        result = channel_pings.get(name) or {}
        reason = result.get("reason") or result.get("error") or result.get("body") or ""
        status = result.get("status_code")
        bit = f"{name}"
        if status:
            bit += f" HTTP {status}"
        if reason:
            bit += f" {reason}"
        parts.append(bit.strip())
    return "; ".join(parts)[:300]


def _recent_keepalive_alert(channel_failures: list[str], *, window_sec: int = 3600) -> bool:
    """True if the same channel_failures already failed keepalive in the window (Slack debounce)."""
    sig = tuple(sorted(channel_failures))
    if not sig:
        return False
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT detail FROM audit_logs
                WHERE action = 'keepalive_check'
                  AND created_at >= NOW() - (%s || ' seconds')::interval
                ORDER BY created_at DESC
                LIMIT 8
                """,
                (str(window_sec),),
            )
            rows = list(cur.fetchall() or [])
    for row in rows:
        detail = row.get("detail") if isinstance(row, dict) else None
        if not isinstance(detail, dict):
            continue
        if detail.get("ok") is True:
            continue
        prev = tuple(sorted(str(x) for x in (detail.get("channel_failures") or [])))
        if prev == sig:
            return True
    return False


def keepalive_check(*, correlation_id: str | None = None, ping_channels: bool = True) -> dict[str, Any]:
    """Sidecar + PG health; optional light Woo/Shopify Admin pings when configured."""
    cfg = get_config()
    corr = correlation_id or _uuid()
    db_ok = False
    db_error = None
    try:
        db_ok = ping_db()
    except Exception as exc:
        db_error = str(exc)[:200]

    channel_pings: dict[str, Any] = {}
    if ping_channels:
        try:
            from channels.woocommerce import WooCommerceClient, woo_configured

            if woo_configured():
                channel_pings["woocommerce"] = WooCommerceClient().ping()
            else:
                channel_pings["woocommerce"] = {"ok": False, "reason": "not_configured"}
        except Exception as exc:
            channel_pings["woocommerce"] = {"ok": False, "reason": str(exc)[:200]}
        try:
            from channels.shopify_admin import ShopifyAdminClient, shopify_admin_configured

            if shopify_admin_configured():
                channel_pings["shopify_admin"] = ShopifyAdminClient().ping()
            else:
                channel_pings["shopify_admin"] = {"ok": False, "reason": "not_configured"}
        except Exception as exc:
            channel_pings["shopify_admin"] = {"ok": False, "reason": str(exc)[:200]}

    healthy = db_ok
    # Channel not_configured is not a failure; only configured+failing fails keepalive.
    channel_failures = [
        name
        for name, result in channel_pings.items()
        if result.get("reason") != "not_configured" and not result.get("ok")
    ]
    if channel_failures:
        healthy = False

    fail_reason = _channel_fail_reason(channel_pings, channel_failures)
    fail_lines = [
        "🚨 Ecom Health Keepalive FAILED",
        f"Database: {'ok' if db_ok else 'error'}",
        f"Channel failures: {', '.join(channel_failures) or 'none'}",
    ]
    if fail_reason:
        fail_lines.append(f"Detail: {fail_reason}")
    fail_lines.append(f"Correlation: {corr}")
    alert = (
        (not healthy)
        and cfg["mode"] == "production"
        and cfg["slack_enabled"]
        and _truthy(cfg["flat"].get("keepalive_alert_enabled", "true"))
        and not _recent_keepalive_alert(channel_failures, window_sec=3600)
    )

    body = {
        "ok": healthy,
        "correlation_id": corr,
        "mode": cfg["mode"],
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
        "channel_pings": channel_pings,
        "channel_failures": channel_failures,
        "should_alert_slack": alert,
        "slack_text": (
            "\n".join(fail_lines)
            if not healthy
            else f"✅ Ecom Health Keepalive OK (db={'ok' if db_ok else 'error'}) corr={corr}"
        ),
    }
    write_audit(action="keepalive_check", correlation_id=corr, detail={"ok": healthy, "channel_failures": channel_failures})
    return body
