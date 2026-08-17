# 数据库设置

独立 **`ecom_postgres`** — 与 n8n 库分离。存放库存、订单、定价与 config 开关（**不含密钥**）。

## 目录

| 路径 | 作用 |
|------|------|
| `sql/init/` | 首次卷仅装扩展 |
| `sql/migrations/*.sql` | 幂等 schema + 种子数据 |
| Sidecar 启动 | 执行待迁移 → `schema_migrations` 表 |

重复 `docker compose up` 安全。

## 启动

```bash
docker compose -f docker/compose.yml --env-file .env up -d
curl http://localhost:8003/health   # 期望 "database":"ok"
```

## config_* 表（无密钥）

| 表 | 示例键 |
|----|--------|
| `config_main` | `mode`、`project_tag`、`demo_woo_store_key` |
| `config_inventory` | `master_channel`、`slave_channels`、`writeback_enabled`、`writeback_align_sot` |
| `config_pricing` | `enabled`、`min_margin_pct`、`price_writeback_channels`、`demo_pricing_skus` |
| `config_marketing` | `enabled`、`abandon_cart_enabled`、`send_email_in_test` |
| `config_notifications` | `slack_enabled`、`daily_summary_enabled`、`keepalive_alert_enabled` |

完整键：[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)。

## 核心业务表

`stores`、`products`、`inventory_levels`、`orders`、`returns`、`pricing_recommendations`、`competitor_snapshots`、`customers`、`marketing_enrollments`、`audit_logs`、`error_logs`、`prompt_registry`。

## 查看

```bash
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT key, value FROM config_main;"
docker compose -f docker/compose.yml exec -T ecom_postgres \
  psql -U ecom -d ecom -c "SELECT version FROM schema_migrations ORDER BY version;"
```

## 运行时改配置

直接 UPDATE `config_*` — 工作流每次执行重读（无需重启）。

```sql
UPDATE config_main SET value = 'production' WHERE key = 'mode';
```

## 迁移失败

查 `docker compose logs ecom_python_ai`。修复 SQL、重建镜像、重启 — 迁移为幂等。

见 [DEPLOY.md](DEPLOY.md)、[TEST_PRODUCTION.md](TEST_PRODUCTION.md)。
