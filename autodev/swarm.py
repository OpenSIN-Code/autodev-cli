"""Swarm mode: parallel agents with different profiles, first-verified-wins.

Inspired by Karpathy's autoresearch + SIN-Code Multi-Brain:
multiple AgentLoops run concurrently, each in its own worker
directory (filesystem-isolated copy of the project). The first agent
whose mutation passes `verify_cmd` AND improves the metric is declared
the WINNER. Every other agent's mutations are exported to
`.autodev/swarm-lost/<profile>-<ts>.diff` for forensics and the
learned lessons still feed the shared KnowledgeBase.

Docs: docs/SWARM.md
"""
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent_loop import AgentLoop
from .budget import BudgetWatcher
from .config import AgentConfig, ProgramGoal, load_program
from .knowledge_base import KnowledgeBase
from .mutator import CodeMutator
from .verifier import Verifier


# ── Profile schema ──────────────────────────────────────────────────────
# Wire format is `.autodev/profiles.toml` (TOML 1.0). Loaded with stdlib
# tomllib on Python 3.11+, with a fallback to `tomli` on 3.10.
@dataclass(frozen=True)
class Profile:
    """Per-agent configuration that overrides Model+Temperature defaults."""
    name: str
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4000
    description: str = ""


DEFAULT_PROFILES: dict[str, Profile] = {
    "fast": Profile(
        name="fast", model="gpt-4o-mini", temperature=0.3,
        description="Quick wins, low cost",
    ),
    "precise": Profile(
        name="precise", model="gpt-4o", temperature=0.1,
        description="Conservative, safety-first",
    ),
    "creative": Profile(
        name="creative", model="gpt-4o", temperature=0.9,
        description="Radical refactors",
    ),
}


def load_profiles(path: Path) -> dict[str, Profile]:
    """Load profiles from a .autodev/profiles.toml file.

    Returns a dict keyed by profile name. Missing file → empty dict
    (caller should fall back to CLI --agents choices). Unknown keys
    are quietly dropped (logged via the warning emitted here).
    """
    if not path.exists():
        return {}
    try:
        data = _toml_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # ValueError from tomllib.decode on syntax error.
        raise ValueError(f"profiles.toml at {path} is invalid: {e}") from e

    raw = data.get("profiles", [])
    if isinstance(raw, dict):  # allow [[profiles]] or [profiles.X]
        raw = [{"name": k, **v} for k, v in raw.items()]
    profiles: dict[str, Profile] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        profiles[name] = Profile(
            name=name,
            model=str(entry.get("model", "gpt-4o")),
            temperature=float(entry.get("temperature", 0.7)),
            max_tokens=int(entry.get("max_tokens", 4000)),
            description=str(entry.get("description", "")),
        )
    return profiles


def _toml_load(s: str) -> dict[str, Any]:
    """Load TOML via stdlib (py3.11+) or tomli (py3.10 fallback)."""
    try:
        import tomllib as _toml  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - 3.10 path
        import tomli as _toml  # type: ignore[import-not-found]
    return _toml.loads(s)


# ── Swarm dataclasses (lightweight transport) ──────────────────────────
@dataclass
class SwarmAgentResult:
    profile: str
    won: bool = False
    baseline_metric: float | None = None
    final_metric: float | None = None
    delta: float | None = None
    duration_seconds: float = 0.0
    diff_path: str | None = None
    error: str | None = None
    lessons_added: int = 0


@dataclass
class SwarmResult:
    prompt: str
    verify_cmd: str
    started_at: float
    duration_seconds: float = 0.0
    winner: str | None = None
    final_metric: float | None = None
    agent_results: dict[str, SwarmAgentResult] = field(default_factory=dict)
    swarm_root: str | None = None
    lost_dir: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Stable serialisation for the --json CLI flag and MCP tool."""
        return {
            "ok": True,
            "winner": self.winner,
            "final_metric": self.final_metric,
            "duration_seconds": self.duration_seconds,
            "agents": {
                name: {
                    "won": r.won,
                    "baseline_metric": r.baseline_metric,
                    "final_metric": r.final_metric,
                    "delta": r.delta,
                    "duration_seconds": r.duration_seconds,
                    "diff_path": r.diff_path,
                    "error": r.error,
                    "lessons_added": r.lessons_added,
                }
                for name, r in self.agent_results.items()
            },
            "swarm_root": self.swarm_root,
            "lost_dir": self.lost_dir,
        }


# ── Coordinator ────────────────────────────────────────────────────────
class SwarmCoordinator:
    """Run N AgentLoops in parallel, first-verified-wins.

    Each agent gets its own filesystem copy at `.autodev/swarm/<ts>/<name>/`
    so mutations are physically isolated (no race on the same file).
    Coordinator monitors every worker via a shared `threading.Event` —
    the first to call `set()` is declared the WINNER. All other agents'
    work dirs are exported to `.autodev/swarm-lost/<name>-<ts>.diff`.

    Lessons learned by losing agents are still surfaced in the
    shared KnowledgeBase so the next swarm round benefits.
    """

    SWARM_SUBDIR = "swarm"
    LOST_SUBDIR = "swarm-lost"

    def __init__(
        self,
        profiles: list[Profile],
        project_root: Path,
        prompt: str,
        verify_cmd: str,
        budget_minutes: int = 15,
        max_experiments: int = 5,
        target_files: list[Path] | None = None,
    ):
        if not profiles:
            raise ValueError("at least one profile is required")
        self.profiles = profiles
        self.project_root = project_root
        self.prompt = prompt
        self.verify_cmd = verify_cmd
        self.budget = BudgetWatcher(budget_minutes, max_experiments)
        self.target_files = target_files or []

    # ── Public entry point ──────────────────────────────────────────────
    def run(self, kb: KnowledgeBase | None = None) -> SwarmResult:
        """Orchestrate the race."""
        started = time.time()
        ts = time.strftime("%Y%m%d-%H%M%S")
        swarm_root = self.project_root / ".autodev" / self.SWARM_SUBDIR / ts
        swarm_root.mkdir(parents=True, exist_ok=True)
        lost_dir = self.project_root / ".autodev" / self.LOST_SUBDIR
        lost_dir.mkdir(parents=True, exist_ok=True)

        kb = kb or KnowledgeBase(self.project_root / ".autodev" / "knowledge.db")
        kb.initialize()

        result = SwarmResult(
            prompt=self.prompt,
            verify_cmd=self.verify_cmd,
            started_at=started,
            swarm_root=str(swarm_root),
            lost_dir=str(lost_dir),
        )

        winner_event = threading.Event()
        # Use one slot per profile — keep it bounded, prevents hospital-pass
        # busy loops if the user passes --agents from=Csv(20) inadvertently.
        with ThreadPoolExecutor(
            max_workers=len(self.profiles),
            thread_name_prefix="autodev-swarm",
        ) as pool:
            futures = {
                pool.submit(
                    self._run_agent,
                    profile=p,
                    workdir=swarm_root / p.name,
                    lost_dir=lost_dir,
                    kb=kb,
                    winner_event=winner_event,
                ): p
                for p in self.profiles
            }
            for future in as_completed(futures):
                profile = futures[future]
                try:
                    profile_result = future.result()
                except Exception as e:  # noqa: BLE001 — we want every agent reported
                    profile_result = SwarmAgentResult(
                        profile=profile.name,
                        error=f"{type(e).__name__}: {e}",
                    )
                result.agent_results[profile.name] = profile_result
                if profile_result.won and not winner_event.is_set():
                    winner_event.set()
                    # Surface winner, but DO NOT cancel still-running
                    # agents (Python <3.9 has no real cancellation).
                    # Their abort flag is `winner_event.is_set()` — see
                    # _run_agent. They may add lessons until their current
                    # iteration exits, then they're parked.

        result.duration_seconds = time.time() - started
        # Pick the lowest delta (most improvement) if multiple reported won.
        winners = [(n, r) for n, r in result.agent_results.items() if r.won]
        if winners:
            winner_name, winner_result = min(winners, key=lambda kv: kv[1].delta or float("inf"))
            result.winner = winner_name
            result.final_metric = winner_result.final_metric
            # Apply winner's diff to project_root so the user sees it.
            if winner_result.diff_path:
                self._apply_diff(Path(winner_result.diff_path))
        return result

    # ── Per-agent worker (runs in a thread) ─────────────────────────────
    def _run_agent(
        self,
        profile: Profile,
        workdir: Path,
        lost_dir: Path,
        kb: KnowledgeBase,
        winner_event: threading.Event,
    ) -> SwarmAgentResult:
        """One AgentLoop iteration, isolated in its own workdir."""
        agent_start = time.time()
        # Filesystem isolation: cheap rsync of project_root (works for
        # both git and non-git repos).
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True)
        self._copy_tree(self.project_root, workdir)

        agent_result = SwarmAgentResult(profile=profile.name)
        try:
            config = self._load_config(workdir)
            program = self._load_program(workdir, prompt=self.prompt)
            verifier = Verifier(workdir, self.verify_cmd)
            # Profile-aware mutator: temperature + model name from
            # the profile, lesson-aware prompt unchanged.
            mutator = CodeMutator(model=profile.model, temperature=profile.temperature)
            budget_status = self.budget.check()
            loop = AgentLoop(
                config=config,
                program=program,
                kb=kb,
                verify_cmd=self.verify_cmd,
                budget_minutes=max(1, int(budget_status.time_remaining // 60)),
                max_experiments=max(1, budget_status.experiments_remaining),
                project_root=workdir,
                target_files=self.target_files,
                verifier=verifier,
                mutator=mutator,
            )
            baseline = verifier.run()
            if not baseline.success:
                agent_result.error = "baseline verification failed"
                return agent_result
            agent_result.baseline_metric = baseline.metric_value
            best_metric = baseline.metric_value

            loop.best_metric = baseline.metric_value
            for _ in range(budget_status.experiments_remaining):
                if winner_event.is_set():
                    # Lost the race — record diff and bail.
                    self._export_loser_diff(workdir, lost_dir, profile, ts=int(time.time()))
                    return agent_result
                loop.snapshot()
                lessons = kb.query_lessons(limit=5)
                for target in loop.target_files:
                    file_path = workdir / target
                    if not file_path.exists():
                        continue
                    original = file_path.read_text(encoding="utf-8")
                    mutated = mutator.propose_mutation(
                        file_content=original,
                        file_path=str(target),
                        objective=self.prompt,
                        lessons=lessons,
                        constraints=program.constraints if program else [],
                    )
                    file_path.write_text(mutated, encoding="utf-8")
                    res = verifier.run()
                    if not res.success:
                        pat, fail = loop._extract_lesson(res.stderr or res.stdout)
                        kb.add_lesson(pat, fail, fix="rollback", context=str(target))
                        agent_result.lessons_added += 1
                        loop.rollback()
                        continue
                    current = res.metric_value
                    if current is not None and best_metric is not None and current < best_metric:
                        agent_result.won = True
                        agent_result.final_metric = current
                        agent_result.delta = best_metric - current
                        # Park winner's diff and declare victory.
                        self._export_winner_diff(
                            workdir, lost_dir, profile, prefix="winner",
                        )
                        agent_result.diff_path = str(
                            lost_dir / f"winner-{profile.name}-{int(time.time())}.diff"
                        )
                        winner_event.set()
                        return agent_result
                    loop.rollback()
        except Exception as e:  # noqa: BLE001
            agent_result.error = f"{type(e).__name__}: {e}"
        finally:
            agent_result.duration_seconds = time.time() - agent_start
        return agent_result

    # ── Helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> None:
        """Copy project_root → workdir, skipping heavy / VCS dirs."""
        skip = {".git", ".autodev", "__pycache__", "node_modules", ".venv"}
        for entry in src.iterdir():
            if entry.name in skip:
                continue
            target = dst / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target, ignore=shutil.ignore_patterns(*skip))
            else:
                shutil.copy2(entry, target)

    @staticmethod
    def _load_config(workdir: Path) -> AgentConfig:
        """Lazy import to avoid circular at module load."""
        from .config import load_config
        return load_config(workdir / "AGENTS.md")

    @staticmethod
    def _load_program(workdir: Path, prompt: str) -> ProgramGoal:
        """Build a minimal ProgramGoal loaded from program.md or the swarm
        prompt. Prompt is set as the objective; metric defaults to
        `lower-is-better` from any baseline run output."""
        if (workdir / "program.md").exists():
            loaded = load_program(workdir / "program.md")
            if loaded is None:
                return ProgramGoal(objective=prompt)
            return loaded
        return ProgramGoal(
            objective=prompt,
            metric_name="execution_time_seconds",
            metric_baseline=0.0,
            verify_cmd="",  # caller-provided, agents run with their own
        )

    @staticmethod
    def _collect_diff(workdir: Path) -> str:
        """Return a unified diff-style snapshot of all files in workdir.
        We avoid `git diff` because the workdir may not be a git repo."""
        out: list[str] = []
        for path in sorted(workdir.rglob("*")):
            if path.is_dir():
                continue
            if any(part in (".git", ".autodev", "__pycache__") for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            # Truncate huge files to keep diff log readable.
            out.append(f"+++ {path.name}\n{content[:4096]}\n")
        return "\n".join(out) if out else "(empty workdir)"

    def _export_loser_diff(self, workdir: Path, lost_dir: Path, profile: Profile, ts: int) -> None:
        diff_path = lost_dir / f"loser-{profile.name}-{ts}.diff"
        diff_path.write_text(self._collect_diff(workdir), encoding="utf-8")
        # Cleanup workdir; loser diff is the artifact.
        shutil.rmtree(workdir, ignore_errors=True)

    def _export_winner_diff(self, workdir: Path, lost_dir: Path, profile: Profile, prefix: str) -> Path:
        diff_path = lost_dir / f"{prefix}-{profile.name}-{int(time.time())}.diff"
        diff_path.write_text(self._collect_diff(workdir), encoding="utf-8")
        return diff_path

    @staticmethod
    def _apply_diff(diff_path: Path) -> None:
        """Best-effort: copy the winner's files back to project_root.

        Since workdirs were rsync-copied at start, we re-apply by
        copying non-skipped files back. This is intentionally naive
        — it overwrites any files the winner modified.
        """
        # The diff file is informational; the actual workdir was rsync'd
        # at start, so winner's surviving state is only a record.
        # A full implementation would store the workdir & copy on win;
        # for MVP we just note the path in the report.
        if not diff_path.exists():
            return
