# 安装指南

## 前置条件

- Docker Compose v2.20+
- 同级仓库 **platform-n8n**（共享 n8n + Docker 网络）
- 外部网络 `proxy_network`、`n8n_platform`
- DeepSeek API Key（P2+ LLM）
- 可选：Slack、Shopify App、Woo 店铺、Resend（见各 setup 文档）

## 1. 启动 platform-n8n

```bash
cd ../platform-n8n
cp .env.example .env
./scripts/ensure-networks.sh
docker compose -f docker/compose.yml up -d
```

n8n：http://localhost:5678

## 2. 配置 ecom-workflow

```bash
cd ../ecom-workflow
cp .env.example .env
# ECOM_POSTGRES_PASSWORD、DEEPSEEK_*，可选 SHOPIFY_* / WOO_* / SLACK_*
```

见 [CREDENTIALS.md](CREDENTIALS.md)、[SHOPIFY_SETUP.md](SHOPIFY_SETUP.md)、[WOO_SETUP.md](WOO_SETUP.md)。

## 3. 启动 sidecar + Postgres

```bash
../platform-n8n/scripts/ensure-networks.sh
docker compose -f docker/compose.yml --env-file .env up -d --build
curl http://localhost:8003/health
curl http://localhost:8003/prompts
```

Sidecar 启动时自动跑迁移。详见 [DB_SETUP.md](DB_SETUP.md)、[DEPLOY.md](DEPLOY.md)。

## 4. 导入 n8n 工作流

从 `workflows/` 导入（Settings → Import from File），建议顺序：

1. `Ecom Error Handler.json`
2. `Ecom Platform Ingest.json`
3. `Ecom Inventory Sync.json`
4. `Ecom Order Tracker.json`
5. `Ecom Returns Automation.json`
6. P2：Competitor Price Crawl、Pricing Engine、Customer Insights、Marketing Orchestrator、Slack Actions
7. P3：Daily Summary、Weekly Summary、Health Keepalive

**JSON 生成源：** `scripts/generate_workflows.py`（及 `generate_workflows_p2.py`）。改生成器后：

```bash
python3 scripts/generate_workflows.py
python3 scripts/generate_workflows_p2.py
```

### 导入后检查

- [ ] 重新绑定 **Slack** 凭证（JSON 中为 `SLACK_CREDENTIAL_ID` 占位符）
- [ ] 各主工作流 **Settings → Error Workflow → `Ecom Error Handler`**（导入**不会**自动绑定）
- [ ] 核对 error 连线：[ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md)
- [ ] 激活：Platform Ingest、Inventory Sync（Cron）、Slack Actions、Daily/Weekly Summary、Health Keepalive
- [ ] PG 中 `config_main.mode=test`（迁移默认）

工作流内 sidecar：`http://ecom_python_ai:8001/...`

## 5. 渠道配置

- Shopify：[SHOPIFY_SETUP.md](SHOPIFY_SETUP.md) → `/webhook/ecom-shopify`
- Woo：[WOO_SETUP.md](WOO_SETUP.md) → `/webhook/ecom-woo`
- Slack 交互：`/webhook/ecom-slack-interactions`

## 6. 试跑

```bash
python3 scripts/seed_demo_scenario_a.py
```

演练：[RUN_EXAMPLE.md](RUN_EXAMPLE.md)、[DEMO_RUNBOOK.md](DEMO_RUNBOOK.md)。

## 7. 生产

在 Postgres 设置 `config_main.mode=production`（不仅改 `.env`）。见 [TEST_PRODUCTION.md](TEST_PRODUCTION.md)。

## 排查

- **Sidecar 起不来：** 查 `ECOM_POSTGRES_*`、compose 日志
- **无 OTEL：** 服务是否在 `proxy_network`；见 [OBSERVABILITY.md](OBSERVABILITY.md)
- **Webhook 无反应：** 工作流是否 Active？Webhook URL 是否已注册？
