"""P2 domain: competitor parse, pricing recommend/action, RFM/churn insights, marketing copy/enroll/advance."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from db import connect
from domain_p1 import _cfg, _lookup_listing_raw, _truthy, _uuid, get_config, write_audit
from llm import complete_json
from prompt_loader import load_prompt


def _extract_commerce_image_url(raw: Any) -> str | None:
    """Best-effort product thumbnail from Shopify / Woo listing or product raw JSON."""
    if not isinstance(raw, dict):
        return None
    images = raw.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            for key in ("src", "url", "src_large", "thumbnail"):
                u = first.get(key)
                if isinstance(u, str) and u.startswith("http"):
                    return u
        elif isinstance(first, str) and first.startswith("http"):
            return first
    image = raw.get("image")
    if isinstance(image, dict):
        for key in ("src", "url"):
            u = image.get(key)
            if isinstance(u, str) and u.startswith("http"):
                return u
    if isinstance(image, str) and image.startswith("http"):
        return image
    for key in ("featured_src", "thumbnail", "image_url"):
        u = raw.get(key)
        if isinstance(u, str) and u.startswith("http"):
            return u
    variants = raw.get("variants")
    if isinstance(variants, list) and variants:
        v0 = variants[0]
        if isinstance(v0, dict):
            img = v0.get("image") or v0.get("featured_image")
            if isinstance(img, dict):
                u = img.get("src") or img.get("url")
                if isinstance(u, str) and u.startswith("http"):
                    return u
            if isinstance(img, str) and img.startswith("http"):
                return img
    return None


def _extract_commerce_price(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    for key in ("price", "regular_price"):
        try:
            if raw.get(key) is not None and str(raw.get(key)).strip() != "":
                return float(raw[key])
        except (TypeError, ValueError):
            pass
    variants = raw.get("variants")
    if isinstance(variants, list) and variants:
        v0 = variants[0]
        if isinstance(v0, dict):
            try:
                if v0.get("price") is not None:
                    return float(v0["price"])
            except (TypeError, ValueError):
                pass
    return None


def _product_display_meta(store_id: str, sku: str) -> dict[str, Any]:
    """Title + public image URL for Slack (prefer Shopify listing, then Woo, then product)."""
    title = sku
    image_url: str | None = None
    product_raw: dict[str, Any] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, raw FROM products WHERE store_id = %s AND sku = %s",
                (store_id, sku),
            )
            prod = cur.fetchone()
            if prod:
                if prod.get("title"):
                    title = str(prod["title"])
                if isinstance(prod.get("raw"), dict):
                    product_raw = prod["raw"]
            cur.execute(
                """
                SELECT platform, raw FROM listings
                WHERE store_id = %s AND sku = %s
                ORDER BY CASE platform
                    WHEN 'shopify' THEN 0
                    WHEN 'woocommerce' THEN 1
                    ELSE 2
                END
                """,
                (store_id, sku),
            )
            for row in cur.fetchall() or []:
                raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
                if not image_url:
                    image_url = _extract_commerce_image_url(raw)
                if title == sku and raw.get("title"):
                    title = str(raw["title"])
                elif title == sku and raw.get("name"):
                    title = str(raw["name"])
    if not image_url:
        image_url = _extract_commerce_image_url(product_raw)
    if title == sku and product_raw.get("title"):
        title = str(product_raw["title"])
    elif title == sku and product_raw.get("name"):
        title = str(product_raw["name"])
    return {"title": title, "image_url": image_url, "product_raw": product_raw}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_live_price_writeback(
    *,
    store_id: str,
    sku: str,
    price: float,
    currency: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Push approved price to Shopify Admin and/or Woo when credentials exist."""
    _ = correlation_id
    results: list[dict[str, Any]] = []
    cfg = get_config()
    targets = [
        c.strip()
        for c in _cfg(cfg["flat"], "price_writeback_channels", "shopify,woocommerce").split(",")
        if c.strip()
    ]
    if not targets:
        targets = [cfg["master_channel"]]

    for channel in targets:
        ch = channel.lower()
        listing = _lookup_listing_raw(store_id, ch, sku)
        if ch == "shopify":
            from channels.shopify_admin import (
                ShopifyAdminClient,
                extract_shopify_variant_id,
            )

            client = ShopifyAdminClient()
            if not client.configured:
                results.append({"channel": ch, "live_status": "skipped_no_credentials"})
                continue
            variant_id = extract_shopify_variant_id(listing.get("raw") or {}, sku=sku)
            if not variant_id and listing.get("external_id"):
                # Prefer Admin search by SKU when listing maps product id only
                variant_id = client.find_variant_id_by_sku(sku)
            if not variant_id:
                variant_id = client.find_variant_id_by_sku(sku)
            if not variant_id:
                results.append(
                    {
                        "channel": ch,
                        "live_status": "error",
                        "error": "missing_variant_id",
                    }
                )
                continue
            r = client.set_variant_price(variant_id=variant_id, price=price)
            r["channel"] = ch
            results.append(r)
        elif ch in {"woocommerce", "woo"}:
            from channels.woocommerce import WooCommerceClient

            client = WooCommerceClient()
            if not client.configured:
                results.append({"channel": ch, "live_status": "skipped_no_credentials"})
                continue
            r = client.set_price_by_sku(
                sku,
                price,
                product_id=listing.get("external_id"),
                currency=currency,
            )
            r["channel"] = ch
            results.append(r)
        else:
            results.append({"channel": ch, "live_status": "sot_only", "error": "unsupported_channel"})
    return results


def _parse_structured_competitor_price(raw: str, sku: str | None) -> float | None:
    """SKU-bound price only (data-competitor-* or SKU…Price block). No 'first $ on page' fallback."""
    if not sku or not raw:
        return None
    esc = re.escape(sku.strip())
    text = raw
    for pat in (
        rf'data-competitor-sku=["\']{esc}["\'][^>]*?data-competitor-price=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        rf'data-competitor-price=["\']([0-9]+(?:\.[0-9]+)?)["\'][^>]*?data-competitor-sku=["\']{esc}["\']',
        rf'SKU:\s*{esc}\s*.{{0,500}}?Price:\s*\$?\s*([0-9]+(?:\.[0-9]{{1,2}})?)',
    ):
        m = re.search(pat, text, re.I | re.S)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def _parse_price_from_text(raw: str, sku: str | None = None) -> float | None:
    """Extract a price; with sku, only return SKU-scoped structured price (avoid multi-card bleed)."""
    structured = _parse_structured_competitor_price(raw, sku)
    if structured is not None:
        return structured
    if sku:
        # With sku set, refuse unscoped first-$ fallback (multi-card bleed).
        return None
    text = raw or ""
    m = re.search(r"(?:USD|\$|€|£)\s*([0-9]+(?:\.[0-9]{1,2})?)", text, re.I)
    if not m:
        m = re.search(r"\b([0-9]+\.[0-9]{2})\b", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_competitor(
    *,
    store_id: str,
    url: str,
    raw_content: str,
    sku: str | None = None,
    source_name: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """LLM (or regex fallback) extract price → insert price_snapshots."""
    corr = correlation_id or _uuid()
    truncated = (raw_content or "")[:8000]
    structured = _parse_structured_competitor_price(truncated, sku)
    if structured is not None:
        parsed = {
            "price": structured,
            "currency": "USD",
            "title": None,
            "in_stock": None,
            "fallback_used": False,
            "parse_source": "structured_sku",
        }
        fb = False
        price_f = structured
    else:
        prompt = load_prompt("competitor_parse")
        user = prompt.render(url=url or "", raw_content=truncated, sku=sku or "")

        def _fallback() -> dict[str, Any]:
            price = _parse_price_from_text(truncated, sku=sku)
            return {
                "price": price,
                "currency": "USD",
                "title": None,
                "in_stock": None,
                "fallback_used": True,
            }

        parsed, fb = complete_json(
            system="Extract competitor product price as JSON only. If multiple products, use only the Target SKU.",
            user=user,
            model=prompt.model,
            fallback=_fallback,
        )
        price = parsed.get("price")
        try:
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_f = _parse_price_from_text(truncated, sku=sku)
        # Prefer structured SKU match when LLM returns a different price.
        again = _parse_structured_competitor_price(raw_content or "", sku)
        if again is not None:
            price_f = again
            parsed = {**parsed, "price": again, "parse_source": "structured_sku_override"}
            fb = False

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO price_snapshots (
                    store_id, sku, source_type, source_name, url, price, currency, raw, captured_at
                )
                VALUES (%s, %s, 'competitor', %s, %s, %s, %s, %s::jsonb, NOW())
                RETURNING id, captured_at
                """,
                (
                    store_id,
                    sku,
                    source_name or "competitor",
                    url,
                    price_f,
                    parsed.get("currency") or "USD",
                    json.dumps({"parse": parsed, "correlation_id": corr}),
                ),
            )
            row = cur.fetchone()

    write_audit(
        action="competitor_parsed",
        store_id=store_id,
        correlation_id=corr,
        entity_type="price_snapshot",
        entity_id=str(row["id"]) if row else None,
        detail={"url": url, "price": price_f, "fallback_used": fb or parsed.get("fallback_used"), "sku": sku},
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "snapshot_id": str(row["id"]) if row else None,
        "sku": sku,
        "price": price_f,
        "currency": parsed.get("currency") or "USD",
        "title": parsed.get("title"),
        "fallback_used": bool(fb or parsed.get("fallback_used")),
        "captured_at": row["captured_at"].isoformat() if row and row.get("captured_at") else None,
        "parse_source": parsed.get("parse_source") or ("llm" if not fb else "regex_fallback"),
    }


def recommend_price(
    *,
    store_id: str,
    sku: str,
    current_price: float | None = None,
    cost: float | None = None,
    correlation_id: str | None = None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build pricing recommendation; Slack alert left to n8n."""
    cfg = get_config()
    try:
        corr = str(uuid.UUID(str(correlation_id))) if correlation_id else _uuid()
    except (ValueError, TypeError, AttributeError):
        corr = _uuid()
    flat = cfg["flat"]
    min_margin = float(_cfg(flat, "min_margin_pct", "15"))
    strategy = strategy or {"name": "match_undercut", "undercut_pct": 2}

    display = _product_display_meta(store_id, sku)
    title = display["title"]
    image_url = display["image_url"]
    product_raw = display.get("product_raw") or {}

    with connect() as conn:
        with conn.cursor() as cur:
            if cost is None or current_price is None:
                cur.execute(
                    "SELECT cost, raw FROM products WHERE store_id = %s AND sku = %s",
                    (store_id, sku),
                )
                prod = cur.fetchone()
                if prod:
                    if cost is None and prod.get("cost") is not None:
                        cost = float(prod["cost"])
                    if current_price is None:
                        raw = prod.get("raw") if isinstance(prod.get("raw"), dict) else product_raw
                        extracted = _extract_commerce_price(raw)
                        if extracted is not None:
                            current_price = extracted
                if current_price is None:
                    for platform in ("shopify", "woocommerce"):
                        listing = _lookup_listing_raw(store_id, platform, sku)
                        extracted = _extract_commerce_price(listing.get("raw") or {})
                        if extracted is not None:
                            current_price = extracted
                            break
            cur.execute(
                """
                SELECT price, source_name, url, captured_at
                FROM price_snapshots
                WHERE store_id = %s AND sku = %s
                  AND source_type = 'competitor' AND price IS NOT NULL
                ORDER BY captured_at DESC
                LIMIT 20
                """,
                (store_id, sku),
            )
            snaps = list(cur.fetchall() or [])

    if current_price is None:
        current_price = 89.0
    if cost is None:
        cost = round(current_price * 0.4, 2)

    # Newest quote per (source, url) — ignore stale wrong parses of the same competitor page.
    competitor_prices: list[dict[str, Any]] = []
    seen_sources: set[tuple[Any, Any]] = set()
    for s in snaps:
        if s.get("price") is None:
            continue
        key = (s.get("source_name"), s.get("url"))
        if key in seen_sources:
            continue
        seen_sources.add(key)
        competitor_prices.append(
            {"price": float(s["price"]), "source": s.get("source_name"), "url": s.get("url")}
        )
    prompt = load_prompt("pricing_recommend")
    user = prompt.render(
        min_margin_pct=str(min_margin),
        currency="USD",
        sku=sku,
        current_price=str(current_price),
        cost=str(cost),
        competitor_prices_json=json.dumps(competitor_prices),
        strategy_json=json.dumps(strategy),
    )

    floor = round(cost * (1 + min_margin / 100.0), 2)
    undercut_pct = float(strategy.get("undercut_pct") or 2)
    hold_band_pct = float(strategy.get("hold_band_pct") or 2)
    allow_raise = _truthy(str(strategy.get("allow_raise_toward_competitor", "false")))

    def _fallback() -> dict[str, Any]:
        if not competitor_prices:
            return {
                "recommended_price": current_price,
                "reasoning": "No competitor data; hold current price",
                "strategy": "hold_no_competitor",
                "action": "hold",
                "fallback_used": True,
            }
        comp = min(float(c["price"]) for c in competitor_prices)
        band = abs(current_price) * (hold_band_pct / 100.0) if current_price else 0.0
        delta = comp - float(current_price)

        if abs(delta) <= band:
            return {
                "recommended_price": float(current_price),
                "reasoning": f"Competitor {comp} within {hold_band_pct}% of current {current_price}; hold",
                "strategy": "hold_near_competitor",
                "action": "hold",
                "fallback_used": True,
            }
        if delta < 0:
            rec = max(floor, round(comp * (1 - undercut_pct / 100.0), 2))
            return {
                "recommended_price": rec,
                "reasoning": (
                    f"Competitor {comp} below current {current_price}; "
                    f"undercut by {undercut_pct}% → {rec} (floor {floor})"
                ),
                "strategy": strategy.get("name") or "match_undercut",
                "action": "lower",
                "fallback_used": True,
            }
        if allow_raise:
            target = round(comp * (1 - undercut_pct / 100.0), 2)
            if target > float(current_price):
                rec = max(floor, min(target, float(comp) - 0.01))
                return {
                    "recommended_price": rec,
                    "reasoning": (
                        f"Competitor {comp} above current; allow_raise_toward_competitor "
                        f"→ move toward undercut target {target}"
                    ),
                    "strategy": "raise_toward_competitor",
                    "action": "raise",
                    "fallback_used": True,
                }
        return {
            "recommended_price": float(current_price),
            "reasoning": (
                f"Competitor {comp} above current {current_price}; "
                f"already competitive — hold (do not raise to undercut a higher list)"
            ),
            "strategy": "hold_already_competitive",
            "action": "hold",
            "fallback_used": True,
        }

    parsed, fb = complete_json(
        system="Return pricing recommendation JSON only. Follow hold-vs-undercut rules in the user prompt.",
        user=user,
        model=prompt.model,
        fallback=_fallback,
    )
    try:
        rec_price = float(parsed.get("recommended_price"))
    except (TypeError, ValueError):
        fb_out = _fallback()
        rec_price = float(fb_out["recommended_price"])
        parsed = {**parsed, **fb_out}
        fb = True
    rec_price = max(floor, rec_price)

    # Guard: block raise when competitor > current and allow_raise is false.
    if competitor_prices and not allow_raise:
        comp = min(float(c["price"]) for c in competitor_prices)
        if comp > float(current_price) and rec_price > float(current_price):
            rec_price = float(current_price)
            parsed = {
                **parsed,
                "recommended_price": rec_price,
                "action": "hold",
                "strategy": "hold_already_competitive",
                "reasoning": (
                    (parsed.get("reasoning") or "")
                    + " | Guard: blocked raise while competitor is higher than current."
                ).strip(" |"),
            }

    action_l = str(parsed.get("action") or "").lower()
    if action_l not in {"lower", "hold", "raise"}:
        if abs(float(rec_price) - float(current_price)) < 0.005:
            action_l = "hold"
        elif float(rec_price) < float(current_price):
            action_l = "lower"
        else:
            action_l = "raise"
    parsed["action"] = action_l
    rec_status = "held" if action_l == "hold" else "pending"

    comp_prices = [float(c["price"]) for c in competitor_prices if c.get("price") is not None]
    competitor_price = min(comp_prices) if comp_prices else None

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pricing_recommendations (
                    store_id, sku, current_price, recommended_price, currency, reasoning,
                    strategy, status, correlation_id, fallback_used, meta
                )
                VALUES (%s, %s, %s, %s, 'USD', %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, created_at
                """,
                (
                    store_id,
                    sku,
                    current_price,
                    rec_price,
                    parsed.get("reasoning") or "",
                    parsed.get("strategy") or strategy.get("name"),
                    rec_status,
                    corr,
                    fb or bool(parsed.get("fallback_used")),
                    json.dumps(
                        {
                            "competitor_prices": competitor_prices,
                            "competitor_price": competitor_price,
                            "min_margin_pct": min_margin,
                            "floor": floor,
                            "action": action_l,
                        }
                    ),
                ),
            )
            row = cur.fetchone()

    slack_gate = (
        cfg["slack_enabled"]
        and _truthy(flat.get("pricing_alert_enabled", "true"))
        and (cfg["mode"] == "production" or cfg["slack_in_test"])
    )
    write_audit(
        action="pricing_recommended",
        store_id=store_id,
        correlation_id=corr,
        entity_type="pricing_recommendation",
        entity_id=str(row["id"]),
        detail={
            "sku": sku,
            "recommended_price": rec_price,
            "fallback_used": fb,
            "action": action_l,
            "status": rec_status,
            "competitor_price": competitor_price,
        },
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "recommendation_id": str(row["id"]),
        "store_id": store_id,
        "sku": sku,
        "title": title,
        "image_url": image_url,
        "current_price": current_price,
        "recommended_price": rec_price,
        "competitor_price": competitor_price,
        "competitor_prices": competitor_prices,
        "reasoning": parsed.get("reasoning"),
        "strategy": parsed.get("strategy"),
        "action": action_l,
        "status": rec_status,
        "needs_approval": action_l != "hold",
        "fallback_used": bool(fb or parsed.get("fallback_used")),
        "should_alert_slack": slack_gate,
        "mode": cfg["mode"],
    }


def pricing_action(
    *,
    recommendation_id: str,
    action: str,
    actor: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Approve or reject a pricing recommendation; apply writeback only when gated."""
    cfg = get_config()
    corr = correlation_id or _uuid()
    action_l = (action or "").strip().lower()
    if action_l not in {"approve", "reject"}:
        return {"ok": False, "error": "action_must_be_approve_or_reject"}

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pricing_recommendations WHERE id = %s", (recommendation_id,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "recommendation_not_found"}
            if row["status"] not in {"pending", "skipped_test_mode"}:
                return {
                    "ok": True,
                    "idempotent": True,
                    "recommendation_id": recommendation_id,
                    "sku": row.get("sku"),
                    "status": row["status"],
                    "requested_action": action_l,
                    "writeback_status": (row.get("meta") or {}).get("writeback_status") or "none",
                    "recommended_price": float(row["recommended_price"])
                    if row.get("recommended_price") is not None
                    else None,
                    "message": f"already_{row['status']}_reject_ignored"
                    if action_l == "reject" and row["status"] in {"approved", "applied"}
                    else f"already_{row['status']}",
                }

            live_results: list[dict[str, Any]] = []
            if action_l == "reject":
                new_status = "rejected"
                writeback_status = "none"
            else:
                # Approve: live writeback only in production when writeback_enabled.
                if cfg["mode"] != "production":
                    new_status = "approved"
                    writeback_status = "skipped_test_mode"
                elif not _truthy(cfg["flat"].get("writeback_enabled", "true")):
                    new_status = "approved"
                    writeback_status = "skipped_disabled"
                else:
                    live_results = _apply_live_price_writeback(
                        store_id=str(row["store_id"]),
                        sku=str(row["sku"]),
                        price=float(row["recommended_price"]),
                        currency=row.get("currency") or "USD",
                        correlation_id=corr,
                    )
                    cur.execute(
                        """
                        INSERT INTO price_snapshots (
                            store_id, sku, source_type, source_name, price, currency, raw
                        )
                        VALUES (%s, %s, 'own', 'pricing_apply', %s, %s, %s::jsonb)
                        """,
                        (
                            row["store_id"],
                            row["sku"],
                            row["recommended_price"],
                            row.get("currency") or "USD",
                            json.dumps(
                                {
                                    "recommendation_id": recommendation_id,
                                    "actor": actor,
                                    "correlation_id": corr,
                                    "live_writebacks": live_results,
                                }
                            ),
                        ),
                    )
                    new_status = "applied"
                    live_statuses = [r.get("live_status") for r in live_results]
                    if any(s == "ok" for s in live_statuses):
                        writeback_status = (
                            "applied"
                            if all(s in {"ok", "skipped_no_credentials", "sot_only"} for s in live_statuses)
                            else "partial"
                        )
                    elif all(s in {"skipped_no_credentials", "sot_only"} for s in live_statuses):
                        writeback_status = "applied_sot_only"
                    else:
                        writeback_status = "failed" if any(s == "error" for s in live_statuses) else "applied_sot_only"

            cur.execute(
                """
                UPDATE pricing_recommendations
                SET status = %s, updated_at = NOW(),
                    meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                RETURNING *
                """,
                (
                    new_status,
                    json.dumps(
                        {
                            "actor": actor,
                            "action": action_l,
                            "writeback_status": writeback_status,
                            "correlation_id": corr,
                            "live_writebacks": live_results,
                        }
                    ),
                    recommendation_id,
                ),
            )
            updated = cur.fetchone()

    write_audit(
        action=f"pricing_{action_l}",
        store_id=str(row["store_id"]),
        correlation_id=corr,
        entity_type="pricing_recommendation",
        entity_id=recommendation_id,
        detail={"status": new_status, "writeback_status": writeback_status, "actor": actor, "live_writebacks": live_results},
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "recommendation_id": recommendation_id,
        "sku": updated["sku"],
        "status": new_status,
        "writeback_status": writeback_status,
        "live_writebacks": live_results,
        "recommended_price": float(updated["recommended_price"]) if updated.get("recommended_price") else None,
        "mode": cfg["mode"],
    }


def insights_rfm(*, store_id: str, correlation_id: str | None = None) -> dict[str, Any]:
    """Recompute RFM fields on customers from orders."""
    corr = correlation_id or _uuid()
    now = _now()
    updated = 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.email,
                       MAX(o.ordered_at) AS last_order,
                       COUNT(o.id) AS freq,
                       COALESCE(SUM(NULLIF((o.totals->>'total_price')::numeric, 0)), 0) AS monetary
                FROM customers c
                LEFT JOIN orders o ON o.store_id = c.store_id
                  AND (o.customer_email = c.email OR o.raw->'customer'->>'email' = c.email)
                WHERE c.store_id = %s
                GROUP BY c.id, c.email
                """,
                (store_id,),
            )
            rows = list(cur.fetchall() or [])
            for r in rows:
                last = r.get("last_order")
                if last and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                recency_days = (now - last).days if last else 999
                freq = int(r.get("freq") or 0)
                monetary = float(r.get("monetary") or 0)
                if freq >= 3 and monetary >= 200:
                    segment = "champion"
                    vip = True
                elif freq >= 2 or monetary >= 100:
                    segment = "loyal"
                    vip = monetary >= 150
                elif recency_days <= 60:
                    segment = "active"
                    vip = False
                else:
                    segment = "at_risk"
                    vip = False
                cur.execute(
                    """
                    UPDATE customers
                    SET rfm_recency = %s, rfm_frequency = %s, rfm_monetary = %s,
                        rfm_segment = %s, vip = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (recency_days, freq, monetary, segment, vip, r["id"]),
                )
                updated += 1

    write_audit(
        action="insights_rfm",
        store_id=store_id,
        correlation_id=corr,
        entity_type="customers",
        detail={"updated": updated},
    )
    return {"ok": True, "correlation_id": corr, "store_id": store_id, "customers_updated": updated}


def insights_churn(*, store_id: str, correlation_id: str | None = None) -> dict[str, Any]:
    """Heuristic churn_score from RFM recency/frequency."""
    corr = correlation_id or _uuid()
    updated = 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, rfm_recency, rfm_frequency, rfm_monetary
                FROM customers WHERE store_id = %s
                """,
                (store_id,),
            )
            for r in cur.fetchall() or []:
                rec = int(r.get("rfm_recency") or 999)
                freq = int(r.get("rfm_frequency") or 0)
                score = min(1.0, max(0.0, (rec / 180.0) * (1.0 if freq < 2 else 0.5)))
                cur.execute(
                    "UPDATE customers SET churn_score = %s, updated_at = NOW() WHERE id = %s",
                    (round(score, 4), r["id"]),
                )
                updated += 1
    write_audit(
        action="insights_churn",
        store_id=store_id,
        correlation_id=corr,
        entity_type="customers",
        detail={"updated": updated},
    )
    return {"ok": True, "correlation_id": corr, "store_id": store_id, "customers_updated": updated}


def marketing_copy(
    *,
    campaign_type: str = "abandon_cart",
    segment: str = "active",
    offer_context: str = "",
    tone: str = "friendly",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    corr = correlation_id or _uuid()
    prompt = load_prompt("marketing_copy")
    user = prompt.render(
        campaign_type=campaign_type,
        segment=segment,
        offer_context=offer_context or "10% off your cart",
        tone=tone,
    )

    def _fallback() -> dict[str, Any]:
        return {
            "subject": "Your cart is waiting",
            "body": f"Hi — still thinking it over? {offer_context or 'Come back for a special offer.'}",
            "cta": "Complete your order",
            "fallback_used": True,
        }

    parsed, fb = complete_json(
        system="Return marketing email copy JSON only.",
        user=user,
        model=prompt.model,
        fallback=_fallback,
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "subject": parsed.get("subject") or _fallback()["subject"],
        "body": parsed.get("body") or _fallback()["body"],
        "cta": parsed.get("cta") or _fallback()["cta"],
        "fallback_used": bool(fb or parsed.get("fallback_used")),
        "campaign_type": campaign_type,
        "segment": segment,
    }


def marketing_enroll(
    *,
    store_id: str,
    campaign_key: str = "abandon_cart_default",
    campaign_type: str = "abandon_cart",
    email: str,
    customer_id: str | None = None,
    correlation_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure campaign + enrollment row (idempotent on campaign+email open states)."""
    cfg = get_config()
    corr = correlation_id or _uuid()
    if not _truthy(cfg["flat"].get("enabled", "true")) or not _truthy(
        cfg["flat"].get("abandon_cart_enabled" if campaign_type == "abandon_cart" else "vip_enabled", "true")
    ):
        return {"ok": True, "skipped": True, "reason": "marketing_disabled", "correlation_id": corr}

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaigns (store_id, campaign_key, campaign_type, name, enabled, config)
                VALUES (%s, %s, %s, %s, TRUE, '{}'::jsonb)
                ON CONFLICT (store_id, campaign_key) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                (store_id, campaign_key, campaign_type, campaign_key.replace("_", " ").title()),
            )
            camp = cur.fetchone()
            campaign_id = str(camp["id"])
            cur.execute(
                """
                SELECT id, status FROM campaign_enrollments
                WHERE campaign_id = %s AND email = %s
                  AND status IN ('enrolled', 'in_progress')
                ORDER BY created_at DESC LIMIT 1
                """,
                (campaign_id, email),
            )
            existing = cur.fetchone()
            if existing:
                return {
                    "ok": True,
                    "idempotent": True,
                    "enrollment_id": str(existing["id"]),
                    "campaign_id": campaign_id,
                    "status": existing["status"],
                    "correlation_id": corr,
                    "send_email": False,
                    "send_status": "skipped_already_enrolled",
                }

            cur.execute(
                """
                INSERT INTO campaign_enrollments (
                    campaign_id, store_id, customer_id, email, step, status,
                    next_action_at, meta, correlation_id
                )
                VALUES (%s, %s, %s, %s, 0, 'enrolled', NOW(), %s::jsonb, %s)
                RETURNING id, status, next_action_at
                """,
                (
                    campaign_id,
                    store_id,
                    customer_id,
                    email,
                    json.dumps(meta or {}),
                    corr,
                ),
            )
            enr = cur.fetchone()

    write_audit(
        action="marketing_enrolled",
        store_id=store_id,
        correlation_id=corr,
        entity_type="campaign_enrollment",
        entity_id=str(enr["id"]),
        detail={"campaign_key": campaign_key, "email": email},
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "enrollment_id": str(enr["id"]),
        "campaign_id": campaign_id,
        "status": enr["status"],
        "next_action_at": enr["next_action_at"].isoformat() if enr.get("next_action_at") else None,
        "send_email": False,
        "send_status": "pending_advance",
    }


def marketing_advance(
    *,
    store_id: str | None = None,
    limit: int = 20,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Advance due enrollments; generate copy; skip real email unless production + send_email_in_test."""
    cfg = get_config()
    corr = correlation_id or _uuid()
    mode = cfg["mode"]
    send_in_test = _truthy(cfg["flat"].get("send_email_in_test", "false"))
    allow_send = mode == "production" or send_in_test

    results: list[dict[str, Any]] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.*, c.campaign_type, c.campaign_key
                FROM campaign_enrollments e
                JOIN campaigns c ON c.id = e.campaign_id
                WHERE e.status IN ('enrolled', 'in_progress')
                  AND (e.next_action_at IS NULL OR e.next_action_at <= NOW())
                  AND (%s::uuid IS NULL OR e.store_id = %s::uuid)
                ORDER BY e.next_action_at NULLS FIRST
                LIMIT %s
                """,
                (store_id, store_id, limit),
            )
            due = list(cur.fetchall() or [])

            for e in due:
                copy = marketing_copy(
                    campaign_type=e.get("campaign_type") or "abandon_cart",
                    segment="vip" if e.get("campaign_type") == "vip" else "active",
                    offer_context="Complete checkout — limited offer",
                    correlation_id=corr,
                )
                step = int(e.get("step") or 0) + 1
                if not allow_send:
                    send_status = "skipped_test_mode"
                    new_status = "skipped_test_mode" if step >= 1 else "in_progress"
                else:
                    send_status = "queued_resend"
                    new_status = "completed" if step >= 2 else "in_progress"

                next_at = _now() + timedelta(hours=24) if new_status == "in_progress" else None
                meta = e.get("meta") if isinstance(e.get("meta"), dict) else {}
                meta = {
                    **meta,
                    "last_copy": {
                        "subject": copy["subject"],
                        "cta": copy["cta"],
                        "fallback_used": copy["fallback_used"],
                    },
                    "send_status": send_status,
                }
                cur.execute(
                    """
                    UPDATE campaign_enrollments
                    SET step = %s, status = %s, next_action_at = %s, meta = %s::jsonb,
                        correlation_id = COALESCE(%s, correlation_id), updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, status, step
                    """,
                    (step, new_status, next_at, json.dumps(meta), corr, e["id"]),
                )
                upd = cur.fetchone()
                results.append(
                    {
                        "enrollment_id": str(upd["id"]),
                        "email": e.get("email"),
                        "step": upd["step"],
                        "status": upd["status"],
                        "send_status": send_status,
                        "subject": copy["subject"],
                        "body": copy["body"],
                        "cta": copy["cta"],
                        "should_send_email": allow_send and send_status == "queued_resend",
                    }
                )

    write_audit(
        action="marketing_advanced",
        store_id=store_id,
        correlation_id=corr,
        entity_type="campaign_enrollment",
        detail={"count": len(results), "allow_send": allow_send},
    )
    return {
        "ok": True,
        "correlation_id": corr,
        "mode": mode,
        "allow_send": allow_send,
        "advanced": results,
        "count": len(results),
    }


def list_competitor_targets(store_id: str | None = None) -> dict[str, Any]:
    """Read whitelist URLs from config_pricing competitor_urls JSON array."""
    cfg = get_config()
    raw = _cfg(cfg["flat"], "competitor_urls", "[]")
    try:
        urls = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except json.JSONDecodeError:
        urls = []
    if not isinstance(urls, list):
        urls = []
    demo_store = _cfg(cfg["flat"], "demo_store_id", "") or os.getenv("ECOM_DEMO_STORE_ID", "")
    return {
        "ok": True,
        "store_id": store_id or demo_store or None,
        "targets": urls,
        "sku": _cfg(cfg["flat"], "demo_pricing_sku", "sku-managed-1"),
        "skus": [
            s.strip()
            for s in _cfg(
                cfg["flat"],
                "demo_pricing_skus",
                "sku-managed-1,SNOWBOARD-LIQUID",
            ).split(",")
            if s.strip()
        ],
    }
