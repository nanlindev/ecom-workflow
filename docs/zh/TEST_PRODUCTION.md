# 测试 / 生产模式

运行模式为 Postgres 中 **`config_main.mode`**（`test` | `production`）。Sidecar 每次请求重读配置。

## test 模式（默认）

```sql
-- config_main.mode = test
```

| 动作 | 行为 |
|------|------|
| 接入 / 写 PG | 正常 |
| LLM（定价、营销文案） | 执行 |
| 库存漂移 Slack | `slack_in_test=true` 时允许（默认） |
| 库存 live writeback | **跳过** → `writeback_status=skipped_test_mode` |
| 定价审批后价格回写 | **跳过** → `skipped_test_mode` |
| 营销邮件（Resend） | **跳过** → `send_status=skipped_test_mode` |
| Daily / Weekly Slack | 门控下跳过 |
| Error Handler Slack | 需 `mode=production` + 告警开关 |

用于 seed 脚本与链路验证，不碰线上店铺。

## production 模式

```sql
UPDATE config_main SET value = 'production' WHERE key = 'mode';
```

| 动作 | 门控 |
|------|------|
| 库存 live writeback | `writeback_enabled=true` + 从渠道凭证（`WOO_*` 或 `SHOPIFY_ADMIN_*`） |
| 价格 live writeback | Slack **Approve**（或其它审批入口）+ `writeback_enabled=true` + `price_writeback_channels` + 渠道凭证 |
| 漂移 Slack | `inventory_drift_enabled` + `slack_enabled` |
| 定价 Slack | `pricing_alert_enabled` |
| 营销邮件 | `config_marketing.enabled` + `send_email_in_test=false` |
| Daily / Weekly Slack | `daily_summary_enabled` / `weekly_summary_enabled` |
| Keepalive 告警 | `keepalive_alert_enabled` |

## writeback_status 取值

库存 sync 与定价 action 返回：

| 值 | 含义 |
|----|------|
| `none` | 无漂移 / 未尝试回写 |
| `skipped_test_mode` | `mode=test` |
| `skipped_disabled` | `writeback_enabled=false` |
| `applied` | 至少一个渠道 API 写成功 |
| `applied_sot_only` | 仅 PG SoT 对齐；无 live API（缺凭证或 sot-only） |
| `partial` | 多渠道部分成功 |
| `failed` | Live API 错误 |

渠道明细见 `channel_writebacks[].live_status`。

## P3b 环境变量（live writeback）

```bash
WOO_BASE_URL=...
WOO_CONSUMER_KEY=...
WOO_CONSUMER_SECRET=...

SHOPIFY_ADMIN_ACCESS_TOKEN=...
SHOPIFY_LOCATION_ID=...
SHOPIFY_SHOP_DOMAIN=...
```

## 上线步骤

1. `mode=test` → 跑 seed → 核对 PG + Slack 测试告警
2. 配置渠道凭证 → 隔离 demo 店铺设 `mode=production`
3. 回滚：立即改回 `mode=test`（停 writeback，接入仍可跑）

见 [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)、[CREDENTIALS.md](CREDENTIALS.md)。
