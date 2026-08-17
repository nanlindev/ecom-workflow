"""Ecom Python AI sidecar: health, prompts, P1 trust APIs + P2 intel APIs.

Called from n8n at http://ecom_python_ai:8001/...
On startup, applies idempotent SQL migrations against ecom_postgres.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from db import ping_db, run_migrations
from domain_p1 import (
    decide_return,
    get_config,
    ingest_shopify,
    ingest_woocommerce,
    inventory_sync,
    track_order,
    write_error_log,
)
from domain_p2 import (
    insights_churn,
    insights_rfm,
    list_competitor_targets,
    marketing_advance,
    marketing_copy,
    marketing_enroll,
    parse_competitor,
    pricing_action,
    recommend_price,
)
from domain_p3 import keepalive_check, ops_summary
from observability import attach_incoming_trace_context, detach_trace_context, get_correlation_id_from_headers
from prompt_loader import list_prompts, load_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "v1.0")
ENVIRONMENT = (
    os.getenv("ENVIRONMENT")
    or os.getenv("LANGFUSE_TRACING_ENVIRONMENT")
    or "development"
)
os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", ENVIRONMENT)

_langfuse = None
if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
    try:
        from langfuse import get_client

        _langfuse = get_client()
        logger.info(
            "Langfuse host: %s, environment: %s",
            os.getenv("LANGFUSE_HOST", "not-set"),
            ENVIRONMENT,
        )
        try:
            _langfuse.auth_check()
            logger.info("Langfuse auth_check passed")
        except Exception as exc:
            logger.warning("Langfuse auth_check failed: %s", exc)
    except Exception as exc:
        logger.warning("Langfuse init skipped: %s", exc)
else:
    logger.info("Langfuse keys not set; tracing metadata only via OTEL")

app = FastAPI(title="Ecom AI Service", version=SERVICE_VERSION)


@app.on_event("startup")
def _startup_migrate() -> None:
    """Run pending SQL migrations before accepting traffic."""
    try:
        applied = run_migrations()
        if applied:
            logger.info("Applied migrations: %s", ", ".join(applied))
        else:
            logger.info("Database schema up to date")
    except Exception:
        logger.exception("Startup migration failed")
        raise


@app.middleware("http")
async def propagate_w3c_trace_context(request: Request, call_next):
    token = attach_incoming_trace_context(request.headers)
    try:
        return await call_next(request)
    finally:
        detach_trace_context(token)


@app.get("/health")
def health_check():
    """Liveness / readiness probe: process up + Postgres reachable."""
    db_ok = False
    db_error = None
    try:
        db_ok = ping_db()
    except Exception as exc:
        db_error = str(exc)[:200]
        logger.warning("Health DB ping failed: %s", exc)

    status = "healthy" if db_ok else "degraded"
    body: dict[str, Any] = {
        "status": status,
        "service": "n8n-ecom-ai-service",
        "version": SERVICE_VERSION,
        "environment": ENVIRONMENT,
        "database": "ok" if db_ok else "error",
    }
    if db_error:
        body["database_error"] = db_error
    return body


@app.get("/prompts")
def list_prompt_versions():
    """List loaded prompt keys with version and hash (from prompts/*.md files)."""
    return {
        key: {
            "version": load_prompt(key).version,
            "hash": load_prompt(key).prompt_hash,
        }
        for key in list_prompts()
    }


@app.get("/config")
def read_config():
    """Return config_* tables and derived mode / master_channel (no secrets)."""
    return get_config()


class ShopifyIngestRequest(BaseModel):
    raw_body: Any = Field(..., description="Webhook raw body string or JSON object")
    headers: dict[str, Any] = Field(default_factory=dict)
    store_key: str | None = None
    correlation_id: str | None = None
    skip_verify: bool = False


@app.post("/ingest/shopify")
def ingest_shopify_endpoint(body: ShopifyIngestRequest, request: Request):
    """Verify Shopify HMAC, normalize, idempotent upsert, return dispatch flags.

    Always HTTP 200 for business outcomes (ok/signature_valid in body) so n8n
    can branch without treating reject as transport error.
    """
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return ingest_shopify(
        raw_body=body.raw_body,
        headers=body.headers,
        store_key=body.store_key,
        correlation_id=corr,
        skip_verify=body.skip_verify,
    )


class WooIngestRequest(BaseModel):
    raw_body: Any = Field(..., description="Webhook raw body string or JSON object")
    headers: dict[str, Any] = Field(default_factory=dict)
    store_key: str | None = None
    correlation_id: str | None = None
    skip_verify: bool = False


@app.post("/ingest/woocommerce")
def ingest_woocommerce_endpoint(body: WooIngestRequest, request: Request):
    """Verify Woo signature, normalize to shared schema, return dispatch flags."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return ingest_woocommerce(
        raw_body=body.raw_body,
        headers=body.headers,
        store_key=body.store_key,
        correlation_id=corr,
        skip_verify=body.skip_verify,
    )


class InventorySyncRequest(BaseModel):
    store_id: str | None = None
    store_key: str | None = None
    sku: str | None = None
    correlation_id: str | None = None
    slave_levels: list[dict[str, Any]] | None = None


@app.post("/inventory/sync")
def inventory_sync_endpoint(body: InventorySyncRequest, request: Request):
    """Merge channels with master conflict strategy; test skips writeback."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return inventory_sync(
        store_id=body.store_id,
        store_key=body.store_key,
        sku=body.sku,
        correlation_id=corr,
        slave_levels=body.slave_levels,
    )


class OrderTrackRequest(BaseModel):
    store_id: str
    order_id: str | None = None
    external_order_id: str | None = None
    new_status: str | None = None
    correlation_id: str | None = None


@app.post("/orders/track")
def orders_track_endpoint(body: OrderTrackRequest, request: Request):
    """Order status machine + anomaly flags for Slack gating."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    result = track_order(
        store_id=body.store_id,
        order_id=body.order_id,
        external_order_id=body.external_order_id,
        new_status=body.new_status,
        correlation_id=corr,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result


class ReturnDecideRequest(BaseModel):
    store_id: str
    return_id: str | None = None
    external_return_id: str | None = None
    order_id: str | None = None
    amount: float | None = None
    days_since_order: int | None = None
    reason: str | None = None
    correlation_id: str | None = None


@app.post("/returns/decide")
def returns_decide_endpoint(body: ReturnDecideRequest, request: Request):
    """Amount/time rules → auto_approve | manual_review | reject."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return decide_return(
        store_id=body.store_id,
        return_id=body.return_id,
        external_return_id=body.external_return_id,
        order_id=body.order_id,
        amount=body.amount,
        days_since_order=body.days_since_order,
        reason=body.reason,
        correlation_id=corr,
    )


# P2 routes


class CompetitorParseRequest(BaseModel):
    store_id: str
    url: str
    raw_content: str = ""
    sku: str | None = None
    source_name: str | None = None
    correlation_id: str | None = None


@app.post("/competitors/parse")
def competitors_parse_endpoint(body: CompetitorParseRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return parse_competitor(
        store_id=body.store_id,
        url=body.url,
        raw_content=body.raw_content,
        sku=body.sku,
        source_name=body.source_name,
        correlation_id=corr,
    )


@app.get("/competitors/targets")
def competitors_targets_endpoint(store_id: str | None = None):
    return list_competitor_targets(store_id)


class PricingRecommendRequest(BaseModel):
    store_id: str
    sku: str
    current_price: float | None = None
    cost: float | None = None
    correlation_id: str | None = None
    strategy: dict[str, Any] | None = None


@app.post("/pricing/recommend")
def pricing_recommend_endpoint(body: PricingRecommendRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return recommend_price(
        store_id=body.store_id,
        sku=body.sku,
        current_price=body.current_price,
        cost=body.cost,
        correlation_id=corr,
        strategy=body.strategy,
    )


class PricingActionRequest(BaseModel):
    recommendation_id: str
    action: str
    actor: str | None = None
    correlation_id: str | None = None


@app.post("/pricing/action")
def pricing_action_endpoint(body: PricingActionRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return pricing_action(
        recommendation_id=body.recommendation_id,
        action=body.action,
        actor=body.actor,
        correlation_id=corr,
    )


class InsightsRequest(BaseModel):
    store_id: str
    correlation_id: str | None = None


@app.post("/insights/rfm")
def insights_rfm_endpoint(body: InsightsRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return insights_rfm(store_id=body.store_id, correlation_id=corr)


@app.post("/insights/churn")
def insights_churn_endpoint(body: InsightsRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return insights_churn(store_id=body.store_id, correlation_id=corr)


class MarketingCopyRequest(BaseModel):
    campaign_type: str = "abandon_cart"
    segment: str = "active"
    offer_context: str = ""
    tone: str = "friendly"
    correlation_id: str | None = None


@app.post("/marketing/copy")
def marketing_copy_endpoint(body: MarketingCopyRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return marketing_copy(
        campaign_type=body.campaign_type,
        segment=body.segment,
        offer_context=body.offer_context,
        tone=body.tone,
        correlation_id=corr,
    )


class MarketingEnrollRequest(BaseModel):
    store_id: str
    email: str
    campaign_key: str = "abandon_cart_default"
    campaign_type: str = "abandon_cart"
    customer_id: str | None = None
    correlation_id: str | None = None
    meta: dict[str, Any] | None = None


@app.post("/marketing/enroll")
def marketing_enroll_endpoint(body: MarketingEnrollRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return marketing_enroll(
        store_id=body.store_id,
        campaign_key=body.campaign_key,
        campaign_type=body.campaign_type,
        email=body.email,
        customer_id=body.customer_id,
        correlation_id=corr,
        meta=body.meta,
    )


class MarketingAdvanceRequest(BaseModel):
    store_id: str | None = None
    limit: int = 20
    correlation_id: str | None = None


@app.post("/marketing/advance")
def marketing_advance_endpoint(body: MarketingAdvanceRequest, request: Request):
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return marketing_advance(store_id=body.store_id, limit=body.limit, correlation_id=corr)


class ErrorLogRequest(BaseModel):
    workflow_name: str = "unknown"
    node_name: str = "unknown"
    error_message: str = ""
    correlation_id: str | None = None
    store_id: str | None = None
    detail: dict[str, Any] | None = None


@app.post("/errors/log")
def errors_log_endpoint(body: ErrorLogRequest):
    """Persist workflow error for Error Handler."""
    return write_error_log(
        workflow_name=body.workflow_name,
        node_name=body.node_name,
        error_message=body.error_message,
        correlation_id=body.correlation_id,
        store_id=body.store_id,
        detail=body.detail,
    )


class OpsSummaryRequest(BaseModel):
    period: str = "daily"
    store_id: str | None = None
    store_key: str | None = None
    correlation_id: str | None = None


@app.post("/ops/summary")
def ops_summary_endpoint(body: OpsSummaryRequest, request: Request):
    """Daily/weekly ops digest for Slack-gated Summary workflows."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return ops_summary(
        period=body.period,
        store_id=body.store_id,
        store_key=body.store_key,
        correlation_id=corr,
    )


class KeepaliveRequest(BaseModel):
    correlation_id: str | None = None
    ping_channels: bool = True


@app.post("/ops/keepalive")
def keepalive_endpoint(body: KeepaliveRequest, request: Request):
    """Deep health for Cron keepalive (PG + optional channel pings)."""
    corr = body.correlation_id or get_correlation_id_from_headers(request.headers)
    return keepalive_check(correlation_id=corr, ping_channels=body.ping_channels)
