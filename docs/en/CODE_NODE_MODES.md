# Code node modes

n8n Code v2 modes used by `scripts/generate_workflows.py`:

| Mode | API | Use when |
|------|-----|----------|
| `runOnceForAllItems` | `$input.all()`, `$('Node').all()` | Config merge, aggregates, 1→N expand |
| `runOnceForEachItem` | `$input.item` | Per-event transforms, error handlers |

## Must use `runOnceForAllItems`

| Pattern | Workflow | Why |
|---------|----------|-----|
| Load / merge config from sidecar GET | Summaries, Keepalive, Pricing | Single config object |
| Build drift Slack text from full sync body | Inventory Sync | One alert per run |
| Aggregate ops metrics | Daily / Weekly Summary | One digest item |

Generator constant: `BATCH_CODE_MODE = "runOnceForAllItems"`.

## Must use `runOnceForEachItem`

| Pattern | Workflow | Why |
|---------|----------|-----|
| All `Handle * Error` nodes | All | `$input.item.error` |
| Prepare webhook / sidecar body | Ingest, Sync | One webhook event |
| Parse Slack interaction payload | Slack Actions | One button click |
| Build per-SKU sidecar POST | Ingest dispatch | Per platform event |

Default in `code_node()`: `runOnceForEachItem`.

## Pitfalls

1. Using `$('Some Node').item` inside EachItem when you need `.all()` → fan-out bugs.
2. Error handlers must stay EachItem — never batch-merge error items silently.
3. After UI export, re-run generators instead of hand-editing modes.

See [WORKFLOWS.md](WORKFLOWS.md), generator header in `scripts/generate_workflows.py`.
