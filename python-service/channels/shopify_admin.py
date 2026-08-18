"""Shopify Admin REST client (offline access token). Secrets never stored in PG."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "2024-10"


def shopify_admin_configured() -> bool:
    return bool(
        _shop_domain()
        and os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
    )


def _shop_domain() -> str:
    raw = (
        os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip()
        or os.getenv("SHOPIFY_STORE_HANDLE", "").strip()
    )
    if not raw:
        return ""
    if ".myshopify.com" in raw:
        return raw.replace("https://", "").replace("http://", "").split("/")[0]
    return f"{raw}.myshopify.com"


class ShopifyAdminClient:
    """Minimal Admin REST helpers for inventory set + variant price update."""

    def __init__(
        self,
        *,
        shop_domain: str | None = None,
        access_token: str | None = None,
        api_version: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.shop_domain = shop_domain or _shop_domain()
        self.access_token = access_token or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
        self.api_version = api_version or os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION).strip()
        self.timeout = timeout
        self.default_location_id = os.getenv("SHOPIFY_LOCATION_ID", "").strip() or None

    @property
    def configured(self) -> bool:
        return bool(self.shop_domain and self.access_token)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"https://{self.shop_domain}/admin/api/{self.api_version}",
            headers={
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json",
                "User-Agent": "ecom-workflow-sidecar/1.0",
            },
            timeout=self.timeout,
        )

    def ping(self) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "reason": "not_configured"}
        try:
            with self._client() as client:
                resp = client.get("/shop.json")
                if resp.status_code < 400:
                    return {"ok": True, "status_code": resp.status_code}
                return {"ok": False, "status_code": resp.status_code, "body": resp.text[:200]}
        except Exception as exc:
            logger.warning("Shopify Admin ping failed: %s", exc)
            return {"ok": False, "reason": str(exc)[:200]}

    def get_inventory_item_sku(self, inventory_item_id: str | int) -> str | None:
        """Resolve SKU for inventory_levels/update payloads that omit variant.sku."""
        if not self.configured or inventory_item_id is None:
            return None
        item_id = inventory_item_id
        if isinstance(item_id, str) and item_id.startswith("gid://"):
            m = re.search(r"/(\d+)$", item_id)
            item_id = m.group(1) if m else item_id
        try:
            with self._client() as client:
                resp = client.get(f"/inventory_items/{int(item_id)}.json")
                if resp.status_code >= 400:
                    logger.warning(
                        "Shopify inventory_item %s lookup HTTP %s",
                        item_id,
                        resp.status_code,
                    )
                    return None
                sku = (resp.json().get("inventory_item") or {}).get("sku")
                text = str(sku).strip() if sku else ""
                return text or None
        except Exception as exc:
            logger.warning("Shopify get_inventory_item_sku failed: %s", exc)
            return None

    def set_inventory_available(
        self,
        *,
        inventory_item_id: str | int,
        available: int,
        location_id: str | int | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "live_status": "skipped_no_credentials"}
        loc = location_id or self.default_location_id
        if not loc:
            return {"ok": False, "live_status": "error", "error": "missing_location_id"}
        try:
            with self._client() as client:
                resp = client.post(
                    "/inventory_levels/set.json",
                    json={
                        "location_id": int(loc),
                        "inventory_item_id": int(inventory_item_id),
                        "available": int(available),
                    },
                )
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "live_status": "error",
                        "status_code": resp.status_code,
                        "error": resp.text[:300],
                    }
                return {
                    "ok": True,
                    "live_status": "ok",
                    "inventory_item_id": int(inventory_item_id),
                    "location_id": int(loc),
                    "available": int(available),
                }
        except Exception as exc:
            logger.exception("Shopify set_inventory_available failed")
            return {"ok": False, "live_status": "error", "error": str(exc)[:300]}

    def set_variant_price(self, *, variant_id: str | int, price: float) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "live_status": "skipped_no_credentials"}
        price_s = f"{float(price):.2f}"
        try:
            with self._client() as client:
                resp = client.put(
                    f"/variants/{int(variant_id)}.json",
                    json={"variant": {"id": int(variant_id), "price": price_s}},
                )
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "live_status": "error",
                        "status_code": resp.status_code,
                        "error": resp.text[:300],
                        "variant_id": variant_id,
                    }
                return {"ok": True, "live_status": "ok", "variant_id": int(variant_id), "price": price_s}
        except Exception as exc:
            logger.exception("Shopify set_variant_price failed")
            return {"ok": False, "live_status": "error", "error": str(exc)[:300], "variant_id": variant_id}

    def find_variant_id_by_sku(self, sku: str) -> str | None:
        """Search products for a variant matching SKU (paginated; demo + small catalogs)."""
        if not self.configured or not sku:
            return None
        try:
            with self._client() as client:
                page_info = None
                for _ in range(10):
                    params: dict[str, Any] = {"limit": 50, "fields": "id,variants"}
                    if page_info:
                        params = {"limit": 50, "page_info": page_info, "fields": "id,variants"}
                    resp = client.get("/products.json", params=params)
                    resp.raise_for_status()
                    for product in resp.json().get("products") or []:
                        for variant in product.get("variants") or []:
                            if str(variant.get("sku") or "") == sku:
                                return str(variant.get("id"))
                    link = resp.headers.get("Link") or ""
                    next_m = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link)
                    if not next_m:
                        break
                    page_info = next_m.group(1)
            return None
        except Exception as exc:
            logger.warning("Shopify find_variant_id_by_sku failed: %s", exc)
            return None


def extract_shopify_inventory_ids(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Pull inventory_item_id / location_id from webhook or Admin payloads."""
    raw = raw or {}
    item_id = raw.get("inventory_item_id")
    location_id = raw.get("location_id")
    if not item_id and isinstance(raw.get("variant"), dict):
        item_id = raw["variant"].get("inventory_item_id")
    if not item_id:
        for v in raw.get("variants") or []:
            if v.get("inventory_item_id"):
                item_id = v.get("inventory_item_id")
                break
    # Strip GraphQL gid to numeric id
    if isinstance(item_id, str) and item_id.startswith("gid://"):
        m = re.search(r"/(\d+)$", item_id)
        item_id = m.group(1) if m else item_id
    if isinstance(location_id, str) and location_id.startswith("gid://"):
        m = re.search(r"/(\d+)$", location_id)
        location_id = m.group(1) if m else location_id
    return {"inventory_item_id": item_id, "location_id": location_id}


def extract_shopify_variant_id(raw: dict[str, Any] | None, *, sku: str | None = None) -> str | None:
    raw = raw or {}
    if raw.get("variant_id"):
        return str(raw["variant_id"])
    if isinstance(raw.get("variant"), dict) and raw["variant"].get("id"):
        return str(raw["variant"]["id"])
    variants = raw.get("variants") or []
    if sku:
        for v in variants:
            if str(v.get("sku") or "") == sku and v.get("id"):
                return str(v["id"])
    if variants and variants[0].get("id"):
        return str(variants[0]["id"])
    # listings.external_id may be product id — not usable as variant
    return None
