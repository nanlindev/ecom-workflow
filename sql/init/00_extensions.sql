-- Bootstrap for empty Postgres volume only (docker-entrypoint-initdb.d).
-- Full schema is applied idempotently by the sidecar migration runner
-- (sql/migrations/*.sql). This file enables extensions used by the schema.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
