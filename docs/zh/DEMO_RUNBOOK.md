# 演示手册

ecom-workflow P0–P3 作品集演示脚本。先用 `mode=test`；live writeback 需隔离 Slack 频道与 demo 店铺。

相关：[SHOWCASE.md](../SHOWCASE.md) · [TEST_PRODUCTION.md](TEST_PRODUCTION.md) · [INSTALL.md](INSTALL.md) · [RUN_EXAMPLE.md](RUN_EXAMPLE.md)

---

## 0. 预检

- [ ] `docker compose up` 健康；`/health` → `"database":"ok"`
- [ ] 13 条工作流已导入；Error Workflow → **Ecom Error Handler**
- [ ] Slack 机器人在 demo 频道；Interactivity → `/webhook/ecom-slack-interactions`
- [ ] PG：`config_main.mode=test`
- [ ] OBS：Jaeger + Langfuse；`NO_PROXY` 含 `ecom_python_ai`

---

## 场景 A — 库存 + 订单（P1，必做）

**信任路径：** 平台接入 → 漂移检测 → PG SoT。

```bash
python3 scripts/seed_demo_scenario_a.py
```

### 检查

- [ ] `inventory_levels` 有 `sku-managed-1`（Shopify master）
- [ ] Sync：`has_drift=true`、`writeback_status=skipped_test_mode`
- [ ] 订单 `5001`；退货 `R-9001` → `manual_review`
- [ ] 可选 Slack 漂移卡片

详见 [DEMO_SCENARIO_A.md](DEMO_SCENARIO_A.md)

**状态：** [ ] 完成

---

## 场景 B — 定价 + 邮件（P2，必做）

**亮点路径：** 竞品价 → Slack 审批。

```bash
export ECOM_DEMO_STORE_ID=<场景 A 的 store_id>
python3 scripts/seed_demo_scenario_b.py
```

### 检查

- [ ] `pricing_recommendations` 为 `pending`
- [ ] 执行 **Ecom Pricing Engine** → Slack Approve/Reject
- [ ] 点击 → **Ecom Slack Actions** → `approved` / `rejected`
- [ ] test：`writeback_status=skipped_test_mode`；营销 `send_status=skipped_test_mode`

详见 [DEMO_SCENARIO_B.md](DEMO_SCENARIO_B.md)

**状态：** [ ] 完成

---

## 场景 C — Woo 接入 + live writeback（P3/P3b）

**有凭证时演示：** Woo webhook 或 P3 seed。

```bash
python3 scripts/seed_demo_scenario_p3.py
```

### test 模式

- [ ] Woo 产品接入成功；sync 显示漂移
- [ ] `writeback_status=skipped_test_mode`

### production 冒烟（仅隔离店铺）

1. `.env` 配置 `WOO_*` 或 `SHOPIFY_ADMIN_ACCESS_TOKEN` + `SHOPIFY_LOCATION_ID`
2. `UPDATE config_main SET value='production' WHERE key='mode';`
3. 重跑 sync，或对定价建议点 Slack Approve（生产下会 live 写回渠道）
4. 期望 `writeback_status=applied` 或 `applied_sot_only`
5. 在 Woo/Shopify 后台核对库存或价格
6. 回滚：`mode=test`

**状态：** [ ] 完成

---

## 可选 — Daily / Weekly / Keepalive（P3）

| 工作流 | 手动执行 | test 期望 |
|--------|----------|-----------|
| Daily Summary | Execute Workflow | 生成指标；跳过 Slack |
| Weekly Summary | Execute Workflow | 同上 |
| Health Keepalive | Execute Workflow | PG 正常；test 不告警 |

`mode=production` + 通知开关后可收 Slack 摘要。

---

## 可观测性

| 检查 | 方法 |
|------|------|
| Langfuse | 标签 `ecom-workflow`；场景 B 后看定价 generation |
| Jaeger | sync/定价时段的 `n8n-ecom-ai-service` |
| correlation_id | Slack 漂移卡或 seed 输出 |

---

## 演示后

- [ ] `config_main.mode` → `test`
- [ ] 恢复 demo 店铺上手动改的库存/价格

门控参考：[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)。
