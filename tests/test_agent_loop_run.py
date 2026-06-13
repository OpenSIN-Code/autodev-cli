"""Coverage for AgentLoop.run() — mocked mutator + verifier, no real git/LLM.

These tests exercise the actual loop body. The fakes are deliberately
false-but-deterministic: the verifier returns canned VerificationResult
objects; the mutator returns canned file contents. Snapshot/rollback are
injected as no-op so the loop never shells out to git.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from autodev.agent_loop import AgentLoop
from autodev.config import AgentConfig, ProgramGoal
from autodev.knowledge_base import KnowledgeBase
from autodev.verifier import VerificationResult


# ── Fakes ──────────────────────────────────────────────────────────────
@dataclass
class FakeMutator:
    responses: list[str] = field(default_factory=list)
    error_after: int | None = None
    raise_exc: Exception | None = None
    call_count: int = 0

    def propose_mutation(self, *, file_content: str, file_path: str,
                         objective: str, lessons: list, constraints: list) -> str:
        if self.raise_exc and self.error_after is not None and self.call_count >= self.error_after:
            raise self.raise_exc
        idx = self.call_count % len(self.responses)
        self.call_count += 1
        return self.responses[idx]


@dataclass
class FakeVerifier:
    results: list[VerificationResult] = field(default_factory=list)
    call_count: int = 0

    def run(self, metric_pattern=None) -> VerificationResult:
        idx = self.call_count % len(self.results)
        self.call_count += 1
        return self.results[idx]


# ── Setup helper ───────────────────────────────────────────────────────
def _seed_project(tmp_path: Path) -> tuple[Path, KnowledgeBase, AgentConfig, ProgramGoal]:
    target = tmp_path / "src"
    target.mkdir()
    (target / "data_pipeline.py").write_text("def run() -> float:\n    return 1.0\n")

    kb = KnowledgeBase(tmp_path / ".autodev" / "knowledge.db")
    kb.initialize()

    config = AgentConfig(role="test")
    program = ProgramGoal(
        objective="Reduce latency",
        metric_name="execution_time_seconds",
        metric_baseline=4.2,
        verify_cmd="pytest -q",
        budget_minutes=30,
        max_experiments=3,
        allowed_files=["src/data_pipeline.py"],
        constraints=[],
    )
    return tmp_path, kb, config, program


def _build(
    project_root, kb, config, program, *, mutator, verifier,
    max_experiments=3, budget_minutes=30, target_files=None, no_sandbox=True,
):
    original_contents: dict[Path, str] = {}
    target_paths = [project_root / tf for tf in (target_files or [Path("src/data_pipeline.py")])]

    def _snapshot(*_a, **_kw) -> None:
        for p in target_paths:
            if p.exists():
                original_contents[p] = p.read_text(encoding="utf-8")

    def _rollback(*_a, **_kw) -> None:
        for p, content in original_contents.items():
            p.write_text(content, encoding="utf-8")

    snap = _snapshot
    rb = _rollback
    return AgentLoop(
        config=config, program=program, kb=kb, verify_cmd=program.verify_cmd,
        budget_minutes=budget_minutes, max_experiments=max_experiments,
        project_root=project_root,
        target_files=target_files or [Path("src/data_pipeline.py")],
        snapshot_fn=snap, rollback_fn=rb, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
    )


# ── Tests ──────────────────────────────────────────────────────────────
def test_run_exits_early_when_baseline_verification_fails(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    mutator = FakeMutator(responses=["def run() -> float:\n    return 1.0\n"])
    verifier = FakeVerifier(results=[
        VerificationResult(False, 1, "", "pytest crashed — no tests collected"),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier)
    loop.run()
    assert mutator.call_count == 0
    assert verifier.call_count == 1
    assert loop.best_metric is None


def test_run_keeps_experiment_when_metric_improves(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    improved = "def run() -> float:\n    return 0.5\n"
    mutator = FakeMutator(responses=[improved])
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
        VerificationResult(True, 0, "metric=0.5", "", metric_value=0.5),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  max_experiments=1)
    loop.run()
    assert mutator.call_count == 1
    assert loop.best_metric == 0.5
    assert len(loop.experiments) == 1
    assert loop.experiments[0]["delta"] == pytest.approx(3.7, rel=0.01)


def test_run_reverts_experiment_when_metric_regresses(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    target = project_root / "src" / "data_pipeline.py"
    original = target.read_text()
    worse = "def run() -> float:\n    return 5.0\n"
    mutator = FakeMutator(responses=[worse])
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
        VerificationResult(True, 0, "metric=5.0", "", metric_value=5.0),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  max_experiments=1)
    loop.run()
    assert loop.best_metric == 4.2
    assert loop.experiments == []
    assert target.read_text() == original, "mutation must be reverted"


def test_run_records_lesson_when_verification_fails(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    target = project_root / "src" / "data_pipeline.py"
    original = target.read_text()
    mutator = FakeMutator(responses=["def run() -> BROKEN\n"])
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
        VerificationResult(False, 1, "", "AssertionError: x is not 1"),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  max_experiments=1)
    loop.run()
    lessons = kb.query_lessons("test_failure")
    assert len(lessons) == 1
    assert "AssertionError" in lessons[0]["failure"]
    assert target.read_text() == original


def test_run_respects_max_experiment_budget(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    mutator = FakeMutator(responses=["def run():\n    return 0.1\n"] * 99)
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2)
    ] + [
        VerificationResult(True, 0, "metric=0.1", "", metric_value=0.1)
    ] * 99)
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  max_experiments=3)
    loop.run()
    assert mutator.call_count <= 3, "loop respects max_experiments budget"


def test_run_continues_after_mutator_raises_and_rolls_back(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    target = project_root / "src" / "data_pipeline.py"
    original = target.read_text()
    mutator = FakeMutator(
        responses=["def run():\n    return 1.0\n"],
        error_after=1,
        raise_exc=RuntimeError("OpenAI quota exceeded"),
    )
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
        VerificationResult(True, 0, "metric=1.0", "", metric_value=1.0),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  max_experiments=2)
    loop.run()
    # The loop should still have progressed through 2 experiment slots.
    # First slot: LLM error → rolled back. Second slot: successful improvement.
    # file ends in mutated state (1.0 vs 4.2 → kept but no metric improvement on regression).
    assert target.read_text() != original, "second experiment should have kept its mutation"


def test_run_target_files_not_found_warns_and_skips(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    mutator = FakeMutator(responses=["x"])
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2)
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
                  target_files=[Path("does/not/exist.py")], max_experiments=1)
    loop.run()
    assert mutator.call_count == 0


def test_run_keeps_change_when_tests_pass_without_metric(tmp_path):
    project_root, kb, config, program = _seed_project(tmp_path)
    target = project_root / "src" / "data_pipeline.py"
    original = target.read_text()
    new_src = "def run() -> float:\n    # refactor\n    return 1.0\n"
    mutator = FakeMutator(responses=[new_src])
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "passes", "", metric_value=None),
        VerificationResult(True, 0, "passes", "", metric_value=None),
    ])
    loop = _build(project_root, kb, config, program, mutator=mutator, verifier=verifier)
    loop.run()
    assert target.read_text() != original, "no-metric but tests-pass → kept"


def test_run_injected_sandbox_takes_path_argument(tmp_path):
    """When a free function is injected, snapshot/rollback should call with project_root."""
    project_root, kb, config, program = _seed_project(tmp_path)
    targets: list[Path] = []
    def track_snapshot(p: Path) -> None:
        targets.append(p)
    def track_rollback(p: Path) -> None:
        targets.append(p)

    mutator = FakeMutator(responses=["def run(): pass\n"] * 5)
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
    ] + [
        VerificationResult(False, 1, "", "SyntaxError")
    ] * 5)
    loop = AgentLoop(
        config=config, program=program, kb=kb,
        verify_cmd=program.verify_cmd, budget_minutes=30, max_experiments=1,
        project_root=project_root,
        target_files=[Path("src/data_pipeline.py")],
        snapshot_fn=track_snapshot, rollback_fn=track_rollback,
        mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
    )
    loop.run()
    # Both funcs were called at least once
    assert len(targets) >= 2
    # All calls received the same project_root
    assert all(t == project_root for t in targets)


def test_run_injected_sandbox_takes_no_argument(tmp_path):
    """Bound-method style injection (no args) should also work."""
    project_root, kb, config, program = _seed_project(tmp_path)
    snap_calls = []
    rb_calls = []

    def snap():
        snap_calls.append("snap")

    def rb():
        rb_calls.append("rb")

    mutator = FakeMutator(responses=["def run(): pass\n"] * 5)
    verifier = FakeVerifier(results=[
        VerificationResult(True, 0, "metric=4.2", "", metric_value=4.2),
    ] + [
        VerificationResult(False, 1, "", "SyntaxError")
    ] * 5)
    loop = AgentLoop(
        config=config, program=program, kb=kb,
        verify_cmd=program.verify_cmd, budget_minutes=30, max_experiments=1,
        project_root=project_root,
        target_files=[Path("src/data_pipeline.py")],
        snapshot_fn=snap, rollback_fn=rb,
        mutator=mutator, verifier=verifier,  # type: ignore[arg-type]
    )
    loop.run()
    assert snap_calls, "bound snapshot callable invoked"
    assert rb_calls, "bound rollback callable invoked"
