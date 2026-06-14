"""Main CLI entry point using Typer."""
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .agent_loop import AgentLoop
from .config import load_config, load_program
from .knowledge_base import KnowledgeBase
from .sessions import (
    DEFAULT_BRANCH,
    diff_snapshots,
    drop_branch,
    fork_session,
    list_branches,
    list_forks,
    merge_branch,
    take_snapshot,
)
from .swarm import DEFAULT_PROFILES, Profile, SwarmCoordinator, load_profiles
from .verifier import Verifier

app = typer.Typer(
    name="autodev",
    help="AUTONOMOUS coding CLI: metrikgetriebene Experimente + Verification-First",
    no_args_is_help=True,
)
console = Console()


def _emit_json(data: dict) -> None:
    """Emit one JSON line on stdout (NDJSON friendly)."""
    console.print(json.dumps(data, ensure_ascii=False))


@app.command()
def init(
    project_root: Path = typer.Argument(".", help="Project root directory"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of rich UI"),
):
    """Initialize AutoDev in the current project."""
    agents_md = project_root / "AGENTS.md"
    program_md = project_root / "program.md"
    db_path = project_root / ".autodev" / "knowledge.db"

    if not agents_md.exists():
        if json_output:
            _emit_json({"ok": False, "error": "AGENTS.md not found"})
        else:
            console.print("[red]❌ AGENTS.md not found. Create it first.[/red]")
        raise typer.Exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    kb = KnowledgeBase(db_path)
    kb.initialize()

    payload = {
        "ok": True,
        "knowledge_db": str(db_path),
        "context": str(agents_md),
        "goal": str(program_md) if program_md.exists() else None,
        "version": "v0.2.0",
    }
    if json_output:
        _emit_json(payload)
    else:
        console.print("[green]✅ AutoDev initialized.[/green]")
        console.print(f"   Knowledge DB: {db_path}")
        console.print(f"   Context:      {agents_md}")
        console.print(f"   Goal:         {program_md}")


@app.command()
def status(
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Show current project state (goal, budget, KB stats, last experiments).

    Designed for `autodev-mcp` to consume.
    """
    config = load_config(project_root / "AGENTS.md") if (project_root / "AGENTS.md").exists() else None
    program = load_program(project_root / "program.md") if (project_root / "program.md").exists() else None
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    stats = kb.stats()

    payload = {
        "ok": True,
        "project_root": str(project_root),
        "config_path": str(project_root / "AGENTS.md"),
        "goal_path": str(project_root / "program.md"),
        "version": "v0.2.0",
        "role": config.role if config else None,
        "hard_invariants": list(config.hard_invariants) if config else [],
        "objective": program.objective if program else None,
        "metric": {
            "name": program.metric_name if program else None,
            "baseline": program.metric_baseline if program else None,
        } if program else None,
        "budget": {
            "minutes": program.budget_minutes if program else None,
            "max_experiments": program.max_experiments if program else None,
        } if program else None,
        "verify_cmd": program.verify_cmd if program else None,
        "allowed_files": list(program.allowed_files) if program else [],
        "knowledge": stats,
    }

    if json_output:
        _emit_json(payload)
        return

    table = Table(title="📊 AutoDev Status")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    if program:
        table.add_row("Objective", program.objective)
        table.add_row("Metric", f"{program.metric_name} (baseline {program.metric_baseline})")
        table.add_row(
            "Budget",
            f"{program.budget_minutes}m / {program.max_experiments} experiments",
        )
    table.add_row("Knowledge lessons", str(stats["total"]))
    console.print(table)


@app.command()
def lessons(
    pattern: str = typer.Option("", help="Filter by pattern substring"),
    limit: int = typer.Option(20, help="Max lessons"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Query the lessons-learned knowledge base.

    Designed for `autodev-mcp` `autodev_lessons` tool.
    """
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    rows = kb.query_lessons(pattern=pattern, limit=limit)

    if json_output:
        _emit_json({"ok": True, "count": len(rows), "lessons": rows})
        return

    table = Table(title="📚 Lessons Learned")
    table.add_column("ID", style="cyan")
    table.add_column("Pattern", style="green")
    table.add_column("Failure", style="red")
    table.add_column("Fix", style="yellow")
    for lesson in rows:
        table.add_row(
            str(lesson["id"]),
            lesson["pattern"][:40],
            lesson["failure"][:40],
            (lesson.get("fix") or "")[:40],
        )
    console.print(table)


@app.command()
def daemon(
    verify_cmd: str = typer.Option(..., help="Verification command (e.g. 'pytest -q')"),
    budget_minutes: int = typer.Option(30, help="Max wall-clock time"),
    max_experiments: int = typer.Option(20, help="Max experiment iterations"),
    project_root: Path = typer.Option(".", help="Project root"),
):
    """🔁 Start autonomous research daemon (autoresearch-style loop)."""
    config = load_config(project_root / "AGENTS.md")
    program = load_program(project_root / "program.md")
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()

    console.print("[bold cyan]🚀 Starting autonomous daemon...[/bold cyan]")
    console.print(f"   Verify: {verify_cmd}")
    console.print(f"   Budget: {budget_minutes}m / {max_experiments} experiments")

    loop = AgentLoop(
        config=config,
        program=program,
        kb=kb,
        verify_cmd=verify_cmd,
        budget_minutes=budget_minutes,
        max_experiments=max_experiments,
        project_root=project_root,
    )

    try:
        loop.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Daemon interrupted by user.[/yellow]")
        loop.save_report()


@app.command()
def optimize(
    target_file: Path = typer.Argument(..., help="File to optimize"),
    metric_cmd: str = typer.Option(..., help="Command that outputs metric"),
    budget_minutes: int = typer.Option(10, help="Time budget"),
    project_root: Path = typer.Option("."),
):
    """⚡ One-shot optimization of a single file (Karpathy autoresearch style)."""
    config = load_config(project_root / "AGENTS.md")
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()

    loop = AgentLoop(
        config=config,
        program=None,
        kb=kb,
        verify_cmd=metric_cmd,
        budget_minutes=budget_minutes,
        max_experiments=10,
        project_root=project_root,
        target_files=[target_file],
    )
    loop.run()


@app.command()
def run_experiment(
    file: Path = typer.Argument(..., help="Target file path"),
    mutation: str = typer.Option(..., help="The mutated file content"),
    verify_cmd: str = typer.Option(..., help="Verification command"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Submit a single mutation candidate and run verification.

    Designed for `autodev-mcp` `autodev_run_experiment` tool. Unlike the
    daemon, this is a 1-shot plan → act → verify → done with no LLM call.
    """
    full_path = project_root / file
    if not full_path.exists():
        if json_output:
            _emit_json({"ok": False, "error": f"{file} not found"})
        else:
            console.print(f"[red]❌ {file} not found[/red]")
        raise typer.Exit(1)

    original = full_path.read_text(encoding="utf-8")
    snapshot_dir = project_root / ".autodev" / "_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = snapshot_dir / f"{file.name}.orig"

    full_path.write_text(mutation, encoding="utf-8")
    if not snapshot_file.exists():
        snapshot_file.write_text(original, encoding="utf-8")

    verifier = Verifier(project_root, verify_cmd)
    result = verifier.run()

    baseline_verifier = Verifier(project_root, verify_cmd)
    # Re-run baseline against original (cheap, no LLM, no rollback)
    backup = full_path.read_text(encoding="utf-8")
    full_path.write_text(original, encoding="utf-8")
    baseline_result = baseline_verifier.run()
    full_path.write_text(backup, encoding="utf-8")

    metric = result.metric_value
    baseline_metric = baseline_result.metric_value
    improved = (
        metric is not None
        and baseline_metric is not None
        and metric < baseline_metric
    )

    payload = {
        "ok": True,
        "file": str(file),
        "verify_exit_code": result.exit_code,
        "verify_success": result.success,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
        "metric": metric,
        "baseline_metric": baseline_metric,
        "improved": improved,
        "kept": result.success and (improved or (metric is None and result.success)),
    }
    if json_output:
        _emit_json(payload)
        return

    console.print(f"[{'green' if payload['improved'] else 'yellow'}]"
                  f"experiment: improved={payload['improved']}, metric={payload['metric']}[/]")
    console.print(result.stdout[-500:])


@app.command()
def knowledge(
    action: str = typer.Argument("list", help="list | clear | stats"),
    project_root: Path = typer.Option("."),
):
    """📚 Manage the lessons-learned knowledge base."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()

    if action == "list":
        rows = kb.list_lessons()
        table = Table(title="📚 Lessons Learned")
        table.add_column("ID", style="cyan")
        table.add_column("Pattern", style="green")
        table.add_column("Failure", style="red")
        table.add_column("Fix", style="yellow")
        for lesson in rows:
            table.add_row(
                str(lesson["id"]),
                lesson["pattern"][:40],
                lesson["failure"][:40],
                lesson["fix"][:40],
            )
        console.print(table)
    elif action == "clear":
        kb.clear()
        console.print("[green]✅ Knowledge base cleared.[/green]")
    elif action == "stats":
        stats = kb.stats()
        console.print(f"Total lessons: {stats['total']}")
        console.print(f"Applied:       {stats['applied']}")


@app.command()
def goal(
    description: str = typer.Argument(..., help="Goal description"),
    priority: int = typer.Option(5, help="Priority 1-10"),
    project_root: Path = typer.Option("."),
):
    """🎯 Add a research goal to the queue."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    goal_id = kb.add_goal(description, priority)
    console.print(f"[green]✅ Goal #{goal_id} added (priority {priority})[/green]")
    console.print(f"   '{description}'")



app_session = typer.Typer(help="Time-travel sessions: fork, snapshot, branch lesson state.")
app.add_typer(app_session, name="session")


@app_session.command("fork")
def session_fork(
    new_branch: str = typer.Option(..., "--into", help="New branch_id"),
    parent_branch: str = typer.Option(DEFAULT_BRANCH, "--from", help="Parent branch_id"),
    reason: str = typer.Option("", "--reason", help="Why you are forking"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Fork a new session branch inheriting parent's lessons."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    snap = fork_session(kb, new_branch=new_branch, parent_branch=parent_branch, reason=reason)
    if json_output:
        _emit_json({
            "ok": True, "branch_id": snap.branch_id,
            "forked_from": snap.forked_from, "forked_at": snap.forked_at,
            "inherited_lessons": snap.lesson_count,
        })
    else:
        console.print(f"[green]Forked {snap.forked_from!r} -> {snap.branch_id!r}[/green]")
        console.print(f"   Inherited {snap.lesson_count} lessons.")


@app_session.command("branches")
def session_branches(
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """List all session branches with lesson counts."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    branches = list_branches(kb)
    if json_output:
        _emit_json({"ok": True, "branches": branches})
    else:
        table = Table(title="Session Branches")
        table.add_column("Branch", style="cyan")
        table.add_column("Lessons", style="green")
        for b in branches:
            table.add_row(b["branch_id"], str(b["lessons"]))
        console.print(table)


@app_session.command("log")
def session_log(
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Fork log (parent -> child, when, why)."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    forks = list_forks(kb)
    if json_output:
        _emit_json({"ok": True, "count": len(forks), "forks": forks})
    else:
        if not forks:
            console.print("[dim]No forks yet.[/dim]")
            return
        table = Table(title="Fork Log")
        table.add_column("From", style="cyan")
        table.add_column("Into", style="green")
        table.add_column("When", style="yellow")
        table.add_column("Reason", style="magenta")
        for f in forks:
            table.add_row(f["parent_branch"], f["child_branch"], f["forked_at"], f.get("reason") or "")
        console.print(table)


@app_session.command("merge")
def session_merge(
    source: str = typer.Option(..., "--from", help="Branch to merge from"),
    target: str = typer.Option(DEFAULT_BRANCH, "--into", help="Branch to merge into"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Merge source branch's divergent lessons into target (skip dupes)."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    n = merge_branch(kb, source_branch=source, target_branch=target)
    if json_output:
        _emit_json({"ok": True, "merged_lessons": n, "source": source, "target": target})
    else:
        console.print(f"[green]Merged {n} new lessons: {source!r} -> {target!r}[/green]")


@app_session.command("drop")
def session_drop(
    branch: str = typer.Option(..., "--branch", help="Branch to drop"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Drop a session branch (irreversible)."""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    n = drop_branch(kb, branch_id=branch)
    if json_output:
        _emit_json({"ok": True, "deleted_lessons": n, "branch": branch})
    else:
        console.print(f"[yellow]Dropped {n} lessons from {branch!r}.[/yellow]")


@app_session.command("snapshot")
def session_snapshot(
    branch: str = typer.Option(DEFAULT_BRANCH, "--branch"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    snap = take_snapshot(kb, branch_id=branch)
    if json_output:
        _emit_json({"ok": True, "branch": snap.branch_id, "at": snap.forked_at, "lesson_count": snap.lesson_count})
    else:
        console.print(f"[cyan]Snapshot {snap.branch_id!r}: {snap.lesson_count} lessons at {snap.forked_at}[/cyan]")


@app_session.command("diff")
def session_diff(
    branch: str = typer.Option(DEFAULT_BRANCH, "--branch"),
    project_root: Path = typer.Option("."),
    json_output: bool = typer.Option(False, "--json"),
):
    """Time-travel diff: what changed in this branch since fork?"""
    kb = KnowledgeBase(project_root / ".autodev" / "knowledge.db")
    kb.initialize()
    parent_forks = [f for f in list_forks(kb) if f["child_branch"] == branch]
    snap = take_snapshot(
        kb, branch_id=parent_forks[-1]["parent_branch"] if parent_forks else DEFAULT_BRANCH,
    )
    d = diff_snapshots(kb, snap, current_branch=branch)
    if json_output:
        _emit_json({"ok": True, **d})
    else:
        console.print(f"[bold]Diff for {branch!r}:[/bold]")
        console.print(f"   + {len(d['added'])} added, - {len(d['removed'])} removed, = {d['unchanged_count']} unchanged")

@app.command()
def swarm(
    prompt: str = typer.Option(..., "-p", "--prompt", help="Objective for every swarm agent"),
    agents: str = typer.Option(
        "fast,precise",
        "--agents",
        help="Comma-separated profile names (resolved from .autodev/profiles.toml + defaults)",
    ),
    verify_cmd: str = typer.Option(..., "--verify-cmd", help="Verification gate (e.g. 'pytest -q')"),
    budget_minutes: int = typer.Option(15, help="Per-agent wall-clock budget"),
    max_experiments: int = typer.Option(4, help="Per-agent experiment cap"),
    project_root: Path = typer.Option(".", help="Project root"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of rich UI"),
):
    """🐝 Run a swarm of agents (parallel profiles). First-verified-wins.

    Each profile runs in its own filesystem-isolated copy at
    .autodev/swarm/<ts>/<profile>/. Loser diffs are exported to
    .autodev/swarm-lost/ for forensics.
    """
    profiles = _resolve_profiles(agents, project_root)
    if not profiles:
        msg = {"ok": False, "error": f"no profiles resolved from '{agents}'"}
        if json_output:
            _emit_json(msg)
        else:
            console.print(f"[red]❌ {msg['error']}[/red]")
        raise typer.Exit(1)

    coord = SwarmCoordinator(
        profiles=profiles,
        project_root=project_root,
        prompt=prompt,
        verify_cmd=verify_cmd,
        budget_minutes=budget_minutes,
        max_experiments=max_experiments,
    )
    if json_output:
        # _emit_json one line per agent plus a final swarm summary.
        _emit_json({"ok": True, "event": "start", "profiles": [p.name for p in profiles]})
    else:
        console.print(f"[bold cyan]🐝 Swarm with {len(profiles)} profiles: "
                      f"{', '.join(p.name for p in profiles)}[/bold cyan]")
        console.print(f"   Prompt:     {prompt}")
        console.print(f"   Verify:     {verify_cmd}")
        console.print(f"   Budget:     {budget_minutes}m / {max_experiments} experiments per agent")

    result = coord.run()

    if json_output:
        _emit_json(result.to_json())
    else:
        table = Table(title=f"🏁 Swarm Result (winner: {result.winner or 'none'})")
        table.add_column("Profile", style="cyan")
        table.add_column("Won", style="green")
        table.add_column("Metric Δ", style="yellow")
        table.add_column("Lessons", style="magenta")
        table.add_column("Error", style="red")
        for name, r in result.agent_results.items():
            table.add_row(
                name,
                "✓" if r.won else "—",
                f"{r.delta:+.4f}" if r.delta is not None else "—",
                str(r.lessons_added),
                r.error or "",
            )
        console.print(table)
        console.print(f"[bold]Winner:[/bold] {result.winner or 'none'}")
        console.print(f"[dim]Loser diffs:[/dim] {result.lost_dir}")


def _resolve_profiles(names_csv: str, project_root: Path) -> list[Profile]:
    """Merge .autodev/profiles.toml (if present) with the built-in defaults."""
    file_profiles = load_profiles(project_root / ".autodev" / "profiles.toml")
    merged = {**DEFAULT_PROFILES, **file_profiles}
    wanted = [n.strip() for n in names_csv.split(",") if n.strip()]
    return [merged[n] for n in wanted if n in merged]


if __name__ == "__main__":
    app()
