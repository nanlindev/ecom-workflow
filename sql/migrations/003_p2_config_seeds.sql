-- P2 config seeds: competitor whitelist, pricing Slack alert, demo SKU.

INSERT INTO config_pricing (key, value, description) VALUES
    ('pricing_alert_enabled', 'true', 'Slack when a pricing recommendation is created'),
    ('demo_pricing_sku', 'sku-managed-1', 'Primary default SKU for Pricing Engine (multi-channel demo)'),
    (
        'demo_pricing_skus',
        'sku-managed-1,SNOWBOARD-LIQUID',
        'Comma-separated SKUs for Pricing Engine Cron (multi-channel sync demos)'
    ),
    (
        'competitor_urls',
        '[{"url":"https://example.com/products/sku-managed-1","sku":"sku-managed-1","source_name":"example-comp"},{"url":"https://example.com/products/snowboard-liquid","sku":"SNOWBOARD-LIQUID","source_name":"example-comp"}]',
        'JSON array of competitor crawl targets'
    )
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_main (key, value, description) VALUES
    ('demo_store_id', '', 'Optional UUID override for Cron workflows (Scenario B)')
ON CONFLICT (key) DO NOTHING;
