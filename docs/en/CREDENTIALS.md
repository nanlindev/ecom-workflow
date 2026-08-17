# Credentials configuration

Secrets live in **`.env`** (sidecar) or **platform-n8n `.env`** (n8n `$env`). **Never** store API keys in Postgres `config_*` tables.

## Required (sidecar)

### Postgres

```bash
ECOM_POSTGRES_USER=ecom
ECOM_POSTGRES_PASSWORD=change_me
ECOM_POSTGRES_DB=ecom
```

Compose builds `DATABASE_URL` for `ecom_python_ai`.

### DeepSeek (P2+)

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

## Slack (n8n OAuth + signing)

1. n8n → Credentials → Slack OAuth2 → assign to Slack nodes (`SLACK_CREDENTIAL_ID` placeholder)
2. Interactivity Request URL → `https://<n8n>/webhook/ecom-slack-interactions`
3. Signing Secret → `SLACK_SIGNING_SECRET` in platform-n8n `.env`
4. Channel → `SLACK_ECOM_CHANNEL_ID` in platform-n8n `.env`
5. Optional `SLACK_ADMIN_USERS` (comma-separated Slack user IDs)

## Shopify webhook HMAC (P1)

App API secret (Dev Dashboard → app → Credentials), **not** legacy Notifications secret:

```bash
SHOPIFY_WEBHOOK_SECRET=<app_api_secret_key>
```

Empty = skip verify (local demo only). See [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md).

## Shopify Admin token (P3b writeback)

Offline access token from Custom App / CLI app:

```bash
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
SHOPIFY_LOCATION_ID=gid_or_numeric_location_id
SHOPIFY_API_VERSION=2024-10
```

Used for live inventory + price writeback when `mode=production` and gates pass.

## WooCommerce (P3 / P3b)

Webhook signature + REST writeback:

```bash
WOO_WEBHOOK_SECRET=your_woo_webhook_secret
WOO_BASE_URL=https://your-woo-store.example
WOO_CONSUMER_KEY=ck_xxx
WOO_CONSUMER_SECRET=cs_xxx
```

Same `store_key` as Shopify for multi-channel SoT. See [WOO_SETUP.md](WOO_SETUP.md).

## Resend (marketing email)

Set in **platform-n8n `.env`** (n8n HTTP nodes read `$env`):

```bash
RESEND_API_KEY=re_xxx
RESEND_FROM_EMAIL=Ecom Demo <onboarding@resend.dev>
```

Free tier may only send to your Resend account email until domain verified.

## Security

- Never commit `.env`
- Never put secrets in Postgres — only flags like `writeback_enabled`
- Rotate webhook secrets when cutting over ngrok → production domain
