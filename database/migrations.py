from __future__ import annotations

from peewee import SqliteDatabase


def _column_exists(db: SqliteDatabase, table: str, column: str) -> bool:
    rows = db.execute_sql(f"PRAGMA table_info('{table}')").fetchall()
    return any(row[1] == column for row in rows)


def _index_exists(db: SqliteDatabase, index_name: str) -> bool:
    rows = db.execute_sql("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,)).fetchall()
    return bool(rows)


def run_migrations(db: SqliteDatabase) -> None:
    if not _column_exists(db, "payment", "idempotency_key"):
        db.execute_sql("ALTER TABLE payment ADD COLUMN idempotency_key VARCHAR(255)")
    if not _index_exists(db, "payment_idempotency_key_idx"):
        db.execute_sql("CREATE UNIQUE INDEX payment_idempotency_key_idx ON payment(idempotency_key)")
    if not _column_exists(db, "user", "intro_seen"):
        db.execute_sql("ALTER TABLE user ADD COLUMN intro_seen INTEGER DEFAULT 0")
    if not _column_exists(db, "user", "free_quick_used"):
        db.execute_sql("ALTER TABLE user ADD COLUMN free_quick_used INTEGER DEFAULT 0")
