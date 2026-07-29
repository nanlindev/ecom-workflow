# DEMO 场景 A（P1 信任路径）

导入工作流并启动 compose 后的验收清单。详见英文版 [DEMO_SCENARIO_A.md](../en/DEMO_SCENARIO_A.md)。

```bash
docker compose -f docker/compose.yml --env-file .env up -d --build
python3 scripts/seed_demo_scenario_a.py
```

期望：`TEE-BLACK-M` 库存进 PG；sync 在 test 下 `writeback_status=skipped_test_mode`；订单 `5001` 状态可见；退货 `R-9001` → `manual_review`。
