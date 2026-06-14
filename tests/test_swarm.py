"""Tests for autodev.swarm — Profile loader, SwarmCoordinator race, loser forensics."""
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from autodev.mutator import CodeMutator
from autodev.swarm import (
    DEFAULT_PROFILES,
    Profile,
    SwarmAgentResult,
    SwarmCoordinator,
    SwarmResult,
    load_profiles,
)


# ── Profile dataclass ──────────────────────────────────────────────────
class TestProfile:
    def test_defaults(self):
        p = Profile(name="x")
        assert p.name == "x"
        assert p.model == "gpt-4o"
        assert p.temperature == 0.7
        assert p.max_tokens == 4000

    def test_frozen(self):
        p = Profile(name="x")
        with pytest.raises((AttributeError, Exception)):
            p.name = "y"  # type: ignore[misc]

    def test_custom_values(self):
        p = Profile(name="creative", model="claude-3-opus", temperature=0.9, max_tokens=6000)
        assert p.model == "claude-3-opus"
        assert p.temperature == 0.9


class TestDefaults:
    def test_three_builtins(self):
        assert set(DEFAULT_PROFILES.keys()) >= {"fast", "precise", "creative"}

    def test_fast_uses_mini(self):
        assert "mini" in DEFAULT_PROFILES["fast"].model


# ── Profile loader ─────────────────────────────────────────────────────
class TestLoadProfiles:
    def test_empty_when_file_missing(self, tmp_path: Path):
        assert load_profiles(tmp_path / "nope.toml") == {}

    def test_parses_array_of_tables(self, tmp_path: Path):
        toml = tmp_path / "profiles.toml"
        toml.write_text("""
[[profiles]]
name = "fast"
model = "gpt-4o-mini"
temperature = 0.3
max_tokens = 2000
description = "Quick wins"

[[profiles]]
name = "creative"
model = "claude-3-opus"
temperature = 0.9
""", encoding="utf-8")
        profiles = load_profiles(toml)
        assert set(profiles.keys()) == {"fast", "creative"}
        assert profiles["fast"].model == "gpt-4o-mini"
        assert profiles["fast"].temperature == 0.3
        assert profiles["creative"].max_tokens == 4000  # default

    def test_invalid_toml_raises(self, tmp_path: Path):
        toml = tmp_path / "broken.toml"
        toml.write_text("this = is = invalid = toml", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid"):
            load_profiles(toml)

    def test_skips_entries_without_name(self, tmp_path: Path):
        toml = tmp_path / "anonymous.toml"
        toml.write_text("""
[[profiles]]
model = "gpt-4o"

[[profiles]]
name = "valid"
""", encoding="utf-8")
        profiles = load_profiles(toml)
        assert "valid" in profiles
        assert len(profiles) == 1


# ── SwarmResult serialisation ──────────────────────────────────────────
class TestSwarmResult:
    def test_to_json_shape(self):
        r = SwarmResult(
            prompt="opt",
            verify_cmd="pytest -q",
            started_at=time.time(),
            duration_seconds=12.0,
            winner="fast",
            final_metric=0.42,
        )
        r.agent_results = {
            "fast": SwarmAgentResult(profile="fast", won=True, delta=0.30, duration_seconds=4.0),
            "precise": SwarmAgentResult(profile="precise", won=False, error="timeout"),
        }
        d = r.to_json()
        assert d["ok"] is True
        assert d["winner"] == "fast"
        assert d["final_metric"] == 0.42
        assert d["agents"]["fast"]["won"] is True
        assert d["agents"]["precise"]["error"] == "timeout"


# ── Coordinator errors ─────────────────────────────────────────────────
class TestCoordinatorErrors:
    def test_empty_profiles_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="at least one"):
            SwarmCoordinator(
                profiles=[],
                project_root=tmp_path,
                prompt="x",
                verify_cmd="pytest",
            )

    def test_accepts_one_profile(self, tmp_path: Path):
        c = SwarmCoordinator(
            profiles=[Profile(name="fast")],
            project_root=tmp_path,
            prompt="x",
            verify_cmd="pytest",
        )
        assert len(c.profiles) == 1


# ── Coordinator race semantics (mocked workers) ────────────────────────
class TestCoordinatorRace:
    """Race semantics verified without invoking real AgentLoops."""

    def _make_project(self, tmp_path: Path) -> Path:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "AGENTS.md").write_text("# Agent\n## Role\nX\n", encoding="utf-8")
        (proj / "data.py").write_text("x = 1\n", encoding="utf-8")
        (proj / ".autodev").mkdir()
        return proj

    @patch.object(SwarmCoordinator, "_run_agent")
    def test_records_winner_from_first_completed_improvement(
        self, mock_run, tmp_path: Path,
    ):
        proj = self._make_project(tmp_path)
        # Two profiles: 'fast' (won), 'precise' (lost).
        mock_run.side_effect = [
            SwarmAgentResult(profile="fast", won=True, delta=0.5,
                             final_metric=0.42, duration_seconds=1.0),
            SwarmAgentResult(profile="precise", won=False, error="lost",
                             duration_seconds=2.0),
        ]
        c = SwarmCoordinator(
            profiles=[Profile(name="fast"), Profile(name="precise")],
            project_root=proj,
            prompt="opt",
            verify_cmd="pytest",
        )
        r = c.run()
        assert r.winner == "fast"
        assert r.final_metric == 0.42
        assert r.agent_results["fast"].won is True
        assert r.agent_results["precise"].won is False

    @patch.object(SwarmCoordinator, "_run_agent")
    def test_no_winner_when_none_improved(
        self, mock_run, tmp_path: Path,
    ):
        proj = self._make_project(tmp_path)
        mock_run.side_effect = [
            SwarmAgentResult(profile="fast", won=False, error="no progress"),
            SwarmAgentResult(profile="precise", won=False, error="timeout"),
        ]
        c = SwarmCoordinator(
            profiles=[Profile(name="fast"), Profile(name="precise")],
            project_root=proj,
            prompt="opt",
            verify_cmd="pytest",
        )
        r = c.run()
        assert r.winner is None
        assert r.final_metric is None

    @patch.object(SwarmCoordinator, "_run_agent")
    def test_worker_exception_recorded_as_error(
        self, mock_run, tmp_path: Path,
    ):
        proj = self._make_project(tmp_path)
        mock_run.side_effect = [
            SwarmAgentResult(profile="fast", won=False, error="boom"),
        ]
        c = SwarmCoordinator(
            profiles=[Profile(name="fast")],
            project_root=proj,
            prompt="opt",
            verify_cmd="pytest",
        )
        r = c.run()
        assert r.agent_results["fast"].error == "boom"
        assert r.winner is None

    @patch.object(SwarmCoordinator, "_run_agent")
    def test_lowest_delta_wins_among_many(
        self, mock_run, tmp_path: Path,
    ):
        proj = self._make_project(tmp_path)
        # Profile-keyed side_effect: each call returns the
        # SwarmAgentResult for THAT profile. This decouples the test
        # from thread scheduling (as_completed yields in completion
        # order, not submit order).
        deltas_by_name = {"a": 0.5, "b": 0.1, "c": 0.3}  # b is best
        def make_result(*args, **kwargs):
            profile = kwargs.get("profile")
            assert profile is not None
            return SwarmAgentResult(
                profile=profile.name, won=True,
                delta=deltas_by_name[profile.name],
                final_metric=0.42,
            )
        mock_run.side_effect = make_result

        c = SwarmCoordinator(
            profiles=[Profile(name="a"), Profile(name="b"), Profile(name="c")],
            project_root=proj,
            prompt="opt",
            verify_cmd="pytest",
        )
        r = c.run()
        assert r.winner == "b"

    def test_workers_run_in_parallel_threads(self, tmp_path: Path):
        """Verify the coordinator actually uses ThreadPoolExecutor.

        Trick: a Barrier(3) parked-up side. We DO NOT set release before
        workers start — instead workers block on the barrier, which
        holds them while THEIR threads are spun up; the test then
        releases the barrier, ensuring each worker is on its OWN
        named thread.
        """
        proj = self._make_project(tmp_path)
        barrier = threading.Barrier(parties=3, timeout=5.0)
        calls: list[str] = []

        def slow_run(*args, **kwargs):
            calls.append(threading.current_thread().name)
            # Block until all 3 workers are inside; passing barrier.wait
            # proves they ran in parallel.
            barrier.wait()
            profile = kwargs.get("profile")
            assert profile is not None
            return SwarmAgentResult(
                profile=profile.name if profile else "?",
                won=False,
            )

        with patch.object(SwarmCoordinator, "_run_agent", new=slow_run):
            c = SwarmCoordinator(
                profiles=[Profile(name="p1"), Profile(name="p2"), Profile(name="p3")],
                project_root=proj,
                prompt="opt",
                verify_cmd="pytest",
            )
            r = c.run()
            assert r is not None
            assert len(calls) == 3, f"expected 3 worker calls, got {len(calls)}"
            # All 3 calls happened on distinct named worker threads
            # because the barrier held them there.
            assert len({n for n in calls}) == 3, (
                f"workers did NOT run in parallel: {calls}"
            )

    def test_loser_diff_path_set_when_winner_logs_diff(self, tmp_path: Path):
        proj = self._make_project(tmp_path)
        with patch.object(SwarmCoordinator, "_run_agent") as mock_run:
            mock_run.side_effect = [
                SwarmAgentResult(profile="fast", won=True, delta=0.5,
                                 diff_path="/tmp/winner-fast.diff"),
            ]
            c = SwarmCoordinator(
                profiles=[Profile(name="fast")],
                project_root=proj,
                prompt="opt",
                verify_cmd="pytest",
            )
            r = c.run()
            assert r.winner == "fast"
            assert r.agent_results["fast"].diff_path == "/tmp/winner-fast.diff"


# ── Profile-aware mutator wiring ──────────────────────────────────────
class TestProfileAwareMutator:
    def test_code_mutator_accepts_profile_temperature(self):
        # Lazy OPENAI_API_KEY: __init__ succeeds without env.
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        m = CodeMutator(model="gpt-4o-mini", temperature=0.3)
        assert m.model == "gpt-4o-mini"
        assert m.temperature == 0.3

    def test_code_mutator_rejects_bad_temperature(self):
        with pytest.raises(ValueError, match="temperature"):
            CodeMutator(temperature=-1.0)
        with pytest.raises(ValueError, match="temperature"):
            CodeMutator(temperature=3.0)
