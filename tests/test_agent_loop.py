"""Tests for autonomous agent loop (subprocess-mocked, no LLM/git pollution)."""
from pathlib import Path
from unittest.mock import patch

import pytest

from autodev.agent_loop import AgentLoop
from autodev.config import AgentConfig, ProgramGoal
from autodev.knowledge_base import KnowledgeBase


class TestAgentLoop:
    @pytest.fixture
    def mock_config(self) -> AgentConfig:
        return AgentConfig(
            role="Test agent",
            hard_invariants=["Verification-First"],
            forbidden_actions=["Modify AGENTS.md"],
            allowed_files=["test.py"],
        )

    @pytest.fixture
    def mock_program(self) -> ProgramGoal:
        return ProgramGoal(
            objective="Optimize test.py",
            metric_name="execution_time",
            metric_baseline=5.0,
            budget_minutes=1,
            max_experiments=5,
            verify_cmd="echo 'test'",
            allowed_files=["test.py"],
            constraints=["No external deps"],
        )

    def test_agent_loop_initialization(self, temp_project: Path, mock_config, mock_program):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=mock_program, kb=kb,
            verify_cmd="echo test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        assert loop.config == mock_config
        assert loop.program == mock_program
        assert loop.best_metric is None

    def test_extract_lesson_import_error(self, temp_project: Path, mock_config):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=None, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        pattern, failure = loop._extract_lesson("ImportError: No module named 'numpy'")
        assert pattern == "import_error"
        assert "numpy" in failure

    def test_extract_lesson_syntax_error(self, temp_project: Path, mock_config):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=None, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        pattern, _ = loop._extract_lesson("SyntaxError: invalid syntax at line 42")
        assert pattern == "syntax_error"

    def test_extract_lesson_test_failure(self, temp_project: Path, mock_config):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=None, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        pattern, _ = loop._extract_lesson("AssertionError: 1 != 2\nFAILED test_something")
        assert pattern == "test_failure"

    @patch("autodev.agent_loop.subprocess.run")
    def test_git_snapshot(self, mock_run, temp_project: Path, mock_config):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=None, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        loop._git_snapshot()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "git" in cmd and "stash" in cmd

    @patch("autodev.agent_loop.subprocess.run")
    def test_rollback(self, mock_run, temp_project: Path, mock_config):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=None, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        loop._rollback()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "git" in cmd and "checkout" in cmd

    def test_save_report(self, temp_project: Path, mock_config, mock_program):
        kb = KnowledgeBase(temp_project / ".autodev" / "knowledge.db")
        kb.initialize()
        loop = AgentLoop(
            config=mock_config, program=mock_program, kb=kb,
            verify_cmd="test", budget_minutes=1, max_experiments=5,
            project_root=temp_project,
        )
        loop.best_metric = 3.5
        loop.experiments = [{"file": "test.py", "metric": 3.5, "delta": 1.5}]
        loop.save_report()  # must not raise
