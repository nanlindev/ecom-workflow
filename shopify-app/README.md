# Shopify app (declarative webhooks → n8n)

Modern Shopify flow: declare webhooks in `shopify.app.toml`, then let Shopify CLI
create subscriptions on deploy (`shopify app deploy`). No manual Admin
“Add webhook” rows and no hand-written `webhookSubscriptionCreate` mutations.

## Prerequisites

- Node.js 20+
- Shopify Partner account + development store (`nans-automation-store` or similar)
- [Shopify CLI](https://shopify.dev/docs/api/shopify-cli) (`npm i -g @shopify/cli @shopify/theme` or current install docs)
- n8n reachable at a **stable HTTPS** URL (`WEBHOOK_URL`), workflow **Ecom Platform Ingest** active

## One-time setup

```bash
cd shopify-app
shopify auth login
shopify app init
# Or: create app in Dev Dashboard, then:
# shopify app config link
```

Replace `client_id` in `shopify.app.toml` with the linked app’s Client ID.

Set scopes / webhook `uri` (already pointed at `/webhook/ecom-shopify`).

Install the app on the development store when CLI prompts (or Dev Dashboard → Install).

## Deploy webhook subscriptions

```bash
cd shopify-app
# edit uri if ngrok host changed
shopify app deploy
```

For local `app dev` against the chosen dev store, TOML webhooks sync automatically while the session runs; use `deploy` to persist a released app version.

## HMAC secret (important)

App-delivered webhooks sign with the **App API secret key** (Dev Dashboard → app → Credentials), **not** the legacy Notifications webhook signing secret.

Put that value in `ecom-workflow/.env`:

```bash
SHOPIFY_WEBHOOK_SECRET=<app_api_secret_key>
```

Recreate `ecom_python_ai` so the sidecar picks it up.

## Avoid double delivery

After app webhooks work, **delete** the same topics under store **Settings → Notifications → Webhooks**, or you will get duplicate Slack/ingest events.

## Ngrok / server cutover

When `WEBHOOK_URL` changes (new ngrok host or production domain):

1. Update `uri` in `shopify.app.toml` (and `redirect_urls` if needed)
2. `shopify app deploy`
3. Keep `SHOPIFY_WEBHOOK_SECRET` (app secret usually unchanged)

## Optional later

- Add Admin API calls for production writeback using the app’s offline token (`SHOPIFY_ADMIN_ACCESS_TOKEN` + `SHOPIFY_LOCATION_ID` in ecom `.env`). Inventory/price writeback is implemented in the sidecar (`channels/shopify_admin.py`) when `mode=production` and gates allow.
- For App Store distribution, add mandatory `compliance_topics` subscriptions
