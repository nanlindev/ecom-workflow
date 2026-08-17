# Demo video script — one spine, three cuts

**Story spine:** Multi-channel inventory drift → Postgres SoT → **live writeback** (Woo or Shopify Admin) proves production gates. Secondary wow: **pricing Slack Approve** + Langfuse trace.

Annotate shots: **F** = Fiverr ≤75s · **U** = Upwork ≤90s · **Y** = YouTube 2–3 min

---

## 0:00–0:08 — Hook (F · U · Y)

| Beat | Visual | VO (English) |
|------|--------|--------------|
| 0:00 | Split screen: Shopify stock 42 vs Woo 37 | "Two storefronts, one SKU — who's right?" |
| 0:05 | n8n **Ecom Platform Ingest** canvas | "This n8n stack ingests, reconciles, and writes back — safely gated." |

---

## 0:08–0:22 — Architecture flash (U · Y only; F: 3s montage)

| Beat | Visual | VO |
|------|--------|-----|
| 0:08 | Mermaid / architecture still | "Shopify master, Woo slave, Postgres SoT, FastAPI sidecar." |
| 0:15 | Jaeger + Langfuse tabs | "Every run carries correlation_id into Jaeger and Langfuse." |

**F cut:** Skip to 0:22.

---

## 0:22–0:45 — Scenario A: drift detect (F · U · Y)

| Beat | Visual | VO |
|------|--------|-----|
| 0:22 | Terminal: `seed_demo_scenario_a.py` | "Seed injects real drift on demo SKU sku-managed-1." |
| 0:30 | Slack drift card | "Inventory Sync flags drift — writeback skipped in test mode." |
| 0:38 | Postgres `inventory_levels` query | "Postgres holds the merged truth before any live API call." |

**F:** End VO at 0:40 with "test mode protects prod stores."

---

## 0:45–1:05 — P3b live writeback (F · U · Y — primary trust)

| Beat | Visual | VO |
|------|--------|-----|
| 0:45 | `.env` blur: `WOO_*` or `SHOPIFY_ADMIN_ACCESS_TOKEN` | "Flip production mode with channel credentials configured." |
| 0:52 | Re-run sync / Woo admin stock before→after | "Writeback_status: applied — slave channel matches master." |
| 1:00 | `writeback_status` in execution output | "SoT aligned in PG even when a channel API is missing — applied_sot_only." |

**F:** Compress to 0:45–0:58 (13s); this is the **money shot**.

---

## 1:05–1:25 — Scenario B: pricing approve (U · Y; F: optional 5s tag)

| Beat | Visual | VO |
|------|--------|-----|
| 1:05 | **Ecom Pricing Engine** Slack Approve button | "Competitor crawl feeds pricing recommendations." |
| 1:12 | Click Approve → updated Slack message | "Human-in-the-loop before price hits the storefront." |
| 1:18 | Langfuse `pricing_recommend` generation | "Prompt version pinned in Langfuse — tag ecom-workflow." |

**F:** Skip entirely or 1:20–1:25 quick flash of Approve button only.

---

## 1:25–1:45 — Ops + observability (Y only)

| Beat | Visual | VO |
|------|--------|-----|
| 1:25 | Daily Summary Slack digest | "Daily and weekly ops digests — same production gates." |
| 1:32 | Health Keepalive execution | "Keepalive pings Postgres and channel endpoints." |
| 1:38 | Jaeger trace filtered by correlation_id | "Debug any run end-to-end in Jaeger." |

---

## 1:45–2:00 — CTA (U · Y)

| Beat | Visual | VO |
|------|--------|-----|
| 1:45 | 13-workflow list in n8n | "Thirteen workflows, generator-driven JSON, MIT template." |
| 1:52 | README / SHOWCASE link | "Clone, import, seed — link in description." |

**F CTA (0:58–1:15):** Drift → live writeback → "DM for install + your stack."

**U CTA (1:25–1:30):** Add pricing approve flash + "Message me for scoped rollout."

---

## Runtime targets

| Cut | Max duration | Must-include shots |
|-----|--------------|-------------------|
| **Fiverr (F)** | 75s | Drift Slack + live writeback before/after + test→prod gate mention |
| **Upwork (U)** | 90s | F shots + pricing Approve + 5s architecture |
| **YouTube (Y)** | 2–3 min | Full A + P3b + B + ops + Jaeger/Langfuse |

## Recording notes

- Use demo store only; blur secrets in `.env`.
- Same `correlation_id` visible in Slack + Jaeger for one continuous narrative.
- Seed scripts: `seed_demo_scenario_a.py`, `seed_demo_scenario_b.py`, `seed_demo_scenario_p3.py`.

Runbook: [docs/en/DEMO_RUNBOOK.md](../docs/en/DEMO_RUNBOOK.md)
