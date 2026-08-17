# Prompt management

LLM prompts live in `prompts/` as markdown with YAML frontmatter. Sidecar loads files — **not** hardcoded in n8n.

## Files

```text
prompts/
├── pricing_recommend.md
├── marketing_copy.md
└── competitor_parse.md
```

Registry mirror in Postgres `prompt_registry` (no secrets).

## Frontmatter example

```markdown
---
version: pricing_recommend-v1
model: deepseek-chat
output_format: json
---

Prompt body with {sku} placeholders...
```

## Endpoints

| Endpoint | Prompt file | `prompt_key` |
|----------|-------------|--------------|
| `POST /pricing/recommend` | `pricing_recommend.md` | `pricing_recommend` |
| `POST /marketing/copy` | `marketing_copy.md` | `marketing_copy` |
| `POST /competitors/parse` | `competitor_parse.md` | `competitor_parse` |

List all:

```bash
curl http://localhost:8003/prompts
```

## Loading

`python-service/prompt_loader.py` reads `./prompts` (Docker mount `:ro`). Postgres `prompt_registry` is ops metadata only.

## Change a prompt

1. Edit `.md`; bump `version` in frontmatter.
2. Restart sidecar: `docker compose -f docker/compose.yml restart ecom_python_ai`
3. Update matching `prompt_registry.version` row (optional but recommended).
4. Confirm new version in Langfuse generation metadata.

No n8n JSON change required unless workflow passes new variables.

See [WORKFLOWS.md](WORKFLOWS.md) (Pricing Engine, Marketing Orchestrator, Competitor Crawl).
