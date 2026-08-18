# WooCommerce 配置

Woo Webhook → n8n `/webhook/ecom-woo` → sidecar `/ingest/woocommerce`。REST 密钥用于 P3b 库存/价格 live writeback。

## 注册 Webhook

Woo **设置 → 高级 → Webhook**：

| 主题 | 投递 URL |
|------|----------|
| 产品创建/更新 | `https://<n8n>/webhook/ecom-woo` |
| 订单创建/更新 | 同上 |
| （退款） | **无需单独 refund topic**：订 `order.updated`；sidecar 见 `status=refunded` / `refunds[]` 则 `event_type=return` 并 dispatch Returns |

核心 Woo webhook 主题只有 `order.created|updated|deleted`。payload 与 REST **Order** 同形（不是 `/orders/<id>/refunds` 资源）。退款明细可在订单体 `refunds[]`，需要完整行项目时再调 REST Order Refunds。

设置 **Secret** → `.env`：

```bash
WOO_WEBHOOK_SECRET=your_woo_webhook_secret
```

Sidecar 校验 HMAC（本地 curl 可临时 `skip_verify: true`）。

## REST API 密钥（P3b 回写）

Woo **设置 → 高级 → REST API** → 读写密钥：

```bash
WOO_BASE_URL=https://your-woo-store.example
WOO_CONSUMER_KEY=ck_xxx
WOO_CONSUMER_SECRET=cs_xxx
```

`python-service/channels/woocommerce.py` 在门控通过时更新库存/价格。

## 多渠道 SoT

与 Shopify 使用 **相同 `store_key`**（种子默认 `demo-shopify`），合并到同一店铺：

- ingest body/头可传 `store_key`
- 或配置 `config_main.demo_woo_store_key`

`master_channel`（`shopify`）冲突时优先；Woo 通常在 `slave_channels` 中。商品/库存 webhook 仍写入 Woo `inventory_levels`；Shopify 为 master 时 **不会** dispatch Inventory Sync（避免回写回声）。

## n8n 检查

- [ ] **Ecom Platform Ingest** 已激活（Woo 路径）
- [ ] 已绑定 Error Workflow
- [ ] 验证凭证前保持 `mode=test`

## 冒烟

```bash
python3 scripts/seed_demo_scenario_p3.py
```

期望 Woo 产品接入 + inventory sync 漂移及 `writeback_status`。

见 [CREDENTIALS.md](CREDENTIALS.md)、[TEST_PRODUCTION.md](TEST_PRODUCTION.md)、[RUN_EXAMPLE.md](RUN_EXAMPLE.md)。
