# Installation Guide

## Prerequisites

- Docker Compose v2.20+
- Sibling repo **platform-n8n** (shared n8n + Docker networks)
- External networks `proxy_network` and `n8n_platform`
- DeepSeek API key (P2+ LLM endpoints)
- Optional: Slack app, Shopify app, Woo store, Resend (see setup docs)

## 1. Start platform-n8n

```bash
cd ../platform-n8n
cp .env.example .env
./scripts/ensure-networks.sh
docker compose -f docker/compose.yml up -d
```

n8n UI: http://localhost:5678

## 2. Configure ecom-workflow

```bash
cd ../ecom-workflow
cp .env.example .env
# ECOM_POSTGRES_PASSWORD, DEEPSEEK_*, optional SHOPIFY_* / WOO_* / SLACK_*
```

See [CREDENTIALS.md](CREDENTIALS.md), [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md), [WOO_SETUP.md](WOO_SETUP.md).

## 3. Start sidecar + Postgres

```bash
../platform-n8n/scripts/ensure-networks.sh
docker compose -f docker/compose.yml --env-file .env up -d --build
curl http://localhost:8003/health
curl http://localhost:8003/prompts
```

Migrations run automatically on sidecar boot. Details: [DB_SETUP.md](DB_SETUP.md), [DEPLOY.md](DEPLOY.md).

## 4. Import n8n workflows

Import from `workflows/` (Settings → Import from File), preferably:

1. `Ecom Error Handler.json`
2. `Ecom Platform Ingest.json`
3. `Ecom Inventory Sync.json`
4. `Ecom Order Tracker.json`
5. `Ecom Returns Automation.json`
6. P2: Competitor Price Crawl, Pricing Engine, Customer Insights, Marketing Orchestrator, Slack Actions
7. P3: Daily Summary, Weekly Summary, Health Keepalive

**Source of truth for JSON:** `scripts/generate_workflows.py` (+ `generate_workflows_p2.py`). Regenerate after edits:

```bash
python3 scripts/generate_workflows.py
python3 scripts/generate_workflows_p2.py   # if P2/P3 generator split
```

### Post-import checklist

- [ ] Re-bind **Slack** credential (`SLACK_CREDENTIAL_ID` placeholders in JSON)
- [ ] **Settings → Error Workflow → `Ecom Error Handler`** on every main workflow (import does **not** auto-bind)
- [ ] Verify error wiring: [ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md)
- [ ] Activate: Platform Ingest, Inventory Sync (Cron), Slack Actions, Daily/Weekly Summary, Health Keepalive
- [ ] PG `config_main.mode=test` (default after migrations)

Sidecar URLs in workflows: `http://ecom_python_ai:8001/...`

## 5. Channel setup

- Shopify: [SHOPIFY_SETUP.md](SHOPIFY_SETUP.md) → `/webhook/ecom-shopify`
- Woo: [WOO_SETUP.md](WOO_SETUP.md) → `/webhook/ecom-woo`
- Slack interactivity: `/webhook/ecom-slack-interactions`

## 6. Test run

```bash
python3 scripts/seed_demo_scenario_a.py
```

Walkthrough: [RUN_EXAMPLE.md](RUN_EXAMPLE.md), [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

## 7. Production

Set `config_main.mode=production` in Postgres (not only `.env`). See [TEST_PRODUCTION.md](TEST_PRODUCTION.md).

## Troubleshooting

- **Sidecar won't start:** check `ECOM_POSTGRES_*`, `DATABASE_URL` in compose logs
- **No OTEL:** both services on `proxy_network`; see [OBSERVABILITY.md](OBSERVABILITY.md)
- **Webhook silent:** workflow Active? production webhook URL registered?
