# Time-Travel Sessions

> "Lessons are not the truth — they're hypotheses your past self
> believed. Fork them, diff them, decide which branch won."

## Das Problem

A single agent accumulates lessons along a single timeline. When you
want to try "what if I had used a different verification strategy?",
you cannot rewind the lesson state. You either override the past with
new learnings (destructive) or fork an entirely new agent (no shared
memory).

**SIN-Code time-travel sessions** solve this with **branch-scoped
lessons**: every lesson in the SQLite KB belongs to a `branch_id`.
Forking a session creates a new branch that inherits the parent's
lessons at fork time, then accumulates its own diverging lessons.
Merging replays divergent lessons back into any other branch.

## Architecture

```
                             ┌───────┐
                             │ main  │  ──┐
                             └───┬───┘    │
                  fork_session  │         │
                                 │         │ diverging agents
                                 ▼         │
                    ┌──────────────────────┐│
                    │ alpha (try creative) ││
                    │ inherits 4 lessons   ││
                    │ + adds 2 unique      ││
                    └────┬─────────────────┘│
                         │                  │
                merge_branch                │
                         │                  │
                         ▼                  │
                    ┌───────────┐           │
                    │ main      │◀──────────┘
                    │ now: 4+1  │
                    └───────────┘
```

## Konzept: Snapshot, Fork, Diff, Merge

### Snapshot
Erfasst den Lesson-Stand einer Branch zu einem Zeitpunkt.

```bash
autodev session snapshot --branch main --json
# {"ok": true, "branch": "main", "at": "2026-06-14T10:30:00",
#  "lesson_count": 12}
```

### Fork
Erzeugt einen neuen Branch, der die Lessons des Parents erbt.

```bash
autodev session fork --into creative-hyp --from main --reason "try T=0.9" --json
# {"ok": true, "branch_id": "creative-hyp", "forked_from": "main",
#  "inherited_lessons": 12}
```

### Diff
Zeigt, was sich in einer Branch seit dem letzten Fork verändert hat.

```bash
autodev session diff --branch creative-hyp --json
# {"ok": true, "added": [...], "removed": [...], "unchanged_count": 12}
```

### Merge
Replays die diverging Lessons zurück in eine andere Branch.

```bash
autodev session merge --from creative-hyp --into main --json
# {"ok": true, "merged_lessons": 2, "source": "creative-hyp", "target": "main"}
```

### Drop
Verwirft eine Branch irreversibel (default 'main' ist geschützt).

```bash
autodev session drop --branch old-experiment
```

## SQLite-Schema (v0.4.0)

```sql
-- New column added via idempotent ALTER TABLE migration:
ALTER TABLE lessons ADD COLUMN branch_id TEXT NOT NULL DEFAULT 'main';
CREATE INDEX idx_lessons_branch ON lessons(branch_id);

-- New audit log table:
CREATE TABLE forks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_branch TEXT NOT NULL,
    child_branch TEXT NOT NULL,
    forked_at TEXT NOT NULL,
    reason TEXT
);
```

Migration ist idempotent: alte `lessons.db` aus v0.3.0 wird mit
`PRAGMA table_info(lessons)` geprüft und nur falls `branch_id` fehlt
mit `DEFAULT 'main'` ergänzt.

## Use Cases

| Scenario | Aktion |
|---|---|
| „Was wenn ich eine andere Verifizierung hätte?" | `session fork --into alt-verify` |
| „Welche Lessons sind in der Hypothese entstanden?" | `session diff --branch alt-verify` |
| „Hat sich die Hypothese gelohnt?" | Merge oder Drop |
| „Audit-Trail: Wer hat wann warum geforkt?" | `session log` |

## MCP-Bridge (WebUI / Claude Code)

Tool `autodev_session_log` exposed alle 7 Actions (`fork`, `branches`,
`log`, `merge`, `drop`, `snapshot`, `diff`) via stdio JSON-RPC. Bridge
schält nur auf die verifizierte CLI (`tests/test_cli.py`).

```json
{
  "method": "tools/call",
  "params": {
    "name": "autodev_session_log",
    "arguments": {
      "project_root": "/path/to/repo",
      "action": "fork",
      "new_branch": "creative-hyp",
      "parent_branch": "main",
      "reason": "try T=0.9"
    }
  }
}
```

## Sicherheit & Invarianten

- `drop_branch("main")` → `ValueError` (Default-Branch ist geschützt).
- `fork_session(parent="main", new_branch="main")` → `ValueError`
  (kein Self-Fork).
- Lessons sind immutable by `(pattern, failure)` Schlüsselpaar in der
  Merge-Phase: Duplikate werden übersprungen.

## Roadmap

- **Branch-Pinning an Profile**: `session fork --into fast-hyp --profile fast`
  kombiniert Swarm Mode 1.0 mit Time-Travel Sessions.
- **Visualisierungs-Tool**: `autodev session graph --format mermaid`
  zeichnet den Fork-Tree als Mermaid-Diagramm.
- **Crash-Replay**: `session replay --branch creative-hyp --until <ts>`
  reproduziert die Lesson-Historie bis zu einem Zeitpunkt.
