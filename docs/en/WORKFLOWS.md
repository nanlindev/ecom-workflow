# Workflows

Thirteen n8n workflows in `workflows/`. Import order: [INSTALL.md](INSTALL.md). Regenerate from `scripts/generate_workflows.py` (source of truth).

## Catalog

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| **Ecom Error Handler** | Error Trigger | Global sink: `error_logs` + optional Slack alert |
| **Ecom Platform Ingest** | Webhooks `ecom-shopify` / `ecom-woo` | HMAC verify → sidecar ingest → dispatch sync/track/returns |
| **Ecom Inventory Sync** | Cron + Execute Workflow | Merge master/slave levels; drift Slack; P3b live writeback |
| **Ecom Order Tracker** | Execute Workflow | Upsert order status from platform payloads |
| **Ecom Returns Automation** | Execute Workflow | Return decision rules + manual_review path |
| **Ecom Competitor Price Crawl** | Cron | Fetch competitor URLs → `/competitors/parse` → snapshots |
| **Ecom Pricing Engine** | Cron | Recommend price → Slack Approve/Reject when drift |
| **Ecom Customer Insights** | Cron | RFM + churn scoring via sidecar |
| **Ecom Marketing Orchestrator** | Cron | Enroll/advance sequences; Resend send (gated) |
| **Ecom Slack Actions** | Webhook `ecom-slack-interactions` | Pricing approve/reject → `/pricing/action` |
| **Ecom Daily Summary** | Schedule daily | `/ops/summary` daily digest → Slack when gated |
| **Ecom Weekly Summary** | Schedule weekly | Weekly ops digest → Slack when gated |
| **Ecom Health Keepalive** | Schedule | `/ops/keepalive` PG + channel ping; alert on failure |

## P1 chain

```text
Platform Ingest → /ingest/shopify|woocommerce
  → Execute Inventory Sync (master channel + resolved SKU only) / Order Tracker / Returns
Inventory Sync → POST /inventory/sync → drift Slack + writeback
```

## P2 chain

```text
Competitor Crawl → Pricing Engine → Slack Actions → /pricing/action
Customer Insights + Marketing Orchestrator (parallel Cron paths)
```

## P3 ops

Daily / Weekly Summary and Health Keepalive call `/ops/summary` and `/ops/keepalive`.

## Sidecar URLs (from n8n)

```text
http://ecom_python_ai:8001/ingest/shopify
http://ecom_python_ai:8001/ingest/woocommerce
http://ecom_python_ai:8001/inventory/sync
http://ecom_python_ai:8001/orders/track
http://ecom_python_ai:8001/returns/decide
http://ecom_python_ai:8001/pricing/recommend
http://ecom_python_ai:8001/pricing/action
http://ecom_python_ai:8001/ops/summary
http://ecom_python_ai:8001/ops/keepalive
http://ecom_python_ai:8001/errors/log
```

Gate details: [TEST_PRODUCTION.md](TEST_PRODUCTION.md), [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md).
