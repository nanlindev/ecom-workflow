# 节点错误处理对照

导入后在 UI 核对。生成源：`scripts/generate_workflows.py`。

## 全局约定

| 设置 | 适用节点 |
|------|----------|
| **Stop Workflow** | Code（逻辑）、IF、Merge、Execute Workflow、Set |
| **Continue + error 口** | HTTP Request（sidecar）、Slack、Resend HTTP |
| **重试 3× / 5s** | HTTP Request、Slack |
| **Error Workflow** | 各主工作流重绑 `Ecom Error Handler` |

凭证占位符：`SLACK_CREDENTIAL_ID` — 导入后重绑。

## 必须接 `connect_error`

| 工作流 | 节点 |
|--------|------|
| **Platform Ingest** | ingest HTTP → Handle Ingest Error |
| **Inventory Sync** | `/inventory/sync` HTTP；Slack → Log Slack Error |
| **Order Tracker** | `/orders/track` HTTP → handler |
| **Returns Automation** | `/returns/decide` HTTP → handler |
| **Competitor Price Crawl** | 抓取 + `/competitors/parse` HTTP |
| **Pricing Engine** | `/pricing/recommend` HTTP；Slack notify |
| **Customer Insights** | insight HTTP 节点 |
| **Marketing Orchestrator** | copy/enroll/advance；Resend 发送 |
| **Slack Actions** | `/pricing/action` HTTP；Slack 响应 |
| **Daily / Weekly Summary** | `/ops/summary` HTTP；Slack |
| **Health Keepalive** | `/ops/keepalive` HTTP；Slack 告警 |
| **Error Handler** | `/errors/log` HTTP → Handle error_logs Write Failure |

## 输出口

- **main[0]**：成功
- **main[1]**：错误 → Handler → 汇合或 End

## 验收抽查

| 场景 | 期望 |
|------|------|
| sync 时 sidecar 不可用 | Handler 带 `inventory_error_message` |
| 漂移后 Slack 失败 | 错误被记录；漂移数据保留 |
| Code 未捕获异常 | 全局 Error Handler → `error_logs` 行 |

重新生成：`python3 scripts/generate_workflows.py`。总览：[ERROR_HANDLING.md](ERROR_HANDLING.md)。
