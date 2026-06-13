"""Verification gate — PoC/Oracle style (SIN-Code M3)."""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VerificationResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    metric_value: float | None = None


class Verifier:
    """Runs verification commands and extracts metrics."""

    def __init__(self, project_root: Path, verify_cmd: str):
        self.project_root = project_root
        self.verify_cmd = verify_cmd

    def run(self, metric_pattern: str | None = None) -> VerificationResult:
        """Execute verification command and optionally extract a metric."""
        try:
            result = subprocess.run(
                self.verify_cmd,
                shell=True,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )

            metric_value = None
            if metric_pattern and result.returncode == 0:
                if match := re.search(metric_pattern, result.stdout + result.stderr):
                    try:
                        metric_value = float(match.group(1))
                    except (IndexError, ValueError):
                        pass

            return VerificationResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                metric_value=metric_value,
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                success=False, exit_code=-1, stdout="", stderr="Verification timed out (5min)",
            )
        except Exception as e:
            return VerificationResult(
                success=False, exit_code=-2, stdout="", stderr=str(e),
            )
