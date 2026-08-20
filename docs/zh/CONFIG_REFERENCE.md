# 配置参考

运行时业务配置在 Postgres **`config_*`** 表。Sidecar 每次请求加载。**不含密钥** — 仅开关与阈值。

运行时修改：

```sql
UPDATE config_inventory SET value = 'shopify,woocommerce' WHERE key = 'slave_channels';
```

## config_main

| 键 | 默认 | 作用 |
|----|------|------|
| `mode` | `test` | `test`：跳过 live writeback / 门控摘要 Slack。`production`：启用副作用 |
| `project_tag` | `ecom-workflow` | Langfuse / 工作流标签 |
| `demo_woo_store_key` | `demo-woocommerce` | Woo webhook 未带头时的默认 `store_key` |

## config_inventory

| 键 | 默认 | 作用 |
|----|------|------|
| `master_channel` | `shopify` | 库存权威渠道 |
| `slave_channels` | `woocommerce` | 接收漂移回写的从渠道（逗号分隔） |
| `safety_stock_default` | `5` | 默认安全库存 |
| `writeback_enabled` | `true` | 生产模式下允许 live 回写 |
| `writeback_align_sot` | `true` | live 尝试后对齐 PG `inventory_levels` |
| `inventory_drift_enabled` | `true` | 门控通过时漂移 Slack |

## config_pricing

| 键 | 默认 | 作用 |
|----|------|------|
| `enabled` | `true` | 定价引擎开关 |
| `min_margin_pct` | `15` | 最低毛利率 |
| `price_writeback_channels` | `shopify,woocommerce` | Slack Approve 后 live 价格回写渠道 |
| `demo_pricing_sku` | `sku-managed-1` | 默认主 SKU |
| `demo_pricing_skus` | `sku-managed-1,SNOWBOARD-LIQUID` | Cron 多 SKU（逗号分隔；多渠道可见演示品） |
| `competitor_urls` | JSON 数组 | Competitor Crawl 白名单 URL |

## config_marketing

| 键 | 默认 | 作用 |
|----|------|------|
| `enabled` | `true` | 营销编排开关 |
| `abandon_cart_enabled` | `true` | 弃购序列 |
| `vip_enabled` | `true` | VIP 触达 |
| `send_email_in_test` | `false` | test 模式不发真实邮件 |

## config_notifications

| 键 | 默认 | 作用 |
|----|------|------|
| `slack_enabled` | `true` | Slack 总开关 |
| `slack_in_test` | `true` | test 模式允许运维/漂移 Slack |
| `email_provider` | `resend` | 运维标签；n8n Marketing Orchestrator 实际用 Resend HTTP |
| `daily_summary_enabled` | `true` | `mode=production` 时 Daily Slack |
| `weekly_summary_enabled` | `true` | `mode=production` 时 Weekly Slack |
| `keepalive_alert_enabled` | `true` | Keepalive 失败时 Slack（同一渠道失败 1h 内不重复告警） |
| `inventory_drift_enabled` | `true` | 漂移告警 |
| `pricing_alert_enabled` | `true` | 定价建议 Slack |

## API 查看

```bash
curl http://localhost:8003/config
```

返回嵌套 config + 派生 `mode` / `master_channel`（无密钥）。

见 [TEST_PRODUCTION.md](TEST_PRODUCTION.md)、[DB_SETUP.md](DB_SETUP.md)。
