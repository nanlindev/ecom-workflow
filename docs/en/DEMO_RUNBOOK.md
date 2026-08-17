# Demo Runbook

Portfolio demo script for ecom-workflow P0–P3. Start with `mode=test`; use isolated Slack channel + demo stores for production writeback.

Related: [SHOWCASE.md](../SHOWCASE.md) · [TEST_PRODUCTION.md](TEST_PRODUCTION.md) · [INSTALL.md](INSTALL.md) · [RUN_EXAMPLE.md](RUN_EXAMPLE.md)

**Chinese:** [zh/DEMO_RUNBOOK.md](../zh/DEMO_RUNBOOK.md)

---

## 0. Pre-flight

- [ ] `docker compose up` healthy; `/health` → `"database":"ok"`
- [ ] 13 workflows imported; Error Workflow → **Ecom Error Handler**
- [ ] Slack bot in demo channel; Interactivity → `/webhook/ecom-slack-interactions`
- [ ] PG: `config_main.mode=test`
- [ ] OBS: Jaeger + Langfuse; `NO_PROXY` includes `ecom_python_ai`

---

## Scenario A — Inventory + orders (P1, required)

**Trust path:** platform ingest → drift detect → PG SoT.

```bash
python3 scripts/seed_demo_scenario_a.py
```

### Checklist

- [ ] `sku-managed-1` in `inventory_levels` (Shopify master)
- [ ] Sync: `has_drift=true`, `writeback_status=skipped_test_mode`
- [ ] Order `5001` in `orders`; return `R-9001` → `manual_review`
- [ ] Optional Slack drift card (if `slack_in_test=true`)

Detail: [DEMO_SCENARIO_A.md](DEMO_SCENARIO_A.md)

**Status:** [ ] Done

---

## Scenario B — Pricing + email (P2, required)

**Wow path:** competitor price → Slack Approve/Reject.

```bash
export ECOM_DEMO_STORE_ID=<from Scenario A>
python3 scripts/seed_demo_scenario_b.py
```

### Checklist

- [ ] `pricing_recommendations` row `pending`
- [ ] Execute **Ecom Pricing Engine** → Slack Approve/Reject
- [ ] Click → **Ecom Slack Actions** → status `approved` / `rejected`
- [ ] test mode: `writeback_status=skipped_test_mode`; marketing `send_status=skipped_test_mode`

Detail: [DEMO_SCENARIO_B.md](DEMO_SCENARIO_B.md)

**Status:** [ ] Done

---

## Scenario C — Woo ingest + live writeback (P3/P3b)

**Trigger when creds set:** Woo webhook or seed P3.

```bash
python3 scripts/seed_demo_scenario_p3.py
```

### test mode

- [ ] Woo product ingest OK; sync shows drift
- [ ] `writeback_status=skipped_test_mode`

### production smoke (isolated store only)

1. Set `.env`: `WOO_*` or `SHOPIFY_ADMIN_ACCESS_TOKEN` + `SHOPIFY_LOCATION_ID`
2. `UPDATE config_main SET value='production' WHERE key='mode';`
3. Re-run sync, or Slack-Approve a pricing recommendation (production applies live channel writeback)
4. Expect `writeback_status=applied` or `applied_sot_only`
5. Verify stock/price on Woo Admin or Shopify Admin
6. Roll back: `mode=test`

**Status:** [ ] Done

---

## Optional — Daily / Weekly / Keepalive (P3)

| Workflow | Manual trigger | Expect (test) |
|----------|----------------|---------------|
| Daily Summary | Execute Workflow | Metrics built; Slack skipped |
| Weekly Summary | Execute Workflow | Same |
| Health Keepalive | Execute Workflow | PG ok; alert skipped in test |

Flip `mode=production` + enable notification flags for Slack digests.

---

## Observability pass

| Check | How |
|-------|-----|
| Langfuse | Tag `ecom-workflow`; pricing generation after Scenario B |
| Jaeger | `n8n-ecom-ai-service` around sync/pricing |
| correlation_id | Slack drift card or seed script output |

---

## Post-demo

- [ ] `config_main.mode` → `test`
- [ ] Revert any manual stock/price changes on demo stores

Gate reference: [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md).
