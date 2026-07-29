# Ecom sidecar deployment (CI/CD)

Deploy the ecom Python AI sidecar and dedicated `ecom_postgres`. Shared n8n runs in `platform-n8n`.

## Networks

| Network | Purpose |
|---------|---------|
| `n8n_platform` | n8n → `http://ecom_python_ai:8001/...`; n8n/sidecar → `ecom_postgres` |
| `proxy_network` | OTEL / Langfuse / Jaeger |

## Prerequisites

- `platform-n8n` running (`proxy_network` + `n8n_platform` exist)
- Project `.env` from `.env.example` (`ECOM_POSTGRES_*`, optional `DEEPSEEK_*` / `LANGFUSE_*`)

## Local

```bash
cd /path/to/ecom-workflow
cp .env.example .env
../platform-n8n/scripts/ensure-networks.sh
docker compose -f docker/compose.yml --env-file .env up -d --build
```

Health: http://localhost:8003/health  
Prompts: http://localhost:8003/prompts

On first start, Postgres runs `sql/init/` (extensions only). The sidecar then applies `sql/migrations/*.sql` idempotently (`schema_migrations` table). Re-running compose is safe.

## GitHub Actions CI/CD

Workflow: [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml)

| Item | Value |
|------|-------|
| Trigger | Push to `main` / `master`, or `workflow_dispatch` |
| Reusable | `nanlindev/platform-n8n/.github/workflows/reusable-deploy-python.yml@main` |
| Image | `ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest` |
| Server path | `/home/deploy/projects/ecom-workflow` |
| Compose | `docker/compose.yml` |
| Assert service | `ecom_python_ai` is `running` |

**Secrets** (shared with other projects): `SSH_HOST`, `SSH_PRIVATE_KEY`. `GITHUB_TOKEN` is used for GHCR push.

Pipeline outline:

```text
push main/master or workflow_dispatch
  → build-and-push python image → ghcr.io/nanlindev/ecom-workflow/python-ai-service
  → SSH deploy: ensure-networks → git pull → docker compose up -d
  → assert compose_service ecom_python_ai is running
```

`ecom_postgres` starts with the same compose file; schema evolves via sidecar migrations after each new image deploy. **n8n workflow JSON is not auto-imported** (manual import / sync, same as CRM).

## Production (manual)

Example path: `/home/deploy/projects/ecom-workflow` (sibling of `platform-n8n`; compose `include` uses that relative path).

**First clone** (if the folder only has a hand-made `.env`, back it up first):

```bash
cd /home/deploy/projects
mv ecom-workflow/.env /tmp/ecom-workflow.env
rmdir ecom-workflow 2>/dev/null || rm -rf ecom-workflow   # only when nearly empty
git clone git@github.com:nanlindev/ecom-workflow.git ecom-workflow
mv /tmp/ecom-workflow.env ecom-workflow/.env
```

Set `ENVIRONMENT=production` in `.env` (correct spelling). Never commit secrets.

```bash
../platform-n8n/scripts/ensure-networks.sh
docker pull ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest
docker compose -f docker/compose.yml --env-file .env up -d
```

Or build from source:

```bash
docker compose -f docker/compose.yml --env-file .env up -d --build
```

## Sidecar URLs (from n8n)

- `http://ecom_python_ai:8001/health`
- `http://ecom_python_ai:8001/prompts`
- (P2) `/competitors/parse`, `/competitors/targets`, `/pricing/recommend`, `/pricing/action`, `/insights/rfm`, `/insights/churn`, `/marketing/copy`, `/marketing/enroll`, `/marketing/advance`

Host mapping: **8003 → 8001**.

## Failure triage

| Symptom | Check |
|---------|--------|
| Actions: service not running | SSH, `.env` present on server, `docker compose logs ecom_python_ai` |
| `/health` → `database: error` | `ecom_postgres` healthy? `DATABASE_URL` / compose env? |
| Migration errors on boot | `docker compose logs ecom_python_ai`; inspect `schema_migrations` |
| OTEL / Langfuse missing | Sidecar on `proxy_network`; OBS stacks up; Langfuse keys |

## GHCR image

`ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest`
