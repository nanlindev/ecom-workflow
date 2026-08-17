# Shopify 配置

通过 Shopify CLI 应用声明式 Webhook → n8n **Ecom Platform Ingest**，路径 `/webhook/ecom-shopify`。

## 应用配置

主部署文件：`shopify-app/shopify.app.toml`。

关键字段：

```toml
[[webhooks.subscriptions]]
topics = [
  "products/create", "products/update",
  "inventory_levels/update",
  "orders/create", "orders/updated",
  "refunds/create",
]
uri = "https://<n8n 域名>/webhook/ecom-shopify"

[access_scopes]
scopes = "write_inventory,read_inventory,read_locations,read_orders,read_products,write_products"
```

P3b 回写需要 `write_inventory`、`write_products`、`read_locations`。

## 部署订阅

```bash
cd shopify-app
shopify auth login
shopify app config link   # 首次
# ngrok/域名变更时改 uri
shopify app deploy
```

在开发商店安装应用。删除 **设置 → 通知 → Webhook** 中重复 topic，避免双投递。

## HMAC 密钥

App Webhook 使用 **App API secret**（Dev Dashboard → 应用 → Credentials）：

```bash
SHOPIFY_WEBHOOK_SECRET=<app_api_secret_key>
```

改 `.env` 后重启 `ecom_python_ai`。空密钥跳过校验（仅本地）。

Sidecar 在 `/ingest/shopify` 校验。

## Admin Token + 库位（P3b 回写）

Custom App 或 CLI offline token：

```bash
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
SHOPIFY_LOCATION_ID=gid_or_numeric_location_id
SHOPIFY_API_VERSION=2024-10
```

库存更新需 `SHOPIFY_LOCATION_ID` 指定库位。

Live writeback 门控：`mode=production`、`writeback_enabled=true`、凭证齐全。见 [TEST_PRODUCTION.md](TEST_PRODUCTION.md)。

## n8n 检查

- [ ] **Ecom Platform Ingest** 已激活
- [ ] 生产 Webhook URL 与 TOML `uri` 一致
- [ ] Error Workflow → `Ecom Error Handler`

更多：[shopify-app/README.md](../../shopify-app/README.md)、[CREDENTIALS.md](CREDENTIALS.md)。
