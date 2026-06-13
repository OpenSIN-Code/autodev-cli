"""Tests for AGENTS.md and program.md parsing."""
from pathlib import Path

import pytest

from autodev.config import AgentConfig, ProgramGoal, load_config, load_program


class TestLoadConfig:
    def test_load_valid_agents_md(self, temp_project: Path):
        config = load_config(temp_project / "AGENTS.md")
        assert isinstance(config, AgentConfig)
        assert config.role == "You are an autonomous coding agent."
        assert len(config.hard_invariants) == 3
        assert "Verification-First" in config.hard_invariants[0]
        assert len(config.forbidden_actions) == 2

    def test_load_missing_agents_md(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="AGENTS.md not found"):
            load_config(tmp_path / "AGENTS.md")

    def test_empty_agents_md(self, tmp_path: Path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Empty Config\n", encoding="utf-8")
        config = load_config(agents_md)
        assert config.role == ""
        assert config.hard_invariants == []
        assert config.forbidden_actions == []

    def test_partial_agents_md(self, tmp_path: Path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("""# Agent Context

## Role
Test agent role.

## Hard Invariants
- Invariant 1
- Invariant 2
""", encoding="utf-8")
        config = load_config(agents_md)
        assert config.role == "Test agent role."
        assert len(config.hard_invariants) == 2
        assert config.forbidden_actions == []


class TestLoadProgram:
    def test_load_valid_program_md(self, temp_project: Path):
        program = load_program(temp_project / "program.md")
        assert program is not None
        assert isinstance(program, ProgramGoal)
        assert program.objective == "Optimize data_pipeline.py for execution time."
        assert program.metric_name == "execution_time_seconds"
        assert program.metric_baseline == 4.2
        assert program.budget_minutes == 30
        assert program.max_experiments == 10
        assert "pytest tests/ -q" in program.verify_cmd
        assert len(program.allowed_files) == 2
        assert len(program.constraints) == 1

    def test_load_missing_program_md(self, tmp_path: Path):
        assert load_program(tmp_path / "program.md") is None

    def test_partial_program_md(self, tmp_path: Path):
        program_md = tmp_path / "program.md"
        program_md.write_text("""# Current Research Goal

## Objective
Just optimize something.
""", encoding="utf-8")
        program = load_program(program_md)
        assert program is not None
        assert program.objective == "Just optimize something."
        assert program.metric_name == ""
        assert program.metric_baseline == 0.0
        assert program.budget_minutes == 30

    def test_program_with_no_budget_section(self, tmp_path: Path):
        program_md = tmp_path / "program.md"
        program_md.write_text("""# Goal

## Objective
Test objective.

## Metric
- **Target**: `metric_name`
- **Baseline**: 1.5
""", encoding="utf-8")
        program = load_program(program_md)
        assert program is not None
        assert program.budget_minutes == 30
        assert program.max_experiments == 20
