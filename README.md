# E-commerce Intelligence Template

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Multi-store e-commerce ops automation on n8n: platform ingest → inventory sync → order tracking → returns → competitor pricing → customer insights → marketing — with a dedicated Postgres SoT, FastAPI sidecar, and Jaeger/Langfuse observability.

**Full stack:** n8n (shared `platform-n8n`) + `ecom_python_ai` + `ecom_postgres` + Slack + SendGrid + OBS.

**Chinese docs:** [docs/zh/](docs/zh/)

## Status (P0 + P1 + P2)

- **P1 trust path:** Ingest, Inventory Sync, Order Tracker, Returns, Error Handler — [DEMO_SCENARIO_A](docs/en/DEMO_SCENARIO_A.md)
- **P2 intel path:** Competitor Crawl, Pricing Engine (+ Slack Approve/Reject), Customer Insights, Marketing Orchestrator, Slack Actions — [DEMO_SCENARIO_B](docs/en/DEMO_SCENARIO_B.md) · `python3 scripts/seed_demo_scenario_b.py`

## Quick start

1. Ensure sibling `platform-n8n` networks exist: `../platform-n8n/scripts/ensure-networks.sh`
2. `cp .env.example .env` and set `ECOM_POSTGRES_PASSWORD` (and optional LLM / Langfuse keys)
3. `docker compose -f docker/compose.yml --env-file .env up -d --build`
4. Open http://localhost:8003/health — expect `"status":"healthy"` and `"database":"ok"`

## Project structure

| Path | Purpose |
|------|---------|
| `workflows/` | n8n JSON (imported manually; generator in `scripts/`) |
| `docker/` | Compose: `ecom_python_ai` + `ecom_postgres` |
| `python-service/` | FastAPI: `/health`, `/ingest/shopify`, `/inventory/sync`, `/orders/track`, `/returns/decide`, … |
| `sql/init/` | First-volume Postgres extensions |
| `sql/migrations/` | Idempotent schema (applied by sidecar) |
| `prompts/` | Versioned LLM prompts |
| `schemas/` | Order / product / inventory JSON Schema |
| `docs/en/` · `docs/zh/` | Bilingual docs |
| `.github/workflows/deploy.yml` | CI/CD → GHCR + SSH compose |

## CI/CD

Push to `main`/`master` (or `workflow_dispatch`) builds `ghcr.io/nanlindev/ecom-workflow/python-ai-service` and deploys via the shared `platform-n8n` reusable workflow. Details: [docs/en/DEPLOY.md](docs/en/DEPLOY.md) · [docs/zh/DEPLOY.md](docs/zh/DEPLOY.md).

## Observability

- **OTEL service:** `n8n-ecom-ai-service`
- **Langfuse tag:** `ecom-workflow`
- Host port: **8003** → container `8001`

## Documentation

| Doc | Topic |
|-----|--------|
| [DEPLOY (en)](docs/en/DEPLOY.md) | Local + GitHub Actions + triage |
| [DEPLOY (zh)](docs/zh/DEPLOY.md) | 本地 + Actions + 排查 |
