# Configuration reference

Runtime business config lives in Postgres **`config_*`** tables. Sidecar loads on each request. **No secrets** — only flags and thresholds.

Change at runtime:

```sql
UPDATE config_inventory SET value = 'shopify,woocommerce' WHERE key = 'slave_channels';
```

## config_main

| Key | Default | Effect |
|-----|---------|--------|
| `mode` | `test` | `test`: skip live writeback / gated Slack digests. `production`: enable side effects |
| `project_tag` | `ecom-workflow` | Langfuse / workflow tag |
| `demo_woo_store_key` | `demo-woocommerce` | Default `store_key` for Woo webhooks when header omits it |

## config_inventory

| Key | Default | Effect |
|-----|---------|--------|
| `master_channel` | `shopify` | Authoritative inventory channel |
| `slave_channels` | `woocommerce` | Comma-separated channels receiving drift writeback |
| `safety_stock_default` | `5` | Default safety stock units |
| `writeback_enabled` | `true` | Allow live slave writeback in production |
| `writeback_align_sot` | `true` | Align PG `inventory_levels` after live writeback attempt |
| `inventory_drift_enabled` | `true` | Slack on drift when notification gates pass |

## config_pricing

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | Pricing engine on/off |
| `min_margin_pct` | `15` | Minimum margin percent |
| `price_writeback_channels` | `shopify,woocommerce` | Live price writeback targets on Slack Approve |
| `demo_pricing_sku` | `sku-managed-1` | Primary default SKU |
| `demo_pricing_skus` | `sku-managed-1,SNOWBOARD-LIQUID` | Cron multi-SKU list (comma-separated; multi-channel demo) |
| `competitor_urls` | JSON array | Whitelist URLs for Competitor Crawl |

## config_marketing

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | Marketing orchestrator on/off |
| `abandon_cart_enabled` | `true` | Abandon cart sequences |
| `vip_enabled` | `true` | VIP outreach |
| `send_email_in_test` | `false` | Never send real email in test mode |

## config_notifications

| Key | Default | Effect |
|-----|---------|--------|
| `slack_enabled` | `true` | Master Slack switch |
| `slack_in_test` | `true` | Allow ops/drift Slack in test mode |
| `email_provider` | `resend` | Label for ops; n8n Marketing Orchestrator sends via Resend HTTP |
| `daily_summary_enabled` | `true` | Daily Summary Slack when `mode=production` |
| `weekly_summary_enabled` | `true` | Weekly Summary Slack when `mode=production` |
| `keepalive_alert_enabled` | `true` | Slack when Health Keepalive fails in production |
| `inventory_drift_enabled` | `true` | Drift alerts |
| `pricing_alert_enabled` | `true` | Pricing recommendation Slack |

## Inspect via API

```bash
curl http://localhost:8003/config
```

Returns nested config + derived `mode` / `master_channel` (no secrets).

See [TEST_PRODUCTION.md](TEST_PRODUCTION.md), [DB_SETUP.md](DB_SETUP.md).
