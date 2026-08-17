# DEMO Scenario B (P2 intelligence path)

After P1 Scenario A (`store_id` known) and compose sidecar healthy.

## Prerequisites

```bash
export ECOM_DEMO_STORE_ID=<uuid from Scenario A>
curl -s http://localhost:8003/health
```

Import P2 workflows from `workflows/`:

1. `Ecom Competitor Price Crawl`
2. `Ecom Pricing Engine`
3. `Ecom Customer Insights`
4. `Ecom Marketing Orchestrator`
5. `Ecom Slack Actions` (Interactivity URL → `/webhook/ecom-slack-interactions`)

Re-bind Error Workflow + Slack credential. Set Slack App Interactivity Request URL to n8n production webhook for `ecom-slack-interactions`. Ensure `SLACK_SIGNING_SECRET` / `SLACK_ADMIN_USERS` in platform `.env`.

## Seed

```bash
cd /path/to/ecom-workflow
ECOM_DEMO_STORE_ID=... python3 scripts/seed_demo_scenario_b.py
```

Expect:

- Competitor snapshots for `sku-managed-1` (~2499) and `SNOWBOARD-LIQUID` (~3899), or LLM parse of the same HTML
- `pricing_recommendations` rows (`pending` undercut / `held` when competitor is higher); Slack when actionable
- RFM/churn customer updates
- Abandon enrollment created; advance → `send_status=skipped_test_mode` (no real email)

## Manual Slack path

Execute **Ecom Pricing Engine** (or wait Cron) → Slack Block Kit with Approve / Reject → click → **Ecom Slack Actions** → `/pricing/action` → status `approved` / `rejected` (writeback skipped in test).

## Acceptance

- [ ] Recommended price / hold appears in Slack
- [ ] Approve/Reject updates `pricing_recommendations.status`
- [ ] test mode: marketing enrollment written, no Resend send
