# Architektur

> "No unverified code ships." — Das fundamentale Prinzip, das jede Komponente antreibt.

## System-Überblick

```
┌────────────────────────────────────────────────────────────┐
│                    AutoDev CLI (Typer)                      │
│  init │ daemon │ optimize │ knowledge │ goal │ swarm       │
└─────────────────────────┬──────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│              Agent Loop (core orchestrator)                 │
│                                                            │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
│   │   PLAN   │→ │   ACT    │→ │  VERIFY  │→ │  DONE   │  │
│   │ (mutator)│  │(file I/O)│  │(verifier)│  │(commit) │  │
│   └──────────┘  └──────────┘  └──────────┘  └─────────┘  │
│                                                            │
│   + Budget Watchdog  + Knowledge Base  + Git Snapshots    │
└────────────────────────────────────────────────────────────┘
```

## Die vier Phasen

### 1. **PLAN** — Kontext assemblieren
- `AGENTS.md` lesen (harte Invarianten, verbotene Aktionen)
- `program.md` lesen (aktuelles Forschungsziel, Metrik)
- **Knowledge Base abfragen** — vergangene Fehler abrufen (SIN-Code Closed Loop)
- Ziel-Datei einlesen

### 2. **ACT** — Mutation vorschlagen & anwenden
- LLM generiert neuen Code (lesson-aware!)
- Git-Snapshot erstellen (`git stash push -m autodev-snapshot-<ts>`)
- Datei überschreiben

### 3. **VERIFY** — Oracle-Gate (M3)
- `verify_cmd` ausführen (z. B. `pytest -q && python bench.py`)
- Metrik extrahieren (Regex-Pattern)
- **Bei Fehlschlag**: Lesson in SQLite speichern, rollback

### 4. **DONE** — Entscheidung
- **Metrik besser?** → Änderung behalten, Experiment loggen
- **Metrik schlechter?** → `git checkout .` (rollback)
- **Budget erschöpft?** → Report generieren, Daemon beenden

## Datenfluss

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  program.md │────▶│  Agent Loop  │────▶│  train.py    │
│   (human)   │     │              │     │  (agent)     │
└─────────────┘     └──────┬───────┘     └──────┬───────┘
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐     ┌──────────────┐
                    │  SQLite DB   │     │  val_bpb /   │
                    │  (lessons)   │◀────│  metric      │
                    └──────────────┘     └──────────────┘
```

## Design-Entscheidungen

| Entscheidung | Warum |
|---|---|
| **Single file to modify** | Karpathys Ansatz — hält Scope klein, Diffs reviewbar |
| **Fixed time budget** | Experimente vergleichbar, plattformunabhängig |
| **SQLite für Lessons** | CGO-free, portabel, zero-setup (SIN-Code M2) |
| **Git stash für Snapshots** | Atomare Rollbacks, keine Datenverluste |
| **Markdown als Config** | LLM-nativ, versionierbar, keine YAML-Syntaxfehler |

## Erweiterbarkeit

Das System ist **schichtweise erweiterbar** (SIN-Code 4-Layer-Stack):

```
┌─────────────────────────────────────────┐
│  LAYER 4 — Tools        (autodev-cli)   │
│  LAYER 3 — Research     (autoresearch)  │
│  LAYER 2 — Methodology  (superpowers)   │
│  LAYER 1 — Context      (dox/co-docs)   │
└─────────────────────────────────────────┘
```

Jede Schicht ist optional und degradiert graceful, wenn nicht vorhanden.

## Komponenten-Übersicht

| Modul | Verantwortung | LOC |
|---|---|---|
| `cli.py` | Typer-Entrypoint, Rich UI + `--json` NDJSON | ~250 |
| `cli_mcp.py` | stdio MCP-Server (`autodev_status`, …) | ~165 |
| `agent_loop.py` | PLAN→ACT→VERIFY→DONE scheduler | ~280 |
| `knowledge_base.py` | SQLite lessons, experiments, goals | ~150 |
| `verifier.py` | subprocess gate + regex metric extraction | ~75 |
| `mutator.py` | OpenAI proposal mit lesson-aware prompt | ~70 |
| `budget.py` | Zeit + Experiment Watchdog (SIN-Code M4) | ~55 |
| `config.py` | AGENTS.md + program.md Parser | ~120 |

## Datenfluss-Diagramm (AgentLoop.run)

```
                ┌────────────────────┐
                │      start()       │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
       ┌────────│  baseline verify   │────  fail ───────────▶ exit (return)
       │        └─────────┬──────────┘
       │                  │ pass
       │                  ▼
       │        ┌────────────────────┐
       │        │ while not exhausted│
       │        └─────────┬──────────┘
       │                  │
       │   ┌──────────────┼──────────────┐
       │   │              │              │
       │   ▼              ▼              ▼
       │ snapshot      for target    record_experiment()
       │   │            file
       │   │              │              ▲
       │   │              ▼              │
       │   │     ┌──────────────┐       │
       │   │     │ propose (LLM)│       │
       │   │     └──────┬───────┘       │
       │   │            │               │
       │   │            ▼               │
       │   │     ┌──────────────┐       │
       │   │     │   write()    │       │
       │   │     └──────┬───────┘       │
       │   │            │               │
       │   │            ▼               │
       │   │     ┌──────────────┐       │
       │   │     │  verify_cmd  │       │
       │   │     └──┬────────┬──┘       │
       │   │  fail  │        │ pass    │
       │   │       ▼        ▼          │
       │   │   ┌────────┐ ┌─────────┐  │
       │   │   │lessons │ │extract  │  │
       │   │   │  +     │ │metric   │  │
       │   │   │rollback│ └──┬───┬──┘  │
       │   │   └────────┘    │   │     │
       │   │                 │   │     │
       │   │                 ▼   ▼     │
       │   │              ┌─────────┐ │
       │   │              │delta >0 │ │
       │   │              └──┬───┬──┘ │
       │   │                 │   │    │
       │   │              keep  revert│
       │   │                 │   │    │
       │   │                 ▼   ▼    │
       │   │              ┌─────────┐ ┌──────────┐
       │   │              │record   │ │rollback  │
       │   │              │kept (±) │ │+ record  │
       │   │              └─────────┘ └──────────┘
       │   │                                │
       │   └────────────────────────────────┘
       │
       └──── (until budget exhausted)
                          │
                          ▼
                ┌────────────────────┐
                │   save_report()    │
                └────────────────────┘
```
