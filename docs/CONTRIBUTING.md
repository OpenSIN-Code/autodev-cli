# Contributing

## Development Setup

```bash
# Clone
git clone https://github.com/OpenSIN-Code/autodev-cli
cd autodev-cli

# Install (mit Dev-Dependencies)
pip install -e ".[dev]"

# Tests ausführen
pytest

# Coverage-Report
pytest --cov=autodev --cov-report=html
open htmlcov/index.html
```

## Code-Style

```bash
# Linting
ruff check autodev/ tests/
ruff format --check autodev/ tests/

# Type-Checking
pyright autodev/
```

`pyproject.toml` konfiguriert:
- `ruff`: `target-version = "py310"`, `line-length = 100`, `select = ["E","F","W","I","B","UP"]`
- `pyright`: `reportArgumentType = none`, `reportPossiblyUnboundVariable = false` (mcp.* Stub-Importe)
- `B008` wird in `cli.py` ignoriert (Typer-Defaults zwingen Argument-Forwarding)

## Commit-Konventionen

Wir nutzen **Conventional Commits** (wie SIN-Code):

```
feat:       Neue Funktion
fix:        Bug-Fix
docs:       Dokumentation
test:       Tests
refactor:   Refactoring ohne Funktionsänderung
perf:       Performance-Verbesserung
chore:      Maintenance
```

**Beispiele**:

```
feat(knowledge): add pattern classifier for type errors
fix(verifier): handle timeout edge case
docs(learning): expand SQLite schema documentation
test(agent_loop): add coverage for rollback scenarios
```

## Pull Request Checklist

- [ ] Alle Tests bestehen (`pytest`)
- [ ] Coverage ≥ 85% für neue Module
- [ ] Linting sauber (`ruff check`)
- [ ] Typisierung vorhanden (`pyright`)
- [ ] CoDoc (`.doc.md`) für neue öffentliche APIs
- [ ] `docs/CHANGELOG.md` aktualisiert
- [ ] Issue referenziert (`Closes #123`)

## Neue Features

### 1. Issue öffnen (Issue-First!)

Seit SIN-Code v3.9.0: **Jedes Feature beginnt als Issue**.

```bash
gh issue create --title "feat: add time-travel debugging"
```

### 2. Branch erstellen

```bash
git checkout -b feat/time-travel
```

### 3. Implementieren + Tests

Beispiel-Test-Skeleton:

```python
# tests/test_session_fork.py
def test_session_fork_replays_baseline(tmp_path):
    """A forked session must re-run baseline verification."""
    ...
```

### 4. PR öffnen mit Issue-Referenz

```
Closes #42

## What
Adds time-travel debugging via session forking.

## Why
Users want to explore parallel solution paths.

## Tests
- Added test_session_fork.py (12 tests)
- Coverage: 92%
```

## Architektur-Entscheidungen

| Entscheidung | Dokumentation |
|---|---|
| SQLite statt Postgres | `docs/LEARNING.md` |
| Git stash für Snapshots | `docs/SAFETY.md` |
| Markdown als Config | `AGENTS.md` |
| MCP für externe Tools | `docs/MCP.md` |
| Injectable Sandbox (snapshot_fn/rollback_fn) | `autodev/agent_loop.doc.md` |

## Fragen?

- 💬 Discussions auf GitHub: <https://github.com/OpenSIN-Code/autodev-cli/discussions>
- 📚 Architecture: `docs/ARCHITECTURE.md`
- 🤖 Sister project: <https://github.com/OpenSIN-Code/SIN-Code-WebUI-v2> (WebUI konsumiert `autodev-mcp`)
