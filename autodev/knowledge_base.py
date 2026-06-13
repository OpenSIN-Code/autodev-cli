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
        """Create tables if they don't exist."""
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

                CREATE INDEX IF NOT EXISTS idx_lessons_pattern
                ON lessons(pattern);
            """)

    def add_lesson(self, pattern: str, failure: str, fix: str = "", context: str = "") -> int:
        """Record a lesson from a failed experiment."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO lessons (pattern, failure, fix, context, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (pattern, failure, fix, context, datetime.now().isoformat()),
            )
            return cursor.lastrowid or 0

    def query_lessons(self, pattern: str = "", limit: int = 10) -> list[dict]:
        """Retrieve relevant lessons before attempting changes."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if pattern:
                cursor = conn.execute(
                    "SELECT * FROM lessons WHERE pattern LIKE ? ORDER BY applied_count DESC LIMIT ?",
                    (f"%{pattern}%", limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM lessons ORDER BY created_at DESC LIMIT ?", (limit,)
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
