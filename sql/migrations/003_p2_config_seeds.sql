-- P2 config seeds: competitor whitelist, pricing Slack alert, demo SKU.

INSERT INTO config_pricing (key, value, description) VALUES
    ('pricing_alert_enabled', 'true', 'Slack when a pricing recommendation is created'),
    ('demo_pricing_sku', 'TEE-BLACK-M', 'Default SKU for Scenario B pricing demo'),
    (
        'competitor_urls',
        '[{"url":"https://example.com/products/tee-black-m","sku":"TEE-BLACK-M","source_name":"example-comp"}]',
        'JSON array of competitor crawl targets'
    )
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_main (key, value, description) VALUES
    ('demo_store_id', '', 'Optional UUID override for Cron workflows (Scenario B)')
ON CONFLICT (key) DO NOTHING;
