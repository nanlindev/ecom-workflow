# Sidecar deploy notes

See bilingual guides:

- [docs/en/DEPLOY.md](../docs/en/DEPLOY.md)
- [docs/zh/DEPLOY.md](../docs/zh/DEPLOY.md)

Compose entrypoint from repo root:

```bash
docker compose -f docker/compose.yml --env-file .env up -d --build
```
