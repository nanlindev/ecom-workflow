# Database setup

Dedicated **`ecom_postgres`** — separate from n8n's Postgres. Business SoT for inventory, orders, pricing, and config flags (no secrets).

## Layout

| Path | Role |
|------|------|
| `sql/init/` | First-volume extensions only |
| `sql/migrations/*.sql` | Idempotent schema + seeds |
| Sidecar boot | Applies pending migrations → `schema_migrations` table |

Re-running `docker compose up` is safe.

## Start

```bash
docker compose -f docker/compose.yml --env-file .env up -d
curl http://localhost:8003/health   # expect "database":"ok"
```

## config_* tables (no secrets)

| Table | Examples |
|-------|----------|
| `config_main` | `mode`, `project_tag`, `demo_woo_store_key` |
| `config_inventory` | `master_channel`, `slave_channels`, `writeback_enabled`, `writeback_align_sot` |
| `config_pricing` | `enabled`, `min_margin_pct`, `price_writeback_channels`, `demo_pricing_skus` |
| `config_marketing` | `enabled`, `abandon_cart_enabled`, `send_email_in_test` |
| `config_notifications` | `slack_enabled`, `daily_summary_enabled`, `keepalive_alert_enabled` |

Full keys: [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md).

## Core business tables

`stores`, `products`, `inventory_levels`, `orders`, `returns`, `pricing_recommendations`, `competitor_snapshots`, `customers`, `marketing_enrollments`, `audit_logs`, `error_logs`, `prompt_registry`.

## Inspect

```bash
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT key, value FROM config_main;"
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT version FROM schema_migrations ORDER BY version;"
```

## Change config at runtime

Update rows in `config_*` — workflows re-read on each run (no restart).

```sql
UPDATE config_main SET value = 'production' WHERE key = 'mode';
```

## Migration failures

Check `docker compose logs ecom_python_ai`. Fix SQL, rebuild image, restart — migrations are idempotent.

See [DEPLOY.md](DEPLOY.md), [TEST_PRODUCTION.md](TEST_PRODUCTION.md).
