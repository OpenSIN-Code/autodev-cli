"""SQLite knowledge base for lessons learned (SIN-Code Closed Learning Loop)."""
import sqlite3
from datetime import datetime
from pathlib import Path


class KnowledgeBase:
    """Persistent memory of failures and lessons — never repeat a mistake."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def initialize(self):
        """Create tables, run idempotent migrations, and ensure indexes.

        v0.4.0 introduced branch-scoped lessons for swarm time-travel
        sessions. Migration adds branch_id TEXT NOT NULL DEFAULT 'main'
        to pre-existing lessons tables; SQLite ALTER TABLE keeps the
        rows intact. The forks table is brand new (no migration needed).
        """
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    failure TEXT NOT NULL,
                    fix TEXT,
                    context TEXT,
                    applied_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_value REAL,
                    metric_delta REAL,
                    duration_seconds REAL,
                    success BOOLEAN,
                    diff TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_branch TEXT NOT NULL,
                    child_branch TEXT NOT NULL,
                    forked_at TEXT NOT NULL,
                    reason TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_lessons_pattern
                ON lessons(pattern);
            """)
            self._migrate_lessons_branch_id(conn)

    @staticmethod
    def _migrate_lessons_branch_id(conn: sqlite3.Connection) -> None:
        """Add branch_id column to lessons if missing (v0.4.0 migration)."""
        cols = [row[1] for row in conn.execute("PRAGMA table_info(lessons)").fetchall()]
        if "branch_id" not in cols:
            conn.execute(
                "ALTER TABLE lessons ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'main'"
            )
        # Index on branch_id for fast scoping.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_branch ON lessons(branch_id)"
        )

    def add_lesson(
        self, pattern: str, failure: str, fix: str = "", context: str = "",
        branch_id: str = "main",
    ) -> int:
        """Record a lesson from a failed experiment (scoped to branch)."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO lessons
                       (pattern, failure, fix, context, branch_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    pattern, failure, fix, context, branch_id,
                    datetime.now().isoformat(),
                ),
            )
            return cursor.lastrowid or 0

    def query_lessons(
        self, pattern: str = "", limit: int = 10, branch_id: str = "main",
    ) -> list[dict]:
        """Retrieve relevant lessons before attempting changes (branch-scoped)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            sql = (
                "SELECT * FROM lessons WHERE branch_id = ? "
                "AND (? = '' OR pattern LIKE ?) "
                "ORDER BY applied_count DESC, created_at DESC LIMIT ?"
            )
            cursor = conn.execute(
                sql, (branch_id, pattern, f"%{pattern}%", limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def record_experiment(
        self, metric_value: float, metric_delta: float, duration: float, success: bool, diff: str
    ):
        """Log an experiment result."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO experiments
                   (metric_value, metric_delta, duration_seconds, success, diff, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (metric_value, metric_delta, duration, success, diff, datetime.now().isoformat()),
            )

    def list_lessons(self) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM lessons ORDER BY created_at DESC LIMIT 50")
            return [dict(row) for row in cursor.fetchall()]

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            applied = conn.execute(
                "SELECT COALESCE(SUM(applied_count), 0) FROM lessons"
            ).fetchone()[0]
            return {"total": total, "applied": applied}

    def add_goal(self, description: str, priority: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO goals (description, priority, created_at) VALUES (?, ?, ?)",
                (description, priority, datetime.now().isoformat()),
            )
            return cursor.lastrowid or 0

    def clear(self):
        with self._connect() as conn:
            conn.executescript("""
                DELETE FROM lessons;
                DELETE FROM experiments;
            """)
