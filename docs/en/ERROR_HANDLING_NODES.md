# Node error-handling reference

Short checklist after import. Generator source: `scripts/generate_workflows.py`.

## Global conventions

| Setting | Applies to |
|---------|------------|
| **Stop Workflow** | Code (logic), IF, Merge, Execute Workflow, Set |
| **Continue + error output** | HTTP Request (sidecar), Slack, Resend HTTP |
| **Retry 3× / 5s** | HTTP Request, Slack |
| **Error Workflow** | Re-bind `Ecom Error Handler` on every main workflow |

Credential placeholder: `SLACK_CREDENTIAL_ID` — re-bind after import.

## Must wire `connect_error`

| Workflow | Node types / names |
|----------|-------------------|
| **Platform Ingest** | Sidecar ingest HTTP → Handle Ingest Error |
| **Inventory Sync** | `/inventory/sync` HTTP → Handle Inventory Sync Error; Slack → Log Slack Error |
| **Order Tracker** | `/orders/track` HTTP → handler |
| **Returns Automation** | `/returns/decide` HTTP → handler |
| **Competitor Price Crawl** | fetch + `/competitors/parse` HTTP → handlers |
| **Pricing Engine** | `/pricing/recommend` HTTP; Slack notify → handlers |
| **Customer Insights** | insight HTTP nodes → handlers |
| **Marketing Orchestrator** | copy/enroll/advance HTTP; Resend send → handlers |
| **Slack Actions** | `/pricing/action` HTTP; Slack response → handlers |
| **Daily / Weekly Summary** | `/ops/summary` HTTP; Slack → handlers |
| **Health Keepalive** | `/ops/keepalive` HTTP; Slack alert → handlers |
| **Error Handler** | `/errors/log` HTTP → Handle error_logs Write Failure |

## Output ports

- **main[0]**: success path
- **main[1]**: error → Handler → rejoin or End

## Acceptance spot-checks

| Scenario | Expected |
|----------|----------|
| Sidecar down during sync | Handler item with `inventory_error_message`; no silent success |
| Slack fails after drift detect | Error logged; drift data preserved in execution |
| Unhandled Code throw | Global Error Handler → `error_logs` row |

Regenerate: `python3 scripts/generate_workflows.py`. Overview: [ERROR_HANDLING.md](ERROR_HANDLING.md).
