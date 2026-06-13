"""Parse AGENTS.md and program.md configuration files."""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    """Immutable agent configuration (from AGENTS.md)."""
    role: str = ""
    hard_invariants: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)
    raw_content: str = ""


@dataclass
class ProgramGoal:
    """Current research goal (from program.md)."""
    objective: str = ""
    metric_name: str = ""
    metric_baseline: float = 0.0
    measurement_cmd: str = ""
    budget_minutes: int = 30
    max_experiments: int = 20
    verify_cmd: str = ""
    allowed_files: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


def load_config(path: Path) -> AgentConfig:
    """Parse AGENTS.md into structured config."""
    if not path.exists():
        raise FileNotFoundError(f"AGENTS.md not found at {path}")

    content = path.read_text(encoding="utf-8")
    config = AgentConfig(raw_content=content)

    if role_match := re.search(r"## Role\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        config.role = role_match.group(1).strip()

    if inv_match := re.search(r"## Hard Invariants\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        config.hard_invariants = [
            line.strip("- ").strip()
            for line in inv_match.group(1).split("\n")
            if line.strip().startswith("-")
        ]

    if forbid_match := re.search(r"## Forbidden Actions\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        config.forbidden_actions = [
            line.strip("- ").strip()
            for line in forbid_match.group(1).split("\n")
            if line.strip().startswith("-")
        ]

    return config


def load_program(path: Path) -> ProgramGoal | None:
    """Parse program.md into structured goal."""
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    goal = ProgramGoal()

    if obj_match := re.search(r"## Objective\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        goal.objective = obj_match.group(1).strip()

    if metric_match := re.search(r"## Metric\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        metric_text = metric_match.group(1)
        if target := re.search(r"\*\*Target\*\*:\s*`([^`]+)`", metric_text):
            goal.metric_name = target.group(1)
        if baseline := re.search(r"\*\*Baseline\*\*:\s*([\d.]+)", metric_text):
            goal.metric_baseline = float(baseline.group(1))

    if budget_match := re.search(r"## Budget\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        budget_text = budget_match.group(1)
        if time_m := re.search(r"Time:\s*(\d+)", budget_text):
            goal.budget_minutes = int(time_m.group(1))
        if exp_m := re.search(r"Max experiments:\s*(\d+)", budget_text):
            goal.max_experiments = int(exp_m.group(1))

    if verify_match := re.search(r"## Verification Gate\s+```bash\s+(.*?)```", content, re.DOTALL):
        goal.verify_cmd = verify_match.group(1).strip()

    if files_match := re.search(r"## Allowed Files\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        goal.allowed_files = [
            line.strip("- ").strip().strip("`")
            for line in files_match.group(1).split("\n")
            if line.strip().startswith("-")
        ]

    if constraints_match := re.search(r"## Constraints\s+(.*?)(?=\n##|\Z)", content, re.DOTALL):
        goal.constraints = [
            line.strip("- ").strip()
            for line in constraints_match.group(1).split("\n")
            if line.strip().startswith("-")
        ]

    return goal
