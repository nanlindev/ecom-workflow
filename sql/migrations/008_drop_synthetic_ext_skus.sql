-- Drop synthetic SKUs created from SKU-less inventory_levels/update webhooks.

DELETE FROM inventory_levels WHERE sku LIKE 'ext-%';
DELETE FROM listings WHERE sku LIKE 'ext-%';
DELETE FROM products WHERE sku LIKE 'ext-%';
