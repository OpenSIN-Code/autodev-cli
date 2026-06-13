# AutoDev-CLI

Autonomous Python optimizer that fuses [Karpathy's `autoresearch`
pattern](https://github.com/karpathy/autoresearch) (metrikgetriebene
optimization loops) with the [SIN-Code](https://github.com/OpenSIN-Code/SIN-Code-Bundle)
verification-first + bounded-autonomy invariants.

```
AGENTS.md  →  hard invariants (DO NOT MODIFY)
program.md →  current research goal + metric + budget
              ↓
autodev daemon  ── mutation ──► verify_cmd ──► keep? revert? → log lesson
```

## Features

- ✅ **Verification-First gates** — every mutation must `pytest -q`
  before it is kept (SIN-Code M3).
- 🧠 **Closed Learning Loop** — failed experiments become SQLite
  lessons that surface in the LLM prompt next round (SIN-Code v3.4.0).
- ⏱ **Bounded Autonomy** — hard time and experiment caps (SIN-Code M4).
- 🛰 **MCP server** — `autodev-mcp` exposes the same capabilities as
  Model-Context-Protocol tools (`autodev_status`, `autodev_lessons`,
  `autodev_run_experiment`, `autodev_init`) for use by the
  [SIN-Code WebUI v2](https://github.com/OpenSIN-Code/SIN-Code-WebUI-v2).

## Installation

```bash
git clone https://github.com/OpenSIN-Code/autodev-cli.git
cd autodev-cli
pip install -e ".[dev]"
export OPENAI_API_KEY="sk-..."   # required only when running the daemon
```

## Quick start

```bash
# Bootstrap a project
mkdir my-project && cd my-project
cp ../autodev-cli/AGENTS.md .
cp ../autodev-cli/program.md .
edit my-project/program.md             # set your objective + metric

autodev init .                          # creates .autodev/knowledge.db
autodev status --project-root . --json  # single-source snapshot for MCP
autodev daemon \
    --verify-cmd "pytest -q" \
    --budget-minutes 30 --max-experiments 12
```

## MCP integration (SIN-Code WebUI v2)

```bash
# Run the MCP server (zero-config, stdio transport)
autodev-mcp
# → exposes 4 tools that the WebUI chat agent can call.
```

Wire it into your SIN-Code WebUI v2 MCP client config:

```jsonc
{
  "mcpServers": {
    "autodev": {
      "command": "autodev-mcp",
      "env": {}
    }
  }
}
```

## Architecture

```
autodev/
├── __init__.py
├── cli.py             # Typer CLI (rich UI OR --json NDJSON)
├── cli_mcp.py         # stdio MCP server (4 tools)
├── agent_loop.py      # PLAN → ACT → VERIFY → DONE core
├── knowledge_base.py  # SQLite lessons (closed-loop memory)
├── mutator.py         # OpenAI-powered proposal
├── verifier.py        # subprocess verification gate
├── budget.py          # time + experiment watchdog (M4)
└── config.py          # AGENTS.md + program.md parsers
tests/
├── conftest.py                # temp_project, temp_db, sample_lessons fixtures
├── test_config.py             # 8 tests (AGENTS.md / program.md parsing)
├── test_knowledge_base.py     # 9 tests (SQLite lessons / experiments / goals)
├── test_verifier.py           # 9 tests (subprocess + metric extraction)
├── test_mutator.py            # 6 tests (OpenAI client mock)
├── test_budget.py             # 9 tests (time + experiments)
├── test_agent_loop.py         # 7 tests (_extract_lesson + sandbox)
├── test_agent_loop_run.py     # 10 tests (full PLAN→ACT→VERIFY with fakes)
└── test_cli.py                # 9 tests (Typer smoke)
```

## Quality gates

```bash
ruff check .                    # 0 errors
pyright .                       # 0 errors
pytest tests/                   # 67 passed
```

## License

MIT — see [`LICENSE`](./LICENSE).
