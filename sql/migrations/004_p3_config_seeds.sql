-- P3 config seeds: summaries, keepalive, writeback Sot align, Woo demo key.

INSERT INTO config_notifications (key, value, description) VALUES
    ('daily_summary_enabled', 'true', 'Slack Daily Summary when mode=production'),
    ('weekly_summary_enabled', 'true', 'Slack Weekly Summary when mode=production'),
    ('keepalive_alert_enabled', 'true', 'Slack when Health Keepalive fails in production')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_inventory (key, value, description) VALUES
    ('writeback_align_sot', 'true', 'Align slave inventory_levels in PG after live writeback attempt')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_pricing (key, value, description) VALUES
    (
        'price_writeback_channels',
        'shopify,woocommerce',
        'Comma-separated channels for live price writeback on Slack Approve (production + writeback_enabled)'
    )
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_main (key, value, description) VALUES
    ('demo_woo_store_key', 'demo-woocommerce', 'Default store_key for Woo ingest webhooks')
ON CONFLICT (key) DO NOTHING;
