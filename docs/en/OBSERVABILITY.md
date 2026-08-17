# Observability

End-to-end tracing for n8n executions and LLM calls.

## Stack

| Piece | Role |
|-------|------|
| OpenTelemetry Collector | Receives OTLP from n8n + sidecar |
| Jaeger | Span UI (`n8n-platform`, `n8n-ecom-ai-service`) |
| Langfuse | LLM generations tagged **`ecom-workflow`** |

Deploy OBS on `proxy_network` (sibling repos: `otel-collector-stack`, `jaeger-stack`, `langfuse-stack`).

## Environment checklist

**platform-n8n**

- OTEL exporter → `http://otel-collector:4318`
- Prefer `N8N_OTEL_TRACES_INJECT_OUTBOUND=true`

**ecom sidecar** (`.env`)

- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
- `OTEL_SERVICE_NAME=n8n-ecom-ai-service`
- `LANGFUSE_*` keys + `LANGFUSE_HOST`

**NO_PROXY** must include internal Docker names:

```text
ecom_python_ai,ecom_postgres,otel-collector,langfuse-web,jaeger,crm_python_ai
```

See `.env.example` — prevents sidecar→Postgres / OTEL calls through an external HTTP proxy.

## Correlation model

| Id | Where | Use |
|----|-------|-----|
| `correlation_id` | Webhook / seed / workflow Code; header `X-Correlation-Id` | Business search in `audit_logs`, Slack text |
| `trace_id` | W3C from OTEL | Join Jaeger spans |
| `store_id` | PG `stores` | Filter ops summaries |

## Verify after a seed run

1. Copy `correlation_id` from script output or Slack message.
2. Jaeger → services `n8n-platform` / `n8n-ecom-ai-service` around execution time.
3. Langfuse → filter tag `ecom-workflow`; check `prompt_version` on pricing/marketing runs.
4. `curl http://localhost:8003/health` and `/prompts`.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No Jaeger spans | Collector up? `proxy_network`? OTEL endpoint? |
| No Langfuse | Keys/host; sidecar logs for auth warnings |
| Spans without LLM | Pricing/marketing workflow executed? |
| Proxy errors to sidecar | Expand `NO_PROXY` for `ecom_python_ai` |

See [ARCHITECTURE.md](ARCHITECTURE.md), [RUN_EXAMPLE.md](RUN_EXAMPLE.md).
