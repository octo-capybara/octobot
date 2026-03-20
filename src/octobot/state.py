from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS analyzed_tickets (
    ticket_id   TEXT PRIMARY KEY,
    analyzed_at TEXT NOT NULL,
    comment_id  TEXT,
    status      TEXT NOT NULL DEFAULT 'analyzed'
);
"""


class StateDB:
    def __init__(self, db_path: str):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._init()

    def _init(self):
        with self._conn() as conn:
            conn.execute(CREATE_TABLE)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def is_analyzed(self, ticket_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM analyzed_tickets WHERE ticket_id = ? AND status = 'analyzed'",
                (ticket_id,),
            ).fetchone()
            return row is not None

    def get_record(self, ticket_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM analyzed_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            return dict(row) if row else None

    def save(self, ticket_id: str, comment_id: str | None, status: str = "analyzed"):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO analyzed_tickets (ticket_id, analyzed_at, comment_id, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    analyzed_at = excluded.analyzed_at,
                    comment_id  = excluded.comment_id,
                    status      = excluded.status
                """,
                (ticket_id, datetime.utcnow().isoformat(), comment_id, status),
            )

    def mark_error(self, ticket_id: str):
        self.save(ticket_id, None, status="error")

    def delete(self, ticket_id: str) -> bool:
        """Remove a ticket from the state. Returns True if a row was deleted."""
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM analyzed_tickets WHERE ticket_id = ?", (ticket_id,)
            )
            return cursor.rowcount > 0

    def summary(self) -> dict:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                        AS total,
                    SUM(status = 'analyzed')                       AS analyzed,
                    SUM(status = 'error')                          AS errors,
                    MAX(CASE WHEN status = 'analyzed'
                             THEN analyzed_at END)                 AS last_analyzed_at,
                    (SELECT ticket_id FROM analyzed_tickets
                     WHERE status = 'analyzed'
                     ORDER BY analyzed_at DESC LIMIT 1)            AS last_ticket
                FROM analyzed_tickets
            """).fetchone()
            return dict(row)

    def recent(self, limit: int = 10) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM analyzed_tickets ORDER BY analyzed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def all_records(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM analyzed_tickets ORDER BY analyzed_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
