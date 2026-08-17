# Shopify setup

Declarative webhooks via Shopify CLI app → n8n **Ecom Platform Ingest** at `/webhook/ecom-shopify`.

## App config

Primary deploy file: `shopify-app/shopify.app.toml`.

Key fields:

```toml
[[webhooks.subscriptions]]
topics = [
  "products/create", "products/update",
  "inventory_levels/update",
  "orders/create", "orders/updated",
  "refunds/create",
]
uri = "https://<your-n8n-host>/webhook/ecom-shopify"

[access_scopes]
scopes = "write_inventory,read_inventory,read_locations,read_orders,read_products,write_products"
```

P3b writeback needs `write_inventory` + `write_products` + `read_locations`.

## Deploy subscriptions

```bash
cd shopify-app
shopify auth login
shopify app config link   # first time
# Edit uri when ngrok/domain changes
shopify app deploy
```

Install app on dev store. Delete duplicate topics under **Settings → Notifications → Webhooks** to avoid double delivery.

## HMAC secret

App webhooks sign with **App API secret key** (Dev Dashboard → app → Credentials):

```bash
SHOPIFY_WEBHOOK_SECRET=<app_api_secret_key>
```

Restart `ecom_python_ai` after `.env` change. Empty secret skips verify (local only).

Sidecar verifies in `/ingest/shopify`.

## Admin token + location (P3b writeback)

From Custom App or CLI offline token:

```bash
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
SHOPIFY_LOCATION_ID=gid_or_numeric_location_id
SHOPIFY_API_VERSION=2024-10
```

`SHOPIFY_LOCATION_ID` required for inventory level updates at a specific location.

Live writeback gates: `mode=production`, `writeback_enabled=true`, creds present. See [TEST_PRODUCTION.md](TEST_PRODUCTION.md).

## n8n checklist

- [ ] **Ecom Platform Ingest** Active
- [ ] Production webhook URL matches TOML `uri`
- [ ] Error Workflow → `Ecom Error Handler`

More: [shopify-app/README.md](../../shopify-app/README.md), [CREDENTIALS.md](CREDENTIALS.md).
