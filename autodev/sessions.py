"""Time-travel sessions: fork, snapshot, branch the agent's lesson state.

Inspired by SIN-Code M5 (Replayable Experiments): every session is a
*branch* of the SQLite lessons table. Forks inherit their parent's
lessons at fork time, then accumulate their own diverging lessons
during the new branch's experiments. Merge replays the fork log into
a single chronological ledger for retrospection.

Docs: docs/SESSIONS.md
"""
from dataclasses import dataclass
from datetime import datetime

from .knowledge_base import KnowledgeBase

DEFAULT_BRANCH = "main"


@dataclass
class Snapshot:
    """A point-in-time capture of a session's lesson state."""
    branch_id: str
    forked_from: str | None
    forked_at: str
    reason: str
    lesson_count: int
    lesson_ids: list[int]


# ── Session helpers (thin layer over KnowledgeBase) ────────────────────
def fork_session(
    kb: KnowledgeBase,
    new_branch: str,
    parent_branch: str = DEFAULT_BRANCH,
    reason: str = "",
) -> Snapshot:
    """Create a new branch, inheriting the parent's lesson IDs at fork time.

    The parent's lessons remain in `parent_branch` (read-only base).
    New lessons added under `new_branch` represent divergent learnings.

    Records a row in the `forks` log so you can replay the family tree.
    """
    if new_branch == parent_branch:
        raise ValueError(f"refusing to fork {parent_branch!r} into itself")

    kb.initialize()  # idempotent; ensures migration
    with kb._connect() as conn:  # noqa: SLF001 — internal but OK here
        # Capture parent lesson IDs (zero-copy `inheritance`).
        cursor = conn.execute(
            "SELECT id FROM lessons WHERE branch_id = ? ORDER BY id",
            (parent_branch,),
        )
        parent_ids = [row[0] for row in cursor.fetchall()]
        forked_at = datetime.now().isoformat()
        # Record fork in log.
        conn.execute(
            """INSERT INTO forks (parent_branch, child_branch, forked_at, reason)
               VALUES (?, ?, ?, ?)""",
            (parent_branch, new_branch, forked_at, reason),
        )
    # Seed the new branch with the parent's lessons (so query_lessons
    # on the new branch sees inherited knowledge).
    _seed_branch_with_parent_lessons(kb, new_branch, parent_branch)
    return Snapshot(
        branch_id=new_branch,
        forked_from=parent_branch,
        forked_at=forked_at,
        reason=reason,
        lesson_count=len(parent_ids),
        lesson_ids=parent_ids,
    )


def _seed_branch_with_parent_lessons(
    kb: KnowledgeBase, target_branch: str, source_branch: str,
) -> None:
    """Copy parent's lessons into target_branch (as if they were freshly learned).

    The pattern/failure/fix are preserved; ids are re-generated so the
    new branch owns its rows. Future divergent learnings only modify
    the target branch's rows.
    """
    rows = kb.query_lessons(pattern="", limit=10_000, branch_id=source_branch)
    for row in rows:
        kb.add_lesson(
            pattern=row["pattern"],
            failure=row["failure"],
            fix=row.get("fix") or "",
            context=row.get("context") or "",
            branch_id=target_branch,
        )


def list_forks(kb: KnowledgeBase) -> list[dict]:
    """Return the fork log (parent → child, when, why)."""
    kb.initialize()
    with kb._connect() as conn:  # noqa: SLF001
        conn.row_factory = __import__("sqlite3").Row
        cursor = conn.execute(
            "SELECT * FROM forks ORDER BY forked_at DESC, id DESC"
        )
        return [dict(row) for row in cursor.fetchall()]


def list_branches(kb: KnowledgeBase) -> list[dict]:
    """All distinct branch_ids with lesson counts."""
    kb.initialize()
    with kb._connect() as conn:  # noqa: SLF001
        rows = conn.execute(
            "SELECT branch_id, COUNT(*) as lessons FROM lessons "
            "GROUP BY branch_id ORDER BY lessons DESC"
        ).fetchall()
    return [{"branch_id": r[0], "lessons": r[1]} for r in rows]


def merge_branch(
    kb: KnowledgeBase,
    source_branch: str,
    target_branch: str = DEFAULT_BRANCH,
) -> int:
    """Replay any lessons unique to source_branch into target_branch.

    Returns the number of lessons merged. Conflict policy: skip
    duplicates (same pattern+failure pair already in target = skip).
    Source branch is left intact (you can audit it later or drop it).
    """
    if source_branch == target_branch:
        raise ValueError(f"refusing to merge {source_branch!r} into itself")
    source_rows = kb.query_lessons(pattern="", limit=10_000, branch_id=source_branch)
    target_rows = kb.query_lessons(pattern="", limit=10_000, branch_id=target_branch)
    target_keys = {(r["pattern"], r["failure"]) for r in target_rows}
    merged = 0
    for row in source_rows:
        key = (row["pattern"], row["failure"])
        if key in target_keys:
            continue
        kb.add_lesson(
            pattern=row["pattern"],
            failure=row["failure"],
            fix=row.get("fix") or "",
            context=row.get("context") or "",
            branch_id=target_branch,
        )
        merged += 1
    return merged


def drop_branch(kb: KnowledgeBase, branch_id: str) -> int:
    """Delete all lessons for branch_id (irreversible). Keeps the forks log."""
    if branch_id == DEFAULT_BRANCH:
        raise ValueError("refusing to drop the default 'main' branch")
    kb.initialize()
    with kb._connect() as conn:  # noqa: SLF001
        cursor = conn.execute(
            "DELETE FROM lessons WHERE branch_id = ?", (branch_id,),
        )
        return cursor.rowcount or 0


# ── Snapshot helpers for session-forking "time travel" ──────────────────
def take_snapshot(kb: KnowledgeBase, branch_id: str = DEFAULT_BRANCH) -> Snapshot:
    """Capture the current lesson state of a branch (point-in-time)."""
    kb.initialize()
    rows = kb.query_lessons(pattern="", limit=10_000, branch_id=branch_id)
    return Snapshot(
        branch_id=branch_id,
        forked_from=None,
        forked_at=datetime.now().isoformat(),
        reason="snapshot",
        lesson_count=len(rows),
        lesson_ids=[r["id"] for r in rows],
    )


def diff_snapshots(
    kb: KnowledgeBase, snap: Snapshot, current_branch: str = DEFAULT_BRANCH,
) -> dict:
    """Time-travel diff: what changed between snap and current state?"""
    current_rows = kb.query_lessons(pattern="", limit=10_000, branch_id=current_branch)
    snap_ids = set(snap.lesson_ids)

    # Stable pattern+failure keys for the lesson set.
    current_keys = {(r["pattern"], r["failure"]): r for r in current_rows}
    snap_rows = kb.query_lessons(pattern="", limit=10_000, branch_id=snap.branch_id)
    snap_keys = {(r["pattern"], r["failure"]): r for r in snap_rows if r["id"] in snap_ids}

    new_keys = set(current_keys) - set(snap_keys)
    dropped_keys = set(snap_keys) - set(current_keys)
    return {
        "branch": current_branch,
        "snapshot_branch": snap.branch_id,
        "snapshot_at": snap.forked_at,
        "added": [current_keys[k] for k in new_keys],
        "removed": [snap_keys[k] for k in dropped_keys],
        "unchanged_count": len(set(current_keys) & set(snap_keys)),
    }
