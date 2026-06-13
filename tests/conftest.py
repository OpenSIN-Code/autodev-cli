"""Shared pytest fixtures for AutoDev CLI tests."""
from pathlib import Path

import pytest


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project structure for testing."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    agents_md = project_root / "AGENTS.md"
    agents_md.write_text("""# Agent Context

## Role
You are an autonomous coding agent.

## Hard Invariants
- Verification-First: No code ships without passing verify_cmd
- Bounded Scope: Only modify allowed_files
- No Secrets: Never log API keys

## Forbidden Actions
- Modifying AGENTS.md
- Running destructive git commands
""", encoding="utf-8")

    program_md = project_root / "program.md"
    program_md.write_text("""# Current Research Goal

## Objective
Optimize data_pipeline.py for execution time.

## Metric
- **Target**: `execution_time_seconds`
- **Baseline**: 4.2
- **Measurement**: `python benchmarks/run.py`

## Budget
- Time: 30
- Max experiments: 10

## Verification Gate
```bash
pytest tests/ -q && python benchmarks/run.py
```

## Allowed Files
- `src/data_pipeline.py`
- `src/utils.py`

## Constraints
- Maintain 100% test coverage
""", encoding="utf-8")

    autodev_dir = project_root / ".autodev"
    autodev_dir.mkdir()

    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "data_pipeline.py").write_text("""
def process_data(items):
    result = []
    for item in items:
        result.append(item * 2)
    return result
""", encoding="utf-8")

    return project_root


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database."""
    return tmp_path / "test_knowledge.db"


@pytest.fixture
def sample_lessons() -> list[dict]:
    return [
        {"pattern": "import_error", "failure": "ModuleNotFoundError: No module named 'numpy'",
         "fix": "Use built-in Python libraries only", "context": "src/data_pipeline.py"},
        {"pattern": "syntax_error", "failure": "SyntaxError: invalid syntax at line 42",
         "fix": "Check for missing colons or parentheses", "context": "src/utils.py"},
        {"pattern": "timeout", "failure": "Execution exceeded 300s timeout",
         "fix": "Optimize nested loops", "context": "src/data_pipeline.py"},
    ]
