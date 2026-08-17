# Error handling

## Two-tier model

### Tier 1: Node-level (predictable failures)

External I/O nodes use **On Error → Continue (using error output)** with wired handler Code nodes. See [ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md).

| Failure | Typical handler | Degradation |
|---------|-----------------|-------------|
| Sidecar HTTP (ingest/sync/pricing) | Handle * HTTP Error | `*_error_message`, skip Slack or use fallback text |
| Slack notify | Log Slack Error | Preserve upstream payload; mark notify failed |
| Resend / marketing send | Handle Send Error | `send_status=failed` |
| error_logs write | Handle error_logs Write Failure | Continue to alert gate |

Handlers set `_metadata.processing_stage` and preserve `correlation_id`.

**Rule:** every `continueErrorOutput` node must have `connect_error(...)` — dangling error ports swallow failures and **bypass** the global Error Handler.

### Tier 2: Global (unpredictable crashes)

Unhandled exceptions → **Ecom Error Handler** (Error Trigger) → `POST /errors/log` → `error_logs` + optional Slack when gated.

Node-level handlers are **not** replaced by the global workflow — especially after Slack webhook Ack.

## Bind Error Workflow after import

JSON `errorWorkflow` is a **name**; n8n usually does **not** bind on import.

**Settings → Error Workflow → `Ecom Error Handler`**

Apply to all main workflows (Ingest, Sync, Tracker, Returns, P2/P3 Cron workflows, Slack Actions).

## Retry defaults

HTTP Request, Slack: Retry ON, max 3, wait 5000 ms (from `scripts/generate_workflows.py`).

## Regenerate

```bash
python3 scripts/generate_workflows.py
python3 scripts/generate_workflows_p2.py
```

Re-import JSON; re-bind credentials + Error Workflow.

Overview table: [ERROR_HANDLING_NODES.md](ERROR_HANDLING_NODES.md).
