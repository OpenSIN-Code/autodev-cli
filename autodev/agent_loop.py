"""Core autonomous loop: PLAN → ACT → VERIFY → DONE (SIN-Code style)."""
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from .budget import BudgetWatcher
from .config import AgentConfig, ProgramGoal
from .knowledge_base import KnowledgeBase
from .mutator import CodeMutator
from .verifier import Verifier

console = Console()


# ── Sandbox helpers (module-level, also used by user-facing tests) ─────
def git_snapshot(project_root: Path) -> None:
    """Snapshot current working tree via git stash (with untracked included)."""
    subprocess.run(
        [
            "git", "stash", "push",
            "-u", "-m", f"autodev-snapshot-{int(time.time())}",
        ],
        cwd=project_root,
        capture_output=True,
    )


def git_rollback(project_root: Path) -> None:
    """Rollback: discard any uncommitted mutation in the working tree."""
    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=project_root,
        capture_output=True,
    )


# ── AgentLoop ──────────────────────────────────────────────────────────
# Bound-method sandbox signature: takes no args (closes over self).
# Free-function sandbox signature: takes project_root.
SandboxFn = Callable[..., None]


class AgentLoop:
    """Autonomous experiment loop inspired by autoresearch + SIN-Code.

    Default behaviour: git stash snapshot before each mutation, git
    checkout -- . on revert. Tests can pass no-op sandboxes to avoid
    touching the real git repo.
    """

    def __init__(
        self,
        config: AgentConfig,
        program: ProgramGoal | None,
        kb: KnowledgeBase,
        verify_cmd: str,
        budget_minutes: int,
        max_experiments: int,
        project_root: Path,
        target_files: list[Path] | None = None,
        snapshot_fn: SandboxFn | None = None,
        rollback_fn: SandboxFn | None = None,
        mutator: CodeMutator | None = None,
        verifier: Verifier | None = None,
    ):
        self.config = config
        self.program = program
        self.kb = kb
        self.project_root = project_root
        self.verifier = verifier or Verifier(project_root, verify_cmd)
        # Mutator: lazy if not provided so unit tests that never start the
        # loop don't need an OPENAI_API_KEY (SIN-Code safety: only pay the
        # LLM cost when we actually run).
        self._mutator_override = mutator
        self.budget = BudgetWatcher(budget_minutes, max_experiments)
        self.target_files = target_files or (
            [Path(f) for f in (program.allowed_files if program else [])]
        )
        # Bound-method defaults so callers can pass plain functions instead.
        self.snapshot_fn: SandboxFn = snapshot_fn or self._git_snapshot
        self.rollback_fn: SandboxFn = rollback_fn or self._rollback
        self.best_metric: float | None = None
        self.experiments: list[dict] = []

    # ── Sandbox (kept as methods so existing tests can patch subprocess) ─
    def _git_snapshot(self) -> None:  # noqa: D401 — exposed for backwards compat
        """Snapshot via git stash (relies on subclass / patch for testing)."""
        git_snapshot(self.project_root)

    def _rollback(self) -> None:
        """Rollback via git checkout -- . (subclass / patch for testing)."""
        git_rollback(self.project_root)

    # ── Public dispatchers (used by run()) ──────────────────────────────
    @property
    def mutator(self):
        """Lazy mutator construction (only requires OPENAI_API_KEY when run())."""
        if self._mutator_override is not None:
            return self._mutator_override
        if not hasattr(self, "_mutator_lazy"):
            self._mutator_lazy = CodeMutator()
        return self._mutator_lazy

    def snapshot(self) -> None:
        if self._takes_path(self.snapshot_fn):
            self.snapshot_fn(self.project_root)
        else:
            self.snapshot_fn()

    def rollback(self) -> None:
        if self._takes_path(self.rollback_fn):
            self.rollback_fn(self.project_root)
        else:
            self.rollback_fn()

    @staticmethod
    def _takes_path(fn: SandboxFn) -> bool:
        """Inspect a sandbox callable's arity without calling it."""
        import inspect
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        for p in sig.parameters.values():
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
                return True
        return False

    # ── Lesson extraction (unchanged) ───────────────────────────────────
    def _extract_lesson(self, error_output: str) -> tuple[str, str]:
        """Extract pattern and failure from error output."""
        failure = error_output[:200]
        if "ImportError" in error_output or "ModuleNotFoundError" in error_output:
            pattern = "import_error"
        elif "SyntaxError" in error_output:
            pattern = "syntax_error"
        elif "AssertionError" in error_output or "FAILED" in error_output:
            pattern = "test_failure"
        elif "Timeout" in error_output or "timed out" in error_output:
            pattern = "timeout"
        else:
            pattern = "unknown"
        return pattern, failure

    def _metric_was_improved(self, current: float | None) -> bool | None:
        """Lower-is-better comparison. None when no baseline yet."""
        if current is None or self.best_metric is None:
            return None
        return current < self.best_metric

    def _record_kept(self, file_path: Path, metric: float, delta: float, duration: float):
        self.kb.record_experiment(
            metric_value=metric, metric_delta=delta, duration=duration,
            success=True, diff=f"{file_path}: kept",
        )
        self.experiments.append({
            "file": str(file_path), "metric": metric, "delta": delta,
        })

    def _record_reverted(self, file_path: Path, delta: float, duration: float):
        self.kb.record_experiment(
            metric_value=self.best_metric or 0.0, metric_delta=delta,
            duration=duration, success=False, diff=f"{file_path}: reverted",
        )

    def _record_failure(self, file_path: Path, pattern: str, failure: str, duration: float):
        self.kb.add_lesson(pattern=pattern, failure=failure, fix="rollback", context=str(file_path))
        self.kb.record_experiment(
            metric_value=0, metric_delta=0, duration=duration,
            success=False, diff=f"{file_path}: failed ({pattern})",
        )

    # ── Main loop ──────────────────────────────────────────────────────
    def run(self):
        """Main autonomous loop."""
        console.print(Panel(
            f"[bold cyan]🧠 Autonomous Research Loop[/bold cyan]\n"
            f"Objective: {self.program.objective if self.program else 'Optimize'}\n"
            f"Files: {', '.join(str(f) for f in self.target_files)}",
            title="AutoDev Daemon",
        ))

        console.print("[yellow]📏 Measuring baseline...[/yellow]")
        baseline = self.verifier.run()
        if not baseline.success:
            console.print(f"[red]❌ Baseline verification failed:\n{baseline.stderr}[/red]")
            return

        self.best_metric = baseline.metric_value
        console.print(f"[green]✅ Baseline: {self.best_metric}[/green]")

        while not self.budget.check().exhausted:
            self.budget.record_experiment()
            self.snapshot()

            lessons = self.kb.query_lessons(limit=5)
            console.print(f"[cyan]{self.budget.summary()}[/cyan]")

            for target_file in self.target_files:
                full_path = self.project_root / target_file
                if not full_path.exists():
                    console.print(f"[red]⚠️  {target_file} not found, skipping[/red]")
                    continue

                original = full_path.read_text(encoding="utf-8")
                objective = self.program.objective if self.program else "Improve performance"

                console.print(f"\n[bold]🧪 Experiment {len(self.experiments)+1} on {target_file}[/bold]")

                try:
                    m = self.mutator  # resolves the lazy property
                    mutated = m.propose_mutation(
                        file_content=original,
                        file_path=str(target_file),
                        objective=objective,
                        lessons=lessons,
                        constraints=self.program.constraints if self.program else [],
                    )
                except Exception as e:
                    console.print(f"[red]LLM error: {e}[/red]")
                    self.rollback()
                    continue

                full_path.write_text(mutated, encoding="utf-8")

                start = time.time()
                result = self.verifier.run()
                duration = time.time() - start

                if not result.success:
                    pattern, failure = self._extract_lesson(result.stderr or result.stdout)
                    self._record_failure(full_path, pattern, failure, duration)
                    console.print(f"[red]❌ Failed: {pattern}[/red]")
                    self.rollback()
                    continue

                current_metric = result.metric_value
                improved = self._metric_was_improved(current_metric)
                if improved is True and current_metric is not None:
                    delta = (self.best_metric or 0.0) - current_metric
                    self.best_metric = current_metric
                    console.print(
                        f"[bold green]✅ IMPROVEMENT! {delta:+.4f} "
                        f"(new best: {current_metric:.4f})[/bold green]"
                    )
                    self._record_kept(full_path, current_metric, delta, duration)
                elif improved is False and current_metric is not None:
                    delta = (self.best_metric or 0.0) - current_metric
                    console.print(f"[yellow]↩️  No improvement ({delta:+.4f}), reverting[/yellow]")
                    self.rollback()
                    self._record_reverted(full_path, delta, duration)
                else:
                    console.print("[green]✅ Tests passed (no metric extracted), keeping change[/green]")

                time.sleep(1)

        self.save_report()

    def save_report(self):
        """Final report after budget exhaustion."""
        console.print(Panel(
            f"[bold green]🏁 Daemon Complete[/bold green]\n"
            f"Experiments run: {len(self.experiments)}\n"
            f"Best metric: {self.best_metric}\n"
            f"Improvements kept: {len(self.experiments)}\n\n"
            f"📚 Lessons learned: {self.kb.stats()['total']}",
            title="Final Report",
        ))
