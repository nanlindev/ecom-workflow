# 可观测性

n8n 执行与 LLM 调用的端到端追踪。

## 栈

| 组件 | 作用 |
|------|------|
| OpenTelemetry Collector | 接收 n8n + sidecar 的 OTLP |
| Jaeger | Span UI（`n8n-platform`、`n8n-ecom-ai-service`） |
| Langfuse | LLM 追踪，标签 **`ecom-workflow`** |

OBS 部署在 `proxy_network`（同级仓库：`otel-collector-stack`、`jaeger-stack`、`langfuse-stack`）。

## 环境检查

**platform-n8n**

- OTEL → `http://otel-collector:4318`
- 建议 `N8N_OTEL_TRACES_INJECT_OUTBOUND=true`

**ecom sidecar**（`.env`）

- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
- `OTEL_SERVICE_NAME=n8n-ecom-ai-service`
- `LANGFUSE_*` + `LANGFUSE_HOST`

**NO_PROXY** 须包含内部 Docker 主机名：

```text
ecom_python_ai,ecom_postgres,otel-collector,langfuse-web,jaeger,crm_python_ai
```

见 `.env.example` — 避免 sidecar→Postgres / OTEL 走外部 HTTP 代理。

## 关联 ID

| ID | 位置 | 用途 |
|----|------|------|
| `correlation_id` | Webhook / seed / 工作流 Code；头 `X-Correlation-Id` | 查 `audit_logs`、Slack 文案 |
| `trace_id` | OTEL W3C | 串联 Jaeger |
| `store_id` | PG `stores` | 过滤运维摘要 |

## seed 后验证

1. 从脚本输出或 Slack 复制 `correlation_id`。
2. Jaeger → 服务 `n8n-platform` / `n8n-ecom-ai-service`。
3. Langfuse → 标签 `ecom-workflow`；核对定价/营销 `prompt_version`。
4. `curl http://localhost:8003/health`、`/prompts`。

## 排查

| 现象 | 检查 |
|------|------|
| Jaeger 无 span | Collector、`proxy_network`、OTEL 地址 |
| Langfuse 空 | 密钥/Host；sidecar 认证日志 |
| 无 LLM span | 是否跑了定价/营销工作流 |
| 访问 sidecar 走代理失败 | 扩展 `NO_PROXY` 含 `ecom_python_ai` |

见 [ARCHITECTURE.md](ARCHITECTURE.md)、[RUN_EXAMPLE.md](RUN_EXAMPLE.md)。
