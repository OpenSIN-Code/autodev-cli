# Changelog

Alle wichtigen Änderungen werden hier dokumentiert.
Format basiert auf [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- MCP Integration für externe Tools — siehe `docs/MCP.md`
- Time-Travel Debugging via Session-Forking
- Superpowers-Integration (TDD/Debugging Skills)
- GitHub Bridge (issue-first Contributing)

### Changed
- Upgrade auf Python 3.11+
- Typer 0.12 (bessere Fehlermeldungen)

## [0.3.0] - 2026-06-14

### Added
- **Swarm Mode 1.0** (`autodev swarm`): ThreadPool-basierte
  parallel-execution von N Profile-Agents mit first-verified-wins race.
  - `autodev/swarm.py`: `Profile`, `load_profiles`,
    `SwarmCoordinator`, `SwarmResult`.
  - Filesystem-isolated worktrees unter `.autodev/swarm/<ts>/<profile>/`.
  - Loser-Forensics: jeder Verlierer-Agent exportiert seinen Datei-Snapshot
    nach `.autodev/swarm-lost/loser-<profile>-<ts>.diff`.
  - Gewinner-Diff: `.autodev/swarm-lost/winner-<profile>-<ts>.diff`
    (Audit-Log).
  - Lessons aus LAUFENDEN + VERLORENEN Agents werden weiterhin in die
    shared KnowledgeBase geschrieben (SIN-Code closed loop bleibt aktiv).
- **MCP-Tool `autodev_swarm`**: durch das `cli_mcp.py`-Bridge-Pattern
  exposed. Konsumierbar von SIN-Code WebUI v2 + Claude Code.
- **CLI `autodev swarm -p/--prompt --agents --verify-cmd --budget-minutes
  --max-experiments --json/--no-json`**: full Typer-Surface mit
  Profile-Auflösung (`.autodev/profiles.toml` + Built-in-Defaults).
- **Built-in-Profile** (`DEFAULT_PROFILES`): `fast`,
  `precise`, `creative` mit vor-getunten model/temperature-Paaren.
- **CodeMutator ist temperature-aware**: `CodeMutator(model="gpt-4o-mini",
  temperature=0.3)` — Lazy _client, kein OPENAI_API_KEY nötig wenn
  nur `__init__` aufgerufen wird.
- **`test_swarm.py`**: 12 Tests für Profile-Parser, Race-Semantik,
  Loser-Forensics, MCP-Bridge.

### Changed
- pyproject.toml: bumped auf `0.3.0` (semver: minor — additive feature).
- `docs/SWARM.md`: Status von "Stub" → "Implementiert v0.3.0".
- `docs/CHANGELOG.md`: dieses Block.

### Quality
- ruff ✓ · pyright ✓ · pytest ✓ (67 + 12 new = 79 bestehende Tests
  erweitert; 79 bestanden zum Release).

## [0.2.0] - 2026-06-14

### Added
- **MCP-Bridge**: `autodev-mcp` stdio-Server mit 4 Tools
  (`autodev_status`, `autodev_lessons`, `autodev_run_experiment`, `autodev_init`).
  Konsumiert von SIN-Code WebUI v2 (`lib/sin/mcp.ts:getAllMcpTools()`).
- **`--json` NDJSON Output** auf `init`, `status`, `lessons`, `run_experiment`
  für MCP-Konsum.
- **Injectable Sandbox**: `AgentLoop` akzeptiert jetzt `snapshot_fn`/`rollback_fn`/
  `mutator`/`verifier` als Konstruktor-Args. Lazy-`mutator` Property — kein OPENAI_API_KEY
  nötig außer wenn `run()` wirklich feuert.
- **`run()` testbar**: `tests/test_agent_loop_run.py` mit 10 FakeMutator/FakeVerifier-Tests.
- **CoDocs**: `.doc.md` für `agent_loop.py` + `cli_mcp.py` (SOTA Inline Docs, Section
  Separators, Magic-Value-Erklärungen).
- **67/67 pytest passing**, ruff clean, pyright clean.

### Changed
- `pyproject.toml`: bumped auf `0.2.0`; `[dev]` extras; ruff + pyright config.
- Repo-Migration: `yourname/autodev-cli` → `OpenSIN-Code/autodev-cli`.
- AGENTS.md: zeigt jetzt auf SIN-Code WebUI v2 + SIN-Code Tool Suite.

### Security
- MCP-Bridge timeout 300s pro Tool-Call.
- `_run_cli` toleriert non-zero Exit wenn stdout JSON liefert (kein Crashes).

## [0.1.0] - 2026-06-14

### Added
- **Core CLI**: `init`, `daemon`, `optimize`, `knowledge`, `goal`
- **Agent Loop**: PLAN → ACT → VERIFY → DONE
- **Knowledge Base**: SQLite-basierte Lessons-DB (3 Tabellen: lessons,
  experiments, goals)
- **Verifier**: Test-Gates mit Metrik-Extraktion (Regex)
- **Mutator**: LLM-basierte Code-Mutationen
- **Budget Watchdog**: Harte Zeit-/Experiment-Grenzen
- **Safety**: AGENTS.md Firewall, Scope-Limits, Secrets-Detection
- **Full Test Suite**: 67 Tests mit ~85% Coverage
- **Docs**: ARCHITECTURE, LEARNING, SAFETY, COOKBOOK, SWARM, MCP, CONTRIBUTING

### Security
- Secrets-Detection in LLM-Outputs
- Scope-Beschränkung via `allowed_files`
- Git stash Snapshots für atomare Rollbacks
- Headless-Modus mit `ask=deny`

### Philosophy
Inspiriert von:
- **Karpathy's autoresearch**: Metrikgetriebene autonome Loops
- **SIN-Code v3.15.0**: Verification-First, Closed Learning Loop, Bounded Autonomy
