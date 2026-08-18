# Demo video script — one spine, three cuts

**Story spine:** Shopify **order paid** → n8n Order Tracker → **refund > auto-approve** → Slack manual review. Secondary trust: inventory drift live writeback. Wow: pricing Approve + Langfuse.

Annotate shots: **F** = Fiverr ≤75s · **U** = Upwork ≤90s · **Y** = YouTube 2–3 min

---

## 0:00–0:08 — Hook (F · U · Y)

| Beat | Visual | VO (English) |
|------|--------|--------------|
| 0:00 | Shopify Admin: paid order on `SNOWBOARD-LIQUID` | "Order paid. Who tracks it — and who refunds it?" |
| 0:05 | n8n **Ecom Order Tracker** execution | "This n8n stack ingests the order into Postgres — then the return rules fire." |

---

## 0:08–0:22 — Architecture flash (U · Y only; F: 3s montage)

| Beat | Visual | VO |
|------|--------|-----|
| 0:08 | Mermaid / architecture still | "Shopify master, Woo slave, Postgres SoT, FastAPI sidecar." |
| 0:15 | Jaeger + Langfuse tabs | "Every run carries correlation_id into Jaeger and Langfuse." |

**F cut:** Skip to 0:22.

---

## 0:22–0:45 — Scenario A: order + return (F · U · Y — primary trust)

| Beat | Visual | VO |
|------|--------|-----|
| 0:22 | Shopify **Refund** on that order (amount > $50) | "Refunds over the auto-approve cap need a human." |
| 0:30 | Slack: `Return needs manual review` | "Rules engine: amount and age — not a silent refund." |
| 0:38 | n8n **Returns Automation** + same `correlation_id` | "One id from webhook to Slack. Ops can open Shopify Admin from the card." |

**F:** This loop is the money shot. Skip inventory if over time.

---

## 0:45–1:05 — Inventory live writeback (U · Y; F: optional 8s)

| Beat | Visual | VO |
|------|--------|-----|
| 0:45 | Shopify: change `SNOWBOARD-LIQUID` qty | "Same ingest path keeps inventory honest across channels." |
| 0:52 | Slack one drift card, `Writeback: applied` | "Master Shopify, slave Woo — production writeback." |
| 1:00 | Woo Admin stock matches | "One SKU, one number." |

**F:** Optional 8s Woo before/after only.

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

**F CTA (0:58–1:15):** Paid order → refund Slack review → "DM for install + your stack."

**U CTA (1:25–1:30):** Add inventory writeback flash + pricing Reject + "Message me for scoped rollout."

**Y extra (after 1:25):** Daily Slack + Jaeger on the return `correlation_id` + 3–8s flashes: Crawl, Insights, Marketing (gated), Keepalive, Weekly, Error Handler — every workflow appears once. Operator matrix: [demo-shot-list.md](demo-shot-list.md).

---

## Runtime targets

| Cut | Max duration | Must-include shots |
|-----|--------------|-------------------|
| **Fiverr (F)** | 75s | Paid order in n8n + refund Slack `manual_review` |
| **Upwork (U)** | 90s | F shots + inventory writeback before/after |
| **YouTube (Y)** | 2–3 min | Order/return + inventory + pricing + ops + Jaeger |

## Recording notes

- Primary live path: Shopify paid order → Order Tracker → refund >$50 → Slack review. Shot list: [demo-shot-list.md](demo-shot-list.md).
- Secondary: Shopify qty → one real-SKU Slack card → Woo matches.
- Local n8n off. Blur secrets. Same `correlation_id` on the return card + n8n + Jaeger.

Runbook: [docs/en/DEMO_RUNBOOK.md](../docs/en/DEMO_RUNBOOK.md)
