# E-commerce Intelligence Template

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Multi-store e-commerce ops automation on n8n: platform ingest → inventory sync → order tracking → returns → competitor pricing → customer insights → marketing — with a dedicated Postgres SoT, FastAPI sidecar, and Jaeger/Langfuse observability.

**Full stack:** n8n (shared `platform-n8n`) + `ecom_python_ai` + `ecom_postgres` + Slack + Resend + OBS.

**Chinese docs:** [docs/zh/](docs/zh/) · **Portfolio blurb:** [docs/SHOWCASE.md](docs/SHOWCASE.md)

## Status (P0–P3)

| Phase | Scope |
|-------|--------|
| **P0** | Sidecar + Postgres + health/migrations |
| **P1** | Ingest, Inventory Sync, Order Tracker, Returns, Error Handler — [DEMO_SCENARIO_A](docs/en/DEMO_SCENARIO_A.md) |
| **P2** | Competitor Crawl, Pricing Engine (+ Slack Approve/Reject), Customer Insights, Marketing Orchestrator, Slack Actions — [DEMO_SCENARIO_B](docs/en/DEMO_SCENARIO_B.md) |
| **P3** | Daily/Weekly Summary, Health Keepalive, Woo ingest |
| **P3b** | Live inventory/price writeback (Woo REST + Shopify Admin) when creds + `mode=production` |

Workflow JSON source of truth: `scripts/generate_workflows.py` (+ `generate_workflows_p2.py` / `generate_workflows_p3.py`).

## Quick start

1. Ensure sibling `platform-n8n` networks exist: `../platform-n8n/scripts/ensure-networks.sh`
2. `cp .env.example .env` and set `ECOM_POSTGRES_PASSWORD` (and optional LLM / Langfuse / channel keys)
3. `docker compose -f docker/compose.yml --env-file .env up -d --build`
4. Open http://localhost:8003/health — expect `"status":"healthy"` and `"database":"ok"`

Full install: [docs/en/INSTALL.md](docs/en/INSTALL.md)

## Project structure

| Path | Purpose |
|------|---------|
| `workflows/` | n8n JSON (import manually; generator in `scripts/`) |
| `docker/` | Compose: `ecom_python_ai` + `ecom_postgres` |
| `python-service/` | FastAPI sidecar |
| `sql/migrations/` | Idempotent schema (applied by sidecar) |
| `prompts/` | Versioned LLM prompts |
| `shopify-app/` | Declarative Shopify webhook app (`shopify.app.toml`) |
| `assets/` | Demo video script + competitor demo page |
| `docs/en/` · `docs/zh/` | Bilingual docs |
| `.github/workflows/deploy.yml` | CI/CD → GHCR + SSH compose |

## CI/CD

Push to `main`/`master` builds `ghcr.io/nanlindev/ecom-workflow/python-ai-service`. Details: [docs/en/DEPLOY.md](docs/en/DEPLOY.md)

## Observability

- **OTEL service:** `n8n-ecom-ai-service`
- **Langfuse tag:** `ecom-workflow`
- Host port: **8003** → container `8001`

## Documentation

| Doc | Topic |
|-----|--------|
| [SHOWCASE](docs/SHOWCASE.md) | Portfolio overview (EN) |
| [ARCHITECTURE](docs/en/ARCHITECTURE.md) · [zh](docs/zh/ARCHITECTURE.md) | System design |
| [INSTALL](docs/en/INSTALL.md) · [zh](docs/zh/INSTALL.md) | Setup + workflow import |
| [CREDENTIALS](docs/en/CREDENTIALS.md) · [zh](docs/zh/CREDENTIALS.md) | Slack, Shopify, Woo, Resend |
| [WORKFLOWS](docs/en/WORKFLOWS.md) · [zh](docs/zh/WORKFLOWS.md) | All 13 workflows |
| [DB_SETUP](docs/en/DB_SETUP.md) · [zh](docs/zh/DB_SETUP.md) | Postgres + config_* |
| [ERROR_HANDLING](docs/en/ERROR_HANDLING.md) · [zh](docs/zh/ERROR_HANDLING.md) | Two-tier model |
| [ERROR_HANDLING_NODES](docs/en/ERROR_HANDLING_NODES.md) · [zh](docs/zh/ERROR_HANDLING_NODES.md) | Per-node wiring |
| [CODE_NODE_MODES](docs/en/CODE_NODE_MODES.md) · [zh](docs/zh/CODE_NODE_MODES.md) | Code node rules |
| [TEST_PRODUCTION](docs/en/TEST_PRODUCTION.md) · [zh](docs/zh/TEST_PRODUCTION.md) | Gates + writeback_status |
| [OBSERVABILITY](docs/en/OBSERVABILITY.md) · [zh](docs/zh/OBSERVABILITY.md) | Jaeger, Langfuse, NO_PROXY |
| [PROMPTS](docs/en/PROMPTS.md) · [zh](docs/zh/PROMPTS.md) | prompts/ + /prompts |
| [CONFIG_REFERENCE](docs/en/CONFIG_REFERENCE.md) · [zh](docs/zh/CONFIG_REFERENCE.md) | config_* flags |
| [SHOPIFY_SETUP](docs/en/SHOPIFY_SETUP.md) · [zh](docs/zh/SHOPIFY_SETUP.md) | App + P3b Admin |
| [WOO_SETUP](docs/en/WOO_SETUP.md) · [zh](docs/zh/WOO_SETUP.md) | Webhooks + REST writeback |
| [RUN_EXAMPLE](docs/en/RUN_EXAMPLE.md) · [zh](docs/zh/RUN_EXAMPLE.md) | curl + seeds |
| [DEMO_RUNBOOK](docs/en/DEMO_RUNBOOK.md) · [zh](docs/zh/DEMO_RUNBOOK.md) | Scenarios A/B/C |
| [DEPLOY](docs/en/DEPLOY.md) · [zh](docs/zh/DEPLOY.md) | CI/CD + triage |
