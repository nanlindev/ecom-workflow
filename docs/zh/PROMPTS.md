# Prompt 管理

LLM Prompt 位于 `prompts/`，Markdown + YAML frontmatter。Sidecar 读文件 — **不**硬编码在 n8n。

## 文件

```text
prompts/
├── pricing_recommend.md
├── marketing_copy.md
└── competitor_parse.md
```

Postgres `prompt_registry` 为运维镜像（无密钥）。

## Frontmatter 示例

```markdown
---
version: pricing_recommend-v1
model: deepseek-chat
output_format: json
---

正文含 {sku} 等占位符...
```

## 端点

| 端点 | 文件 | `prompt_key` |
|------|------|--------------|
| `POST /pricing/recommend` | `pricing_recommend.md` | `pricing_recommend` |
| `POST /marketing/copy` | `marketing_copy.md` | `marketing_copy` |
| `POST /competitors/parse` | `competitor_parse.md` | `competitor_parse` |

列表：

```bash
curl http://localhost:8003/prompts
```

## 加载方式

`python-service/prompt_loader.py` 读 `./prompts`（Docker 只读挂载）。`prompt_registry` 仅元数据。

## 修改 Prompt

1. 编辑 `.md`；frontmatter 中 bump `version`。
2. 重启 sidecar：`docker compose -f docker/compose.yml restart ecom_python_ai`
3. 可选：更新 `prompt_registry.version` 行。
4. 在 Langfuse 中确认新版本 metadata。

一般无需改 n8n JSON。

见 [WORKFLOWS.md](WORKFLOWS.md)（Pricing Engine、Marketing Orchestrator、Competitor Crawl）。
