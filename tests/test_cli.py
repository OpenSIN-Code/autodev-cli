"""Tests for CLI commands."""
from pathlib import Path

from typer.testing import CliRunner

from autodev.cli import app

runner = CliRunner()


class TestCLI:
    def test_help_command(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "autodev" in result.stdout.lower()

    def test_init_success(self, temp_project: Path):
        result = runner.invoke(app, ["init", str(temp_project)])
        assert result.exit_code == 0
        assert "initialized" in result.stdout.lower()
        assert (temp_project / ".autodev" / "knowledge.db").exists()

    def test_init_missing_agents_md(self, tmp_path: Path):
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code != 0
        assert "AGENTS.md not found" in result.stdout

    def test_knowledge_list_empty(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        result = runner.invoke(app, ["knowledge", "list", "--project-root", str(temp_project)])
        assert result.exit_code == 0

    def test_knowledge_stats(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        result = runner.invoke(app, ["knowledge", "stats", "--project-root", str(temp_project)])
        assert result.exit_code == 0
        assert "Total lessons:" in result.stdout

    def test_knowledge_clear(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        result = runner.invoke(app, ["knowledge", "clear", "--project-root", str(temp_project)])
        assert result.exit_code == 0
        assert "cleared" in result.stdout.lower()

    def test_goal_add(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        result = runner.invoke(
            app, ["goal", "Optimize performance", "--priority", "8",
                  "--project-root", str(temp_project)],
        )
        assert result.exit_code == 0
        assert "Goal" in result.stdout
        assert "priority 8" in result.stdout

    def test_daemon_missing_verify_cmd(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        result = runner.invoke(app, ["daemon", "--project-root", str(temp_project)])
        assert result.exit_code != 0

    def test_optimize_missing_metric_cmd(self, temp_project: Path):
        runner.invoke(app, ["init", str(temp_project)])
        test_file = temp_project / "test.py"
        test_file.write_text("def test(): pass", encoding="utf-8")
        result = runner.invoke(
            app, ["optimize", str(test_file), "--project-root", str(temp_project)],
        )
        assert result.exit_code != 0
