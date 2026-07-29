-- P1 notification / returns rule seeds (idempotent).

INSERT INTO config_notifications (key, value, description) VALUES
    ('error_alert_enabled', 'true', 'Slack on Error Handler when mode=production'),
    ('inventory_drift_enabled', 'true', 'Slack when inventory channels drift'),
    ('order_anomaly_enabled', 'true', 'Slack when order anomalies detected'),
    ('returns_review_enabled', 'true', 'Slack for returns needing manual review')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_inventory (key, value, description) VALUES
    ('slave_channels', 'woocommerce', 'Comma-separated slave channels for writeback')
ON CONFLICT (key) DO NOTHING;

INSERT INTO config_main (key, value, description) VALUES
    ('returns_max_auto_approve_amount', '50', 'Max refund amount for auto_approve'),
    ('returns_max_days', '30', 'Max days since order for auto_approve'),
    ('demo_store_key', 'demo-shopify', 'Default demo store_key for Scenario A')
ON CONFLICT (key) DO NOTHING;
