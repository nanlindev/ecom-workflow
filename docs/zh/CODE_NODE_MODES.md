# Code 节点模式

`scripts/generate_workflows.py` 使用的 n8n Code v2 模式：

| 模式 | API | 适用场景 |
|------|-----|----------|
| `runOnceForAllItems` | `$input.all()`、`$('Node').all()` | 配置合并、聚合、1→N 展开 |
| `runOnceForEachItem` | `$input.item` | 单事件转换、错误 Handler |

## 必须用 `runOnceForAllItems`

| 模式 | 工作流 | 原因 |
|------|--------|------|
| 合并 sidecar 配置 | Summary、Keepalive、Pricing | 单一 config 对象 |
| 由完整 sync 响应组 Slack 文案 | Inventory Sync | 每次运行一条告警 |
| 聚合运维指标 | Daily / Weekly Summary | 一条摘要 item |

生成器常量：`BATCH_CODE_MODE = "runOnceForAllItems"`。

## 必须用 `runOnceForEachItem`

| 模式 | 工作流 | 原因 |
|------|--------|------|
| 所有 `Handle * Error` | 全部 | `$input.item.error` |
| 组装 webhook / sidecar body | Ingest、Sync | 单条 webhook |
| 解析 Slack 交互 | Slack Actions | 单次按钮 |
| 按 SKU 构造 POST | Ingest 分发 | 单平台事件 |

`code_node()` 默认：`runOnceForEachItem`。

## 常见坑

1. EachItem 里误用 `.item` 而应 `.all()` →  fan-out 错误。
2. Error Handler 必须 EachItem — 勿静默批量合并 error item。
3. UI 导出后请跑生成器，勿手改 mode。

见 [WORKFLOWS.md](WORKFLOWS.md)、`scripts/generate_workflows.py` 文件头注释。
