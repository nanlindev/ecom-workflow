# Ecom sidecar 部署（含 CI/CD）

部署 ecom Python AI sidecar 与独立业务库 `ecom_postgres`。共享 n8n 运行在 `platform-n8n`。

## 网络

| 网络 | 用途 |
|------|------|
| `n8n_platform` | n8n → `http://ecom_python_ai:8001/...`；n8n/sidecar → `ecom_postgres` |
| `proxy_network` | OTEL / Langfuse / Jaeger |

## 前置条件

- `platform-n8n` 已运行（`proxy_network` + `n8n_platform` 已存在）
- 项目 `.env` 由 `.env.example` 复制（`ECOM_POSTGRES_*`，可选 `DEEPSEEK_*` / `LANGFUSE_*`）

## 本地

```bash
cd /path/to/ecom-workflow
cp .env.example .env
../platform-n8n/scripts/ensure-networks.sh
docker compose -f docker/compose.yml --env-file .env up -d --build
```

健康检查：http://localhost:8003/health  
Prompts：http://localhost:8003/prompts

首次启动时 Postgres 执行 `sql/init/`（仅扩展）。Sidecar 再幂等执行 `sql/migrations/*.sql`（`schema_migrations` 表）。重复 `compose up` 安全。

## GitHub Actions CI/CD

工作流：[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml)

| 项 | 值 |
|----|-----|
| 触发 | push `main` / `master`，或 `workflow_dispatch` |
| 复用 | `nanlindev/platform-n8n/.github/workflows/reusable-deploy-python.yml@main` |
| 镜像 | `ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest` |
| 服务器路径 | `/home/deploy/projects/ecom-workflow` |
| Compose | `docker/compose.yml` |
| 断言服务 | `ecom_python_ai` 为 `running` |

**Secrets**（与其它项目共用）：`SSH_HOST`、`SSH_PRIVATE_KEY`。GHCR 使用 `GITHUB_TOKEN`。

流水线：

```text
push main/master 或 workflow_dispatch
  → build-and-push python 镜像 → ghcr.io/nanlindev/ecom-workflow/python-ai-service
  → SSH 部署：ensure-networks → git pull → docker compose up -d
  → 断言 compose_service ecom_python_ai 为 running
```

`ecom_postgres` 与 sidecar 同属一份 compose；每次新镜像部署后由 sidecar 启动迁移自动迁库。**n8n 工作流 JSON 不会由 CI 自动导入**（与 CRM 相同，文档化手动导入/同步）。

## 生产（手动）

示例路径：`/home/deploy/projects/ecom-workflow`（与 `platform-n8n` 同级，compose `include` 依赖相对路径）。

**首次**（目录里若只有手建 `.env`，先备份再 clone）：

```bash
cd /home/deploy/projects
mv ecom-workflow/.env /tmp/ecom-workflow.env
rmdir ecom-workflow 2>/dev/null || rm -rf ecom-workflow   # 仅当目录几乎为空时
git clone git@github.com:nanlindev/ecom-workflow.git ecom-workflow
mv /tmp/ecom-workflow.env ecom-workflow/.env
```

`.env` 中 `ENVIRONMENT` 必须为 **`production`**（注意拼写，不要写成 `prodution`）。Postgres / Shopify / DeepSeek 等密钥只放服务器 `.env`，勿提交仓库。

```bash
../platform-n8n/scripts/ensure-networks.sh
docker pull ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest
docker compose -f docker/compose.yml --env-file .env up -d
```

或从源码构建：

```bash
docker compose -f docker/compose.yml --env-file .env up -d --build
```

## Sidecar URL（从 n8n 调用）

- `http://ecom_python_ai:8001/health`
- `http://ecom_python_ai:8001/prompts`
- （P2）`/competitors/parse`、`/competitors/targets`、`/pricing/recommend`、`/pricing/action`、`/insights/rfm`、`/insights/churn`、`/marketing/copy`、`/marketing/enroll`、`/marketing/advance`
- （P3）`/ops/summary`、`/ops/keepalive`；Woo 接入 `/ingest/woocommerce`

**P3b live writeback**（可选 `.env`）：`WOO_*`、`SHOPIFY_ADMIN_ACCESS_TOKEN`、`SHOPIFY_LOCATION_ID`。门控：Postgres `config_main.mode=production` + `writeback_enabled`。见 [TEST_PRODUCTION.md](TEST_PRODUCTION.md)。

宿主机映射：**8003 → 8001**。

## 失败排查

| 现象 | 检查 |
|------|------|
| Actions：服务未 running | SSH、服务器上 `.env` 是否存在、`docker compose logs ecom_python_ai` |
| `/health` → `database: error` | `ecom_postgres` 是否 healthy？`DATABASE_URL` / compose 环境变量？ |
| 启动 migration 失败 | `docker compose logs ecom_python_ai`；查看 `schema_migrations` |
| 无 OTEL / Langfuse | Sidecar 是否在 `proxy_network`；OBS 是否起来；Langfuse keys |

## GHCR 镜像

`ghcr.io/nanlindev/ecom-workflow/python-ai-service:latest`
