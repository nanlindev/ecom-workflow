# 工作流

`workflows/` 中共 13 条 n8n 工作流。导入顺序见 [INSTALL.md](INSTALL.md)。由 `scripts/generate_workflows.py` 生成（唯一源）。

## 目录

| 工作流 | 触发 | 用途 |
|--------|------|------|
| **Ecom Error Handler** | Error Trigger | 全局兜底：`error_logs` + 可选 Slack 告警 |
| **Ecom Platform Ingest** | Webhook `ecom-shopify` / `ecom-woo` | HMAC 校验 → sidecar 接入 → 分发 sync/track/returns |
| **Ecom Inventory Sync** | Cron + Execute Workflow | 合并 master/slave 库存；漂移 Slack；P3b live writeback |
| **Ecom Order Tracker** | Execute Workflow | 平台 payload 写入/更新订单状态 |
| **Ecom Returns Automation** | Execute Workflow | 退货规则 + manual_review 路径 |
| **Ecom Competitor Price Crawl** | Cron | 抓取竞品 URL → `/competitors/parse` → 快照 |
| **Ecom Pricing Engine** | Cron | 定价建议 → 有差异时 Slack 审批 |
| **Ecom Customer Insights** | Cron | RFM + 流失评分 |
| **Ecom Marketing Orchestrator** | Cron | 营销序列 enroll/advance；Resend 发送（门控） |
| **Ecom Slack Actions** | Webhook `ecom-slack-interactions` | 定价 Approve/Reject → `/pricing/action` |
| **Ecom Daily Summary** | 每日定时 | `/ops/summary` 日报 → 门控后发 Slack |
| **Ecom Weekly Summary** | 每周定时 | 周报 → 门控后发 Slack |
| **Ecom Health Keepalive** | 定时 | `/ops/keepalive` 测 PG/渠道；失败告警 |

## P1 链路

```text
Platform Ingest → /ingest/shopify|woocommerce
  → Execute Inventory Sync / Order Tracker / Returns
Inventory Sync → POST /inventory/sync → 漂移 Slack + writeback
```

## P2 链路

```text
Competitor Crawl → Pricing Engine → Slack Actions → /pricing/action
Customer Insights + Marketing Orchestrator（并行 Cron）
```

## P3 运维

Daily / Weekly Summary、Health Keepalive 调用 `/ops/summary`、`/ops/keepalive`。

## Sidecar URL（n8n 内）

```text
http://ecom_python_ai:8001/ingest/shopify
http://ecom_python_ai:8001/ingest/woocommerce
http://ecom_python_ai:8001/inventory/sync
http://ecom_python_ai:8001/orders/track
http://ecom_python_ai:8001/returns/decide
http://ecom_python_ai:8001/pricing/recommend
http://ecom_python_ai:8001/pricing/action
http://ecom_python_ai:8001/ops/summary
http://ecom_python_ai:8001/ops/keepalive
http://ecom_python_ai:8001/errors/log
```

门控说明：[TEST_PRODUCTION.md](TEST_PRODUCTION.md)、[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)。
