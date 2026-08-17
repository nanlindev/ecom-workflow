-- E-commerce Intelligence schema v1 (idempotent).
-- Applied by sidecar migrate.py and safe to re-run.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- schema_migrations is created by the runner; keep table list complete here.
-- ---------------------------------------------------------------------------

-- Store registry: platform, credential reference name (not secrets), enable flag.
CREATE TABLE IF NOT EXISTS stores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_key       TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    platform        TEXT NOT NULL CHECK (platform IN ('shopify', 'woocommerce', 'amazon', 'other')),
    credential_name TEXT,
    external_shop_id TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE stores IS 'Registered commerce stores; secrets stay in n8n credentials / .env';

-- Internal products keyed by store + sku.
CREATE TABLE IF NOT EXISTS products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    sku             TEXT NOT NULL,
    title           TEXT,
    cost            NUMERIC(18, 4),
    currency        TEXT DEFAULT 'USD',
    status          TEXT NOT NULL DEFAULT 'active',
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, sku)
);
COMMENT ON TABLE products IS 'Internal SKU catalog per store; raw holds source payload';
CREATE INDEX IF NOT EXISTS idx_products_store_sku ON products (store_id, sku);

-- Platform listing map: external product/variant id → internal sku.
CREATE TABLE IF NOT EXISTS listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    sku             TEXT NOT NULL,
    product_id      UUID REFERENCES products(id) ON DELETE SET NULL,
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, platform, external_id)
);
COMMENT ON TABLE listings IS 'Maps platform external_id to internal sku';
CREATE INDEX IF NOT EXISTS idx_listings_sku ON listings (store_id, sku);

-- Per-channel inventory levels.
CREATE TABLE IF NOT EXISTS inventory_levels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    sku             TEXT NOT NULL,
    platform        TEXT NOT NULL,
    location_key    TEXT NOT NULL DEFAULT 'default',
    available       INTEGER NOT NULL DEFAULT 0,
    reserved        INTEGER NOT NULL DEFAULT 0,
    safety_stock    INTEGER NOT NULL DEFAULT 0,
    last_synced_at  TIMESTAMPTZ,
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, sku, platform, location_key)
);
COMMENT ON TABLE inventory_levels IS 'Channel inventory + last sync timestamp';
CREATE INDEX IF NOT EXISTS idx_inventory_store_sku ON inventory_levels (store_id, sku);

-- Unified orders.
CREATE TABLE IF NOT EXISTS orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id            UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    correlation_id      UUID,
    platform            TEXT NOT NULL,
    external_order_id   TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open',
    fulfillment_status  TEXT,
    financial_status    TEXT,
    customer_email      TEXT,
    currency            TEXT DEFAULT 'USD',
    totals              JSONB NOT NULL DEFAULT '{}'::jsonb,
    line_items          JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    ordered_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, platform, external_order_id)
);
COMMENT ON TABLE orders IS 'Normalized multi-platform orders; idempotent on store+platform+external_order_id';
CREATE INDEX IF NOT EXISTS idx_orders_correlation ON orders (correlation_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (store_id, status);

CREATE TABLE IF NOT EXISTS order_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    sku             TEXT,
    external_line_id TEXT,
    title           TEXT,
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      NUMERIC(18, 4),
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (order_id, external_line_id)
);
COMMENT ON TABLE order_items IS 'Order line items linked to parent order';

-- Customers with RFM cache fields.
CREATE TABLE IF NOT EXISTS customers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    external_id     TEXT,
    display_name    TEXT,
    rfm_recency     INTEGER,
    rfm_frequency   INTEGER,
    rfm_monetary    NUMERIC(18, 4),
    rfm_segment     TEXT,
    churn_score     NUMERIC(8, 4),
    vip             BOOLEAN NOT NULL DEFAULT FALSE,
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, email)
);
COMMENT ON TABLE customers IS 'Customer identity + RFM / churn cache';
CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers (store_id, rfm_segment);

-- Own / competitor price time series.
CREATE TABLE IF NOT EXISTS price_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID REFERENCES stores(id) ON DELETE CASCADE,
    sku             TEXT,
    source_type     TEXT NOT NULL CHECK (source_type IN ('own', 'competitor')),
    source_name     TEXT,
    url             TEXT,
    price           NUMERIC(18, 4),
    currency        TEXT DEFAULT 'USD',
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE price_snapshots IS 'Own and competitor price observations';
CREATE INDEX IF NOT EXISTS idx_price_snapshots_sku ON price_snapshots (store_id, sku, captured_at DESC);

CREATE TABLE IF NOT EXISTS pricing_recommendations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    sku             TEXT NOT NULL,
    current_price   NUMERIC(18, 4),
    recommended_price NUMERIC(18, 4),
    currency        TEXT DEFAULT 'USD',
    reasoning       TEXT,
    strategy        TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'skipped_test_mode', 'held')),
    correlation_id  UUID,
    fallback_used   BOOLEAN NOT NULL DEFAULT FALSE,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE pricing_recommendations IS 'Suggested prices awaiting Slack approval / apply';
CREATE INDEX IF NOT EXISTS idx_pricing_rec_status ON pricing_recommendations (store_id, status);

CREATE TABLE IF NOT EXISTS returns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    order_id        UUID REFERENCES orders(id) ON DELETE SET NULL,
    external_return_id TEXT,
    decision        TEXT CHECK (decision IN ('auto_approve', 'manual_review', 'reject', 'pending')),
    amount          NUMERIC(18, 4),
    currency        TEXT DEFAULT 'USD',
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    correlation_id  UUID,
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE returns IS 'Return automation decisions and status';
CREATE UNIQUE INDEX IF NOT EXISTS idx_returns_external
    ON returns (store_id, external_return_id) WHERE external_return_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    campaign_key    TEXT NOT NULL,
    campaign_type   TEXT NOT NULL CHECK (campaign_type IN ('abandon_cart', 'vip', 'birthday', 'other')),
    name            TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, campaign_key)
);
COMMENT ON TABLE campaigns IS 'Marketing campaign definitions';

CREATE TABLE IF NOT EXISTS campaign_enrollments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    customer_id     UUID REFERENCES customers(id) ON DELETE SET NULL,
    email           TEXT,
    step            INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'enrolled'
                    CHECK (status IN ('enrolled', 'in_progress', 'completed', 'exited', 'skipped_test_mode')),
    next_action_at  TIMESTAMPTZ,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id  UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE campaign_enrollments IS 'Per-customer campaign state machine';
CREATE INDEX IF NOT EXISTS idx_enrollments_next ON campaign_enrollments (status, next_action_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID REFERENCES stores(id) ON DELETE SET NULL,
    correlation_id  UUID,
    action          TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE audit_logs IS 'Business audit trail';
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_logs (correlation_id);

CREATE TABLE IF NOT EXISTS error_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID REFERENCES stores(id) ON DELETE SET NULL,
    correlation_id  UUID,
    workflow_name   TEXT,
    node_name       TEXT,
    error_message   TEXT,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE error_logs IS 'Workflow / node error records';
CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs (created_at DESC);

-- Config tables (no secrets).
CREATE TABLE IF NOT EXISTS config_main (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE config_main IS 'Global mode and feature flags (e.g. mode=test|production)';

CREATE TABLE IF NOT EXISTS config_inventory (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE config_inventory IS 'Inventory sync policy (master channel, safety stock defaults)';

CREATE TABLE IF NOT EXISTS config_pricing (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE config_pricing IS 'Pricing engine strategy and writeback channel flags';

CREATE TABLE IF NOT EXISTS config_marketing (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE config_marketing IS 'Marketing enrollment and send gates';

CREATE TABLE IF NOT EXISTS config_notifications (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE config_notifications IS 'Slack / email notification enable flags';

CREATE TABLE IF NOT EXISTS prompt_registry (
    prompt_key      TEXT PRIMARY KEY,
    version         TEXT NOT NULL,
    model           TEXT,
    file_path       TEXT,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE prompt_registry IS 'Prompt version registry (files under prompts/; no secrets)';

-- Seed defaults (idempotent upserts).
INSERT INTO config_main (key, value, description) VALUES
    ('mode', 'test', 'Runtime mode: test | production'),
    ('project_tag', 'ecom-workflow', 'Langfuse / workflow tag')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_inventory (key, value, description) VALUES
    ('master_channel', 'shopify', 'Authoritative inventory channel'),
    ('safety_stock_default', '5', 'Default safety stock units'),
    ('writeback_enabled', 'true', 'Allow writeback to slave channels in production')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_pricing (key, value, description) VALUES
    ('enabled', 'true', 'Pricing engine on/off'),
    ('min_margin_pct', '15', 'Minimum margin percent')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_marketing (key, value, description) VALUES
    ('enabled', 'true', 'Marketing orchestrator on/off'),
    ('abandon_cart_enabled', 'true', 'Abandon cart sequences'),
    ('vip_enabled', 'true', 'VIP outreach'),
    ('send_email_in_test', 'false', 'Never send real email in test mode')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_notifications (key, value, description) VALUES
    ('slack_enabled', 'true', 'Slack notifications master switch'),
    ('slack_in_test', 'true', 'Allow Slack in test (ops alerts)'),
    ('email_provider', 'resend', 'Email provider used by n8n Marketing Orchestrator (Resend HTTP)')
ON CONFLICT (key) DO NOTHING;

INSERT INTO prompt_registry (prompt_key, version, model, file_path, description) VALUES
    ('pricing_recommend', 'pricing_recommend-v1', 'deepseek-chat', 'prompts/pricing_recommend.md', 'Pricing recommendation JSON'),
    ('marketing_copy', 'marketing_copy-v1', 'deepseek-chat', 'prompts/marketing_copy.md', 'Marketing email copy JSON'),
    ('competitor_parse', 'competitor_parse-v1', 'deepseek-chat', 'prompts/competitor_parse.md', 'Competitor HTML → price JSON')
ON CONFLICT (prompt_key) DO NOTHING;
