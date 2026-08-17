# DEMO Scenario A (P1 trust path)

Manual checklist after importing workflows and starting compose.

## Prerequisites

```bash
cd /path/to/ecom-workflow
cp -n .env.example .env
../platform-n8n/scripts/ensure-networks.sh
docker compose -f docker/compose.yml --env-file .env up -d --build
curl -s http://localhost:8003/health
```

Import from `workflows/` (order: Error Handler first, then others). Re-bind **Error Workflow** → `Ecom Error Handler` and Slack credential placeholders.

## Seed

```bash
python3 scripts/seed_demo_scenario_a.py
```

Expect:

- Inventory upsert for `sku-managed-1` available=42 on Shopify
- Sync reports `has_drift=true`, `writeback_status=skipped_test_mode` (mode=test)
- Order `5001` status `paid` in PG
- Return `R-9001` → `manual_review` (amount 120 > auto-approve 50)

## Verify in Postgres

```bash
docker compose -f docker/compose.yml --env-file .env exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT sku, platform, available FROM inventory_levels;"
docker compose -f docker/compose.yml --env-file .env exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT external_order_id, status, customer_email FROM orders;"
docker compose -f docker/compose.yml --env-file .env exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT external_return_id, decision, status, amount FROM returns;"
```

## Acceptance

- [x] Test-store inventory change visible in PG
- [x] Order status visible in PG
- [x] test mode: no production writeback (`skipped_test_mode`)
