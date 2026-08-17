# Run Example

Sidecar smoke tests with `mode=test` (default). Base URL: `http://localhost:8003`.

## Health + config

```bash
curl -s http://localhost:8003/health | jq
curl -s http://localhost:8003/prompts | jq
curl -s http://localhost:8003/config | jq
```

## Shopify ingest

```bash
CORR=$(uuidgen)
curl -s -X POST http://localhost:8003/ingest/shopify \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $CORR" \
  -d '{
    "raw_body": {"id": 9001, "sku": "sku-managed-1", "inventory_quantity": 42},
    "headers": {"x-shopify-topic": "products/update"},
    "store_key": "demo-shopify",
    "skip_verify": true
  }' | jq
```

## WooCommerce ingest

```bash
curl -s -X POST http://localhost:8003/ingest/woocommerce \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: '"$CORR"'" \
  -d '{
    "raw_body": {"id": 88001, "sku": "sku-managed-1", "stock_quantity": 37, "_topic": "product.updated"},
    "headers": {"x-wc-webhook-topic": "product.updated"},
    "store_key": "demo-shopify",
    "skip_verify": true
  }' | jq
```

Use `store_id` from ingest response in sync call.

## Inventory sync

```bash
STORE_ID="<uuid-from-ingest>"
curl -s -X POST http://localhost:8003/inventory/sync \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $CORR" \
  -d "{\"store_id\": \"$STORE_ID\", \"sku\": \"sku-managed-1\"}" | jq
```

Expect `has_drift=true`, `writeback_status=skipped_test_mode` in test mode.

## Ops summary

```bash
curl -s -X POST http://localhost:8003/ops/summary \
  -H "Content-Type: application/json" \
  -d "{\"period\": \"daily\", \"store_id\": \"$STORE_ID\", \"correlation_id\": \"$CORR\"}" | jq
```

## Keepalive

```bash
curl -s -X POST http://localhost:8003/ops/keepalive \
  -H "Content-Type: application/json" \
  -d "{\"correlation_id\": \"$CORR\", \"ping_channels\": true}" | jq
```

## Seed scripts (full paths)

```bash
python3 scripts/seed_demo_scenario_a.py      # P1 inventory + orders + returns
python3 scripts/seed_demo_scenario_b.py      # P2 pricing + marketing (needs store_id)
python3 scripts/seed_demo_scenario_p3.py     # P3 Woo + ops summary + keepalive
```

## Verify Postgres

```bash
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT sku, platform, available FROM inventory_levels LIMIT 10;"
```

Observability: [OBSERVABILITY.md](OBSERVABILITY.md). Production writeback: [TEST_PRODUCTION.md](TEST_PRODUCTION.md).
