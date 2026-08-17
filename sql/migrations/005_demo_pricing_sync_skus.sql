-- Point pricing demo at multi-channel sync SKUs (Shopify + Woo visible).

UPDATE config_pricing
SET value = 'sku-managed-1',
    description = 'Primary default SKU for Pricing Engine (multi-channel demo)'
WHERE key = 'demo_pricing_sku';

INSERT INTO config_pricing (key, value, description) VALUES
    (
        'demo_pricing_skus',
        'sku-managed-1,SNOWBOARD-LIQUID',
        'Comma-separated SKUs for Pricing Engine Cron (multi-channel sync demos)'
    )
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    description = EXCLUDED.description;

UPDATE config_pricing
SET value = '[{"url":"https://example.com/products/sku-managed-1","sku":"sku-managed-1","source_name":"example-comp"},{"url":"https://example.com/products/snowboard-liquid","sku":"SNOWBOARD-LIQUID","source_name":"example-comp"}]',
    description = 'JSON array of competitor crawl targets (demo sync SKUs)'
WHERE key = 'competitor_urls';
