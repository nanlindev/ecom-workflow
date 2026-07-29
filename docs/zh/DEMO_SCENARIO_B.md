# DEMO 场景 B（P2 智能路径）

P1 场景 A 拿到 `store_id` 且 sidecar 健康后执行。详见 [DEMO_SCENARIO_B.md](../en/DEMO_SCENARIO_B.md)。

```bash
export ECOM_DEMO_STORE_ID=<uuid>
python3 scripts/seed_demo_scenario_b.py
```

期望：竞品价快照 → 定价建议进 Slack（可 Approve/Reject）；弃购 enrollment 写入且 test 下 `skipped_test_mode` 不发信。
