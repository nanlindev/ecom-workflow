# Test / production mode

Runtime mode is **`config_main.mode`** in Postgres (`test` | `production`). Sidecar reads config on each request.

## test mode (default)

```sql
-- config_main.mode = test
```

| Action | Behavior |
|--------|----------|
| Ingest / PG writes | Normal |
| LLM (pricing, marketing copy) | Runs |
| Inventory drift Slack | Allowed if `slack_in_test=true` (default) |
| Live inventory writeback | **Skipped** → `writeback_status=skipped_test_mode` |
| Live price writeback on approve | **Skipped** → `skipped_test_mode` |
| Marketing email (Resend) | **Skipped** → `send_status=skipped_test_mode` |
| Daily / Weekly Slack | **Skipped** unless you force production gates |
| Error Handler Slack alert | Only if `mode=production` + alert enabled |

Use for seed scripts and pipeline validation without touching live storefronts.

## production mode

```sql
UPDATE config_main SET value = 'production' WHERE key = 'mode';
```

| Action | Gate |
|--------|------|
| Live inventory writeback | `writeback_enabled=true` + slave creds (`WOO_*` or `SHOPIFY_ADMIN_*`) |
| Live price writeback | Slack **Approve** + `writeback_enabled=true` + `price_writeback_channels` + channel creds |
| Drift Slack | `inventory_drift_enabled` + `slack_enabled` |
| Pricing Slack | `pricing_alert_enabled` (see config seeds) |
| Marketing email | `config_marketing.enabled` + `send_email_in_test=false` |
| Daily / Weekly Slack | `daily_summary_enabled` / `weekly_summary_enabled` |
| Keepalive alert | `keepalive_alert_enabled` |

## writeback_status values

Inventory sync and pricing action return:

| Value | Meaning |
|-------|---------|
| `none` | No drift / no writeback attempted |
| `skipped_test_mode` | `mode=test` |
| `skipped_disabled` | `writeback_enabled=false` |
| `applied` | At least one channel API write succeeded |
| `applied_sot_only` | PG SoT aligned; no live API (missing creds or sot-only path) |
| `partial` | Mixed ok / error across channels |
| `failed` | Live API errors |

Channel detail in `channel_writebacks[].live_status` (`ok`, `skipped_no_credentials`, `error`, …).

## P3b env vars (live writeback)

```bash
# Woo
WOO_BASE_URL=...
WOO_CONSUMER_KEY=...
WOO_CONSUMER_SECRET=...

# Shopify Admin
SHOPIFY_ADMIN_ACCESS_TOKEN=...
SHOPIFY_LOCATION_ID=...
SHOPIFY_SHOP_DOMAIN=...
```

## Rollout

1. `mode=test` → run seed scripts → verify PG + Slack test alerts
2. Set channel creds → flip `mode=production` on isolated demo store
3. Rollback: `mode=test` immediately (stops writeback without stopping ingest)

See [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md), [CREDENTIALS.md](CREDENTIALS.md).
