"""WooCommerce REST API client (Basic Auth). Secrets never stored in PG."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def woo_configured() -> bool:
    return bool(
        os.getenv("WOO_BASE_URL", "").strip()
        and os.getenv("WOO_CONSUMER_KEY", "").strip()
        and os.getenv("WOO_CONSUMER_SECRET", "").strip()
    )


class WooCommerceClient:
    """Minimal WooCommerce REST v3 client for stock/price writeback and SKU lookup."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("WOO_BASE_URL", "")).rstrip("/")
        self.consumer_key = consumer_key or os.getenv("WOO_CONSUMER_KEY", "")
        self.consumer_secret = consumer_secret or os.getenv("WOO_CONSUMER_SECRET", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.consumer_key and self.consumer_secret)

    def _auth_params(self) -> dict[str, str]:
        # Query-string keys survive proxies that strip the Authorization header.
        return {"consumer_key": self.consumer_key, "consumer_secret": self.consumer_secret}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"{self.base_url}/wp-json/wc/v3",
            timeout=self.timeout,
            trust_env=False,
            headers={"User-Agent": "ecom-workflow-sidecar/1.0"},
        )

    def ping(self) -> dict[str, Any]:
        """Light reachability: Woo REST index (not a product listing)."""
        if not self.configured:
            return {"ok": False, "reason": "not_configured"}
        try:
            with self._client() as client:
                resp = client.get("/", params=self._auth_params(), timeout=10.0)
                if resp.status_code < 400:
                    return {"ok": True, "status_code": resp.status_code}
                return {"ok": False, "status_code": resp.status_code, "body": resp.text[:200]}
        except Exception as exc:
            logger.warning("Woo ping failed: %s", exc)
            return {"ok": False, "reason": str(exc)[:200]}

    def find_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        if not self.configured or not sku:
            return None
        with self._client() as client:
            resp = client.get("/products", params={**self._auth_params(), "sku": sku})
            resp.raise_for_status()
            rows = resp.json()
            if isinstance(rows, list) and rows:
                return rows[0]
            return None

    def set_stock_by_sku(self, sku: str, available: int, *, product_id: str | int | None = None) -> dict[str, Any]:
        """Update manage_stock + stock_quantity for a product (or variation parent product)."""
        if not self.configured:
            return {"ok": False, "live_status": "skipped_no_credentials", "sku": sku}
        try:
            pid = product_id
            product: dict[str, Any] | None = None
            if not pid:
                product = self.find_product_by_sku(sku)
                if not product:
                    return {"ok": False, "live_status": "error", "error": "product_not_found", "sku": sku}
                pid = product.get("id")
                # Variations: Woo list by sku may return variation; update via parent/variations.
                if product.get("type") == "variation" and product.get("parent_id"):
                    return self._set_variation_stock(int(product["parent_id"]), int(pid), available, sku=sku)

            with self._client() as client:
                resp = client.put(
                    f"/products/{pid}",
                    params=self._auth_params(),
                    json={"manage_stock": True, "stock_quantity": int(available)},
                )
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "live_status": "error",
                        "status_code": resp.status_code,
                        "error": resp.text[:300],
                        "sku": sku,
                        "product_id": pid,
                    }
                return {
                    "ok": True,
                    "live_status": "ok",
                    "sku": sku,
                    "product_id": pid,
                    "available": int(available),
                }
        except Exception as exc:
            logger.exception("Woo set_stock_by_sku failed sku=%s", sku)
            return {"ok": False, "live_status": "error", "error": str(exc)[:300], "sku": sku}

    def _set_variation_stock(
        self, parent_id: int, variation_id: int, available: int, *, sku: str
    ) -> dict[str, Any]:
        with self._client() as client:
            resp = client.put(
                f"/products/{parent_id}/variations/{variation_id}",
                params=self._auth_params(),
                json={"manage_stock": True, "stock_quantity": int(available)},
            )
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "live_status": "error",
                    "status_code": resp.status_code,
                    "error": resp.text[:300],
                    "sku": sku,
                    "product_id": variation_id,
                }
            return {
                "ok": True,
                "live_status": "ok",
                "sku": sku,
                "product_id": variation_id,
                "available": int(available),
            }

    def set_price_by_sku(
        self,
        sku: str,
        price: float,
        *,
        product_id: str | int | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Update Woo price by SKU.

        If the product already has a sale_price, update sale_price only and leave
        regular_price (often used as compare-at / MSRP) unchanged. Otherwise set
        regular_price.
        """
        _ = currency  # Woo price is store-currency; kept for API symmetry
        if not self.configured:
            return {"ok": False, "live_status": "skipped_no_credentials", "sku": sku}
        price_s = f"{float(price):.2f}"
        try:
            product: dict[str, Any] | None = None
            pid = product_id
            if not pid:
                product = self.find_product_by_sku(sku)
                if not product:
                    return {"ok": False, "live_status": "error", "error": "product_not_found", "sku": sku}
                pid = product.get("id")
            else:
                with self._client() as client:
                    resp = client.get(f"/products/{pid}", params=self._auth_params())
                    if resp.status_code < 400:
                        product = resp.json()

            if not product:
                product = self.find_product_by_sku(sku) or {}

            payload = self._woo_price_payload(product, price_s)
            field = "sale_price" if "sale_price" in payload else "regular_price"

            if product.get("type") == "variation" and product.get("parent_id"):
                with self._client() as client:
                    resp = client.put(
                        f"/products/{int(product['parent_id'])}/variations/{int(pid)}",
                        params=self._auth_params(),
                        json=payload,
                    )
                    if resp.status_code >= 400:
                        return {
                            "ok": False,
                            "live_status": "error",
                            "status_code": resp.status_code,
                            "error": resp.text[:300],
                            "sku": sku,
                        }
                    return {
                        "ok": True,
                        "live_status": "ok",
                        "sku": sku,
                        "price": price_s,
                        "product_id": pid,
                        "price_field": field,
                    }

            with self._client() as client:
                resp = client.put(f"/products/{pid}", params=self._auth_params(), json=payload)
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "live_status": "error",
                        "status_code": resp.status_code,
                        "error": resp.text[:300],
                        "sku": sku,
                        "product_id": pid,
                    }
                return {
                    "ok": True,
                    "live_status": "ok",
                    "sku": sku,
                    "price": price_s,
                    "product_id": pid,
                    "price_field": field,
                }
        except Exception as exc:
            logger.exception("Woo set_price_by_sku failed sku=%s", sku)
            return {"ok": False, "live_status": "error", "error": str(exc)[:300], "sku": sku}

    @staticmethod
    def _woo_price_payload(product: dict[str, Any] | None, price_s: str) -> dict[str, str]:
        """Prefer updating sale_price when a sale is already configured; keep regular."""
        product = product or {}
        sale = str(product.get("sale_price") or "").strip()
        if sale:
            return {"sale_price": price_s}
        return {"regular_price": price_s}
