"""Tests for verification gate."""
import subprocess
from pathlib import Path
from unittest.mock import patch

from autodev.verifier import VerificationResult, Verifier


class TestVerifier:
    def test_successful_verification(self, temp_project: Path):
        v = Verifier(temp_project, "echo 'test passed'")
        r = v.run()
        assert isinstance(r, VerificationResult)
        assert r.success is True
        assert r.exit_code == 0
        assert "test passed" in r.stdout

    def test_failed_verification(self, temp_project: Path):
        v = Verifier(temp_project, "exit 1")
        r = v.run()
        assert r.success is False
        assert r.exit_code == 1

    def test_extract_metric_from_stdout(self, temp_project: Path):
        v = Verifier(temp_project, "echo 'Metric: 3.14'")
        r = v.run(metric_pattern=r"Metric:\s*([\d.]+)")
        assert r.success is True
        assert r.metric_value == 3.14

    def test_extract_metric_failure(self, temp_project: Path):
        v = Verifier(temp_project, "echo 'no metric here'")
        r = v.run(metric_pattern=r"Metric:\s*([\d.]+)")
        assert r.success is True
        assert r.metric_value is None

    def test_timeout_handling(self, temp_project: Path):
        with patch("autodev.verifier.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
            r = Verifier(temp_project, "sleep 600").run()
            assert r.success is False
            assert r.exit_code == -1
            assert "timed out" in r.stderr.lower()

    def test_command_error_handling(self, temp_project: Path):
        v = Verifier(temp_project, "nonexistent_command_xyz")
        r = v.run()
        assert r.success is False
        assert r.exit_code != 0

    def test_working_directory(self, temp_project: Path):
        (temp_project / "test_marker.txt").write_text("marker", encoding="utf-8")
        v = Verifier(temp_project, "cat test_marker.txt")
        r = v.run()
        assert r.success is True
        assert "marker" in r.stdout

    def test_stderr_capture(self, temp_project: Path):
        v = Verifier(temp_project, "echo 'error message' >&2")
        r = v.run()
        assert "error message" in r.stderr

    def test_complex_metric_pattern(self, temp_project: Path):
        v = Verifier(temp_project, "echo 'Time: 2.5s, Memory: 100MB, Accuracy: 0.95'")
        r = v.run(metric_pattern=r"Accuracy:\s*([\d.]+)")
        assert r.metric_value == 0.95
