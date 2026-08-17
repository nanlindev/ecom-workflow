# Showcase — E-commerce Intelligence Template

Buyer-facing overview: multi-store ingest → Postgres SoT → gated inventory/price writeback → Slack human-in-the-loop pricing → ops digests, with Jaeger + Langfuse on every path.

| | |
|--|--|
| **Run the demo** | [DEMO_RUNBOOK.md](en/DEMO_RUNBOOK.md) |
| **Install** | [INSTALL.md](en/INSTALL.md) |
| **Video script** | [assets/demo-video-script.md](../assets/demo-video-script.md) |

---

## Value proposition

Shopify and WooCommerce drift silently. This template closes the loop: webhooks into shared n8n, FastAPI sidecar as domain logic, **Postgres as system of record**, and **P3b live writeback** to slave channels when `mode=production` and credentials are set. Secondary path: competitor-aware pricing with Slack Approve/Reject before prices hit the storefront.

**Full stack:** n8n (13 workflows) + Python AI sidecar + Postgres + Shopify/Woo + Slack + Resend + OpenTelemetry / Jaeger / Langfuse.

---

## What buyers get

| Capability | What it proves |
|------------|----------------|
| **Production gates** | `mode=test` → `production`; writeback and digests respect config flags |
| **Multi-channel SoT** | Master/slave inventory merge; same `store_key` across Shopify + Woo |
| **Live writeback (P3b)** | Woo REST or Shopify Admin token + location — not mock-only |
| **Human-in-the-loop pricing** | Slack Approve/Reject → `/pricing/action` |
| **Generator-driven workflows** | `scripts/generate_workflows.py` — node error handlers wired |
| **Observability** | `correlation_id`; Langfuse tag `ecom-workflow` |

---

## Demo scenarios (priority)

1. **A — Inventory drift** (`seed_demo_scenario_a.py`): trust path, test-mode writeback skip  
2. **B — Pricing Slack** (`seed_demo_scenario_b.py`): approve/reject wow  
3. **C — Woo + live writeback** (`seed_demo_scenario_p3.py`): production smoke when creds configured  

---

## Stack at a glance

| Layer | Tech |
|-------|------|
| Orchestration | n8n — 13 workflows |
| AI sidecar | FastAPI — ingest, sync, pricing, insights, marketing, ops |
| SoT | PostgreSQL (`ecom_postgres`) |
| Storefronts | Shopify webhooks + Admin API; Woo webhooks + REST |
| Collab / email | Slack Block Kit; Resend |
| Observability | OTEL → Jaeger; Langfuse |

Deep dive: [ARCHITECTURE.md](en/ARCHITECTURE.md) · [WORKFLOWS.md](en/WORKFLOWS.md)
