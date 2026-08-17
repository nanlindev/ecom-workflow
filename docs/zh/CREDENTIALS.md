# 凭证配置

密钥放在 **`.env`**（sidecar）或 **platform-n8n `.env`**（n8n `$env`）。**禁止**写入 Postgres 的 `config_*` 表。

## 必需（sidecar）

### Postgres

```bash
ECOM_POSTGRES_USER=ecom
ECOM_POSTGRES_PASSWORD=change_me
ECOM_POSTGRES_DB=ecom
```

Compose 为 `ecom_python_ai` 组装 `DATABASE_URL`。

### DeepSeek（P2+）

```bash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-flash
```

### Langfuse

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://langfuse-web:3000
ENVIRONMENT=development
```

## Slack（n8n OAuth + 签名）

1. n8n → Credentials → Slack OAuth2 → 绑定 Slack 节点（JSON 占位符 `SLACK_CREDENTIAL_ID`）
2. Interactivity URL → `https://<n8n>/webhook/ecom-slack-interactions`
3. Signing Secret → platform-n8n `.env` 的 `SLACK_SIGNING_SECRET`
4. 频道 → `SLACK_ECOM_CHANNEL_ID`（platform-n8n `.env`）
5. 可选 `SLACK_ADMIN_USERS`（Slack 用户 ID，逗号分隔）

## Shopify Webhook HMAC（P1）

使用 App API secret（Dev Dashboard → 应用 → Credentials），**不是**旧版 Notifications 签名：

```bash
SHOPIFY_WEBHOOK_SECRET=<app_api_secret_key>
```

为空则跳过校验（仅本地演示）。见 [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md)。

## Shopify Admin Token（P3b 回写）

Custom App / CLI 应用的 offline token：

```bash
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
SHOPIFY_LOCATION_ID=gid_or_numeric_location_id
SHOPIFY_API_VERSION=2024-10
```

生产模式 + 门控通过时用于库存/价格 live writeback。

## WooCommerce（P3 / P3b）

Webhook 签名 + REST 回写：

```bash
WOO_WEBHOOK_SECRET=your_woo_webhook_secret
WOO_BASE_URL=https://your-woo-store.example
WOO_CONSUMER_KEY=ck_xxx
WOO_CONSUMER_SECRET=cs_xxx
```

与 Shopify 使用相同 `store_key` 实现多渠道 SoT。见 [WOO_SETUP.md](WOO_SETUP.md)。

## Resend（营销邮件）

在 **platform-n8n `.env`** 配置（n8n HTTP 节点读 `$env`）：

```bash
RESEND_API_KEY=re_xxx
RESEND_FROM_EMAIL=Ecom Demo <onboarding@resend.dev>
```

免费层在未验证域名前可能只能发到 Resend 账户邮箱。

## 安全

- 勿提交 `.env`
- 密钥不进 Postgres — 仅存放 `writeback_enabled` 等开关
- ngrok 切生产域名时轮换 webhook secret
