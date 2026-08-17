# 错误处理

## 两层模型

### 第一层：节点级（可预期失败）

外部 I/O 节点使用 **On Error → Continue (using error output)**，并接专用 Handler Code 节点。见 [ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md)。

| 失败点 | 典型 Handler | 降级 |
|--------|--------------|------|
| Sidecar HTTP（ingest/sync/pricing） | Handle * HTTP Error | 记 `*_error_message`，跳过或降级 Slack |
| Slack 通知 | Log Slack Error | 保留上游 payload |
| Resend / 营销发送 | Handle Send Error | `send_status=failed` |
| error_logs 写入 | Handle error_logs Write Failure | 继续告警门控 |

Handler 设置 `_metadata.processing_stage`，保留 `correlation_id`。

**规则：** 每个 `continueErrorOutput` 节点必须有 `connect_error(...)` — 悬空 error 口会吞掉失败且**不会**进全局 Error Handler。

### 第二层：全局（未捕获崩溃）

未处理异常 → **Ecom Error Handler**（Error Trigger）→ `POST /errors/log` → `error_logs` + 门控下可选 Slack。

节点级 Handler **不能**被全局工作流替代 — 尤其 Slack Webhook 已 Ack 后的 sidecar 失败。

## 导入后绑定 Error Workflow

JSON 里 `errorWorkflow` 只是**名称**；导入后通常**不会**自动绑定。

**Settings → Error Workflow → `Ecom Error Handler`**

所有主工作流均需设置（Ingest、Sync、Tracker、Returns、P2/P3 Cron、Slack Actions）。

## 重试默认

HTTP Request、Slack：重试 ON，最多 3 次，间隔 5000 ms（来自 `scripts/generate_workflows.py`）。

## 重新生成

```bash
python3 scripts/generate_workflows.py
python3 scripts/generate_workflows_p2.py
```

重新导入 JSON；重绑凭证与 Error Workflow。

节点对照表：[ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md)。
