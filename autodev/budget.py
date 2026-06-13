"""Bounded autonomy: time and experiment budget watchdog (SIN-Code M4)."""
import time
from dataclasses import dataclass


@dataclass
class BudgetStatus:
    time_remaining: float
    experiments_remaining: int
    exhausted: bool


class BudgetWatcher:
    """Hard safety invariant: budget exhausted → stop and summon human."""

    def __init__(self, budget_minutes: int, max_experiments: int):
        self.start_time = time.time()
        self.budget_seconds = budget_minutes * 60
        self.max_experiments = max_experiments
        self.experiments_run = 0

    def check(self) -> BudgetStatus:
        elapsed = time.time() - self.start_time
        time_remaining = max(0, self.budget_seconds - elapsed)
        experiments_remaining = max(0, self.max_experiments - self.experiments_run)

        exhausted = time_remaining <= 0 or experiments_remaining <= 0

        return BudgetStatus(
            time_remaining=time_remaining,
            experiments_remaining=experiments_remaining,
            exhausted=exhausted,
        )

    def record_experiment(self):
        self.experiments_run += 1

    def summary(self) -> str:
        status = self.check()
        mins = int(status.time_remaining // 60)
        secs = int(status.time_remaining % 60)
        return (
            f"⏱  {mins}m {secs}s remaining | "
            f"🧪 {status.experiments_remaining} experiments left"
        )
