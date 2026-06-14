"""Tests for autodev.sessions — fork, snapshot, branch, merge, time-travel diff."""
from pathlib import Path

import pytest

from autodev.knowledge_base import KnowledgeBase
from autodev.sessions import (
    DEFAULT_BRANCH,
    Snapshot,
    diff_snapshots,
    drop_branch,
    fork_session,
    list_branches,
    list_forks,
    merge_branch,
    take_snapshot,
)


# ── Branch ID migration sanity ─────────────────────────────────────────
class TestBranchMigration:
    def test_legacy_lessons_get_main_branch(self, tmp_path: Path):
        """Simulate a v0.3 db created BEFORE branch_id existed."""
        kb = KnowledgeBase(tmp_path / "kb.db")
        # Initialise schema WITHOUT running through the branch migration
        # by hand to mimic a v0.3 db.
        with kb._connect() as conn:  # noqa: SLF001
            conn.executescript(
                """
                CREATE TABLE lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    failure TEXT NOT NULL,
                    fix TEXT,
                    context TEXT,
                    applied_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """INSERT INTO lessons (pattern, failure, fix, context, created_at)
                   VALUES ('import_error', 'numpy', 'stdlib', 'x.py', '2024-01-01')"""
            )
        # Now run the normal initialize() — should ADD branch_id with
        # DEFAULT 'main' so legacy rows get main.
        kb.initialize()
        rows = kb.query_lessons(branch_id="main")
        assert len(rows) == 1
        assert rows[0]["pattern"] == "import_error"

    def test_query_lessons_filters_by_branch(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("a", "x", branch_id="main")
        kb.add_lesson("b", "y", branch_id="alpha")
        kb.add_lesson("c", "z", branch_id="beta")
        assert len(kb.query_lessons(branch_id="main")) == 1
        assert len(kb.query_lessons(branch_id="alpha")) == 1
        assert len(kb.query_lessons(branch_id="beta")) == 1
        assert len(kb.query_lessons(branch_id="ghost")) == 0

    def test_add_lesson_default_branch_is_main(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p", "f")
        rows = kb.query_lessons(branch_id="main")
        assert rows[0]["pattern"] == "p"


# ── fork_session ──────────────────────────────────────────────────────
class TestFork:
    def test_fork_creates_new_branch_with_inherited_lessons(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("import_error", "numpy", "stdlib", branch_id="main")
        snap = fork_session(kb, "alpha", reason="try creative fix")
        assert snap.branch_id == "alpha"
        assert snap.forked_from == "main"
        assert snap.lesson_count == 1
        lessons = kb.query_lessons(branch_id="alpha")
        # Should contain only alpha's lessons (the seeded one)
        assert len(lessons) == 1
        assert lessons[0]["pattern"] == "import_error"

    def test_fork_into_self_raises(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        with pytest.raises(ValueError, match="into itself"):
            fork_session(kb, "main")

    def test_fork_records_to_log(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        fork_session(kb, "alpha", reason="experiment")
        log = list_forks(kb)
        assert len(log) == 1
        assert log[0]["parent_branch"] == "main"
        assert log[0]["child_branch"] == "alpha"
        assert log[0]["reason"] == "experiment"

    def test_branch_isolation_after_fork(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("import_error", "numpy", branch_id="main")
        fork_session(kb, "alpha")
        # Add a divergent lesson to alpha; main should NOT see it.
        kb.add_lesson("syntax_error", "x", branch_id="alpha")
        assert len(kb.query_lessons(branch_id="alpha", pattern="")) == 2
        assert len(kb.query_lessons(branch_id="main", pattern="")) == 1

    def test_fork_chains(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("a", "1", branch_id="main")
        fork_session(kb, "alpha")
        fork_session(kb, "beta", parent_branch="alpha")
        log = list_forks(kb)
        assert len(log) == 2
        assert {f["child_branch"] for f in log} == {"alpha", "beta"}


# ── take_snapshot + diff_snapshots (time travel) ──────────────────────
class TestTimeTravel:
    def test_snapshot_captures_initial_state(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p1", "f1", branch_id="main")
        kb.add_lesson("p2", "f2", branch_id="main")
        snap = take_snapshot(kb, "main")
        assert isinstance(snap, Snapshot)
        assert snap.lesson_count == 2

    def test_diff_shows_added_lessons(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p1", "f1", branch_id="main")
        snap = take_snapshot(kb, "main")
        kb.add_lesson("p2", "f2", branch_id="main")
        kb.add_lesson("p3", "f3", branch_id="main")
        d = diff_snapshots(kb, snap, current_branch="main")
        assert len(d["added"]) == 2

    def test_diff_shows_no_changes(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p1", "f1", branch_id="main")
        snap = take_snapshot(kb, "main")
        d = diff_snapshots(kb, snap, current_branch="main")
        assert len(d["added"]) == 0
        assert len(d["removed"]) == 0
        assert d["unchanged_count"] == 1


# ── merge_branch ──────────────────────────────────────────────────────
class TestMerge:
    def test_merge_skills_duplicates(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p1", "f1", branch_id="main")  # shared
        fork_session(kb, "alpha")
        kb.add_lesson("p2", "f2", branch_id="alpha")  # divergent
        n = merge_branch(kb, "alpha", "main")
        assert n == 1
        rows = kb.query_lessons(branch_id="main")
        assert len(rows) == 2

    def test_merge_into_self_raises(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        with pytest.raises(ValueError, match="into itself"):
            merge_branch(kb, "main", "main")

    def test_merge_zero_when_all_dupes(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("p1", "f1", branch_id="main")
        fork_session(kb, "alpha")
        n = merge_branch(kb, "alpha", "main")
        assert n == 0


# ── drop_branch ────────────────────────────────────────────────────────
class TestDrop:
    def test_drop_removes_lessons(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        fork_session(kb, "alpha")
        kb.add_lesson("p1", "f", branch_id="alpha")
        n = drop_branch(kb, "alpha")
        assert n == 1
        assert kb.query_lessons(branch_id="alpha") == []

    def test_drop_main_blocks(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        with pytest.raises(ValueError, match="default"):
            drop_branch(kb, "main")


# ── list_branches ──────────────────────────────────────────────────────
class TestListBranches:
    def test_lists_empty_when_no_branches(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        # No lessons anywhere.
        assert list_branches(kb) == []

    def test_grouped_counts(self, tmp_path: Path):
        kb = KnowledgeBase(tmp_path / "kb.db")
        kb.initialize()
        kb.add_lesson("a", "1", branch_id="main")
        kb.add_lesson("b", "2", branch_id="main")
        fork_session(kb, "alpha")             # alpha seeds with 2 inherited
        kb.add_lesson("c", "3", branch_id="alpha")  # +1 divergent
        branches = list_branches(kb)
        by_id = {b["branch_id"]: b["lessons"] for b in branches}
        # main retains its originals; alpha has 2 seeded + 1 added.
        assert by_id["main"] == 2
        assert by_id["alpha"] == 3


# ── Default branch constant ────────────────────────────────────────────
class TestConstants:
    def test_default_branch_is_main(self):
        assert DEFAULT_BRANCH == "main"
