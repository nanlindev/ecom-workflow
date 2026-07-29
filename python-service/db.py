"""Idempotent SQL migration runner and connection helpers for ecom Postgres."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(os.getenv("MIGRATIONS_DIR", "/app/sql/migrations"))
if not MIGRATIONS_DIR.exists():
    MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "sql" / "migrations"


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    user = os.getenv("ECOM_POSTGRES_USER", "ecom")
    password = os.getenv("ECOM_POSTGRES_PASSWORD", "ecom")
    host = os.getenv("ECOM_POSTGRES_HOST", "ecom_postgres")
    port = os.getenv("ECOM_POSTGRES_PORT", "5432")
    db = os.getenv("ECOM_POSTGRES_DB", "ecom")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@contextmanager
def connect(*, row_factory=dict_row) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(database_url(), row_factory=row_factory)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations() -> list[str]:
    """Apply pending *.sql files in lexical order. Returns list of newly applied names."""
    if not MIGRATIONS_DIR.exists():
        logger.warning("Migrations directory missing: %s", MIGRATIONS_DIR)
        return []

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.info("No migration files in %s", MIGRATIONS_DIR)
        return []

    applied: list[str] = []
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version     TEXT PRIMARY KEY,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.commit()

            for path in files:
                version = path.name
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cur.fetchone():
                    logger.debug("Skip already-applied migration %s", version)
                    continue

                sql = path.read_text(encoding="utf-8")
                logger.info("Applying migration %s", version)
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
                    conn.commit()
                    applied.append(version)
                except Exception:
                    conn.rollback()
                    logger.exception("Migration failed: %s", version)
                    raise

    return applied


def ping_db() -> bool:
    """Return True if SELECT 1 succeeds."""
    with psycopg.connect(database_url(), connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
