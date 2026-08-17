# 运行示例

默认 `mode=test` 下的 sidecar 冒烟。基址：`http://localhost:8003`。

## 健康检查 + 配置

```bash
curl -s http://localhost:8003/health | jq
curl -s http://localhost:8003/prompts | jq
curl -s http://localhost:8003/config | jq
```

## Shopify 接入

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

## WooCommerce 接入

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

sync 调用使用 ingest 返回的 `store_id`。

## 库存同步

```bash
STORE_ID="<ingest-返回的-uuid>"
curl -s -X POST http://localhost:8003/inventory/sync \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $CORR" \
  -d "{\"store_id\": \"$STORE_ID\", \"sku\": \"sku-managed-1\"}" | jq
```

test 模式下期望 `has_drift=true`、`writeback_status=skipped_test_mode`。

## 运维摘要

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

## Seed 脚本（完整链路）

```bash
python3 scripts/seed_demo_scenario_a.py      # P1 库存 + 订单 + 退货
python3 scripts/seed_demo_scenario_b.py      # P2 定价 + 营销（需 store_id）
python3 scripts/seed_demo_scenario_p3.py     # P3 Woo + 摘要 + keepalive
```

## 核对 Postgres

```bash
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT sku, platform, available FROM inventory_levels LIMIT 10;"
```

可观测：[OBSERVABILITY.md](OBSERVABILITY.md)。生产回写：[TEST_PRODUCTION.md](TEST_PRODUCTION.md)。
