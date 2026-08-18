# WooCommerce setup

Woo webhooks → n8n `/webhook/ecom-woo` → sidecar `/ingest/woocommerce`. REST keys enable P3b live stock/price writeback.

## Webhook registration

In Woo **Settings → Advanced → Webhooks**:

| Topic | Delivery URL |
|-------|--------------|
| Product created / updated | `https://<n8n>/webhook/ecom-woo` |
| Order created / updated | same |
| (Refunds) | **No dedicated refunds topic required**: subscribe `order.updated`; sidecar maps `status=refunded` and/or `refunds[]` → `event_type=return` + Returns dispatch |

Core Woo webhook topics are only `order.created|updated|deleted`. Payload matches the REST **Order** resource (not `/orders/<id>/refunds`). Refund summaries appear on the order as `refunds[]`; use the Order Refunds REST API when full refund line items are needed.
| (optional) Customer | same |

Set a **Secret** → `.env`:

```bash
WOO_WEBHOOK_SECRET=your_woo_webhook_secret
```

Sidecar verifies HMAC (or pass `skip_verify: true` in local curl only).

## REST API keys (P3b writeback)

Woo **Settings → Advanced → REST API** → Read/Write keys:

```bash
WOO_BASE_URL=https://your-woo-store.example
WOO_CONSUMER_KEY=ck_xxx
WOO_CONSUMER_SECRET=cs_xxx
```

Used by `python-service/channels/woocommerce.py` for stock/price updates when gated.

## Multi-channel SoT

Use the **same `store_key`** as Shopify (default `demo-shopify` from seeds) so Woo rows merge under one store:

- Ingest body / header may pass `store_key`
- Or set `config_main.demo_woo_store_key` if Woo uses a different default

Master channel (`shopify`) wins conflicts; Woo is typically a **slave** in `slave_channels`. Product/stock webhooks still upsert Woo `inventory_levels`; they do **not** dispatch Inventory Sync while Shopify is master (writeback must not echo).

## n8n checklist

- [ ] **Ecom Platform Ingest** Active (Woo webhook path)
- [ ] Error Workflow bound
- [ ] `mode=test` until creds verified

## Smoke test

```bash
python3 scripts/seed_demo_scenario_p3.py
```

Expect Woo product ingest + inventory sync with drift / `writeback_status` per mode.

See [CREDENTIALS.md](CREDENTIALS.md), [TEST_PRODUCTION.md](TEST_PRODUCTION.md), [RUN_EXAMPLE.md](RUN_EXAMPLE.md).
