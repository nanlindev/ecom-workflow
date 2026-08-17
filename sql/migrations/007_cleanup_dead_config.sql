-- Remove dead config_pricing.auto_apply; normalize email_provider=resend.

DELETE FROM config_pricing WHERE key = 'auto_apply';

COMMENT ON TABLE config_pricing IS 'Pricing engine strategy and writeback channel flags';

UPDATE config_pricing
SET description = 'Comma-separated channels for live price writeback on Slack Approve (production + writeback_enabled)'
WHERE key = 'price_writeback_channels';

UPDATE config_notifications
SET value = 'resend',
    description = 'Email provider used by n8n Marketing Orchestrator (Resend HTTP)'
WHERE key = 'email_provider';
