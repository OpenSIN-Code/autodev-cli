"""Tests for SQLite knowledge base."""
import sqlite3
from pathlib import Path

from autodev.knowledge_base import KnowledgeBase


class TestKnowledgeBase:
    def test_initialize_creates_tables(self, temp_db: Path):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        with sqlite3.connect(temp_db) as conn:
            table_names = {t[0] for t in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert {"lessons", "experiments", "goals"}.issubset(table_names)

    def test_add_and_query_lesson(self, temp_db: Path):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        lesson_id = kb.add_lesson(
            pattern="import_error",
            failure="ModuleNotFoundError: numpy",
            fix="Use built-in libraries",
            context="test.py",
        )
        assert lesson_id > 0
        lessons = kb.query_lessons(pattern="import")
        assert len(lessons) == 1
        assert lessons[0]["pattern"] == "import_error"
        assert lessons[0]["failure"] == "ModuleNotFoundError: numpy"

    def test_query_lessons_with_pattern(self, temp_db: Path, sample_lessons):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        for lesson in sample_lessons:
            kb.add_lesson(**lesson)
        lessons = kb.query_lessons(pattern="import")
        assert len(lessons) == 1
        assert lessons[0]["pattern"] == "import_error"
        all_lessons = kb.query_lessons(limit=10)
        assert len(all_lessons) == 3

    def test_record_experiment(self, temp_db: Path):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        kb.record_experiment(
            metric_value=3.8, metric_delta=0.4, duration=120.5,
            success=True, diff="src/test.py: optimized loop",
        )
        with sqlite3.connect(temp_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
            assert count == 1

    def test_list_lessons(self, temp_db: Path, sample_lessons):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        for lesson in sample_lessons:
            kb.add_lesson(**lesson)
        lessons = kb.list_lessons()
        assert len(lessons) == 3
        assert all("id" in lesson for lesson in lessons)
        assert all("pattern" in lesson for lesson in lessons)

    def test_stats(self, temp_db: Path, sample_lessons):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        for lesson in sample_lessons:
            kb.add_lesson(**lesson)
        stats = kb.stats()
        assert stats["total"] == 3
        assert stats["applied"] == 0

    def test_add_goal(self, temp_db: Path):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        goal_id = kb.add_goal("Optimize API latency", priority=8)
        assert goal_id > 0
        with sqlite3.connect(temp_db) as conn:
            goals = conn.execute("SELECT * FROM goals").fetchall()
            assert len(goals) == 1
            assert goals[0][1] == "Optimize API latency"
            assert goals[0][2] == 8

    def test_clear(self, temp_db: Path, sample_lessons):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        for lesson in sample_lessons:
            kb.add_lesson(**lesson)
        kb.record_experiment(1.0, 0.5, 60.0, True, "test")
        kb.clear()
        assert kb.stats()["total"] == 0

    def test_idempotent_initialize(self, temp_db: Path):
        kb = KnowledgeBase(temp_db)
        kb.initialize()
        kb.initialize()
        kb.add_lesson("test", "test failure", "test fix")
        assert len(kb.list_lessons()) == 1
