"""Tests for budget watchdog."""
import time

from autodev.budget import BudgetStatus, BudgetWatcher


class TestBudgetWatcher:
    def test_initial_status(self):
        w = BudgetWatcher(budget_minutes=30, max_experiments=20)
        s = w.check()
        assert isinstance(s, BudgetStatus)
        assert s.time_remaining > 0
        assert s.experiments_remaining == 20
        assert s.exhausted is False

    def test_time_budget_decreases(self):
        w = BudgetWatcher(budget_minutes=1, max_experiments=100)
        s1 = w.check()
        time.sleep(0.05)
        s2 = w.check()
        assert s2.time_remaining < s1.time_remaining

    def test_experiment_budget_decreases(self):
        w = BudgetWatcher(budget_minutes=60, max_experiments=10)
        assert w.check().experiments_remaining == 10
        w.record_experiment()
        assert w.check().experiments_remaining == 9
        w.record_experiment()
        w.record_experiment()
        assert w.check().experiments_remaining == 7

    def test_budget_exhausted_by_time(self):
        w = BudgetWatcher(budget_minutes=0, max_experiments=100)
        w.start_time = time.time() - 60
        s = w.check()
        assert s.exhausted is True
        assert s.time_remaining == 0

    def test_budget_exhausted_by_experiments(self):
        w = BudgetWatcher(budget_minutes=60, max_experiments=3)
        for _ in range(3):
            w.record_experiment()
        s = w.check()
        assert s.exhausted is True
        assert s.experiments_remaining == 0

    def test_budget_not_exhausted(self):
        w = BudgetWatcher(budget_minutes=60, max_experiments=10)
        w.record_experiment()
        w.record_experiment()
        s = w.check()
        assert s.exhausted is False
        assert s.experiments_remaining == 8

    def test_summary_format(self):
        w = BudgetWatcher(budget_minutes=30, max_experiments=20)
        w.record_experiment()
        summary = w.summary()
        assert "remaining" in summary
        assert "experiments left" in summary
        assert "⏱" in summary
        assert "🧪" in summary

    def test_time_remaining_never_negative(self):
        w = BudgetWatcher(budget_minutes=0, max_experiments=10)
        w.start_time = time.time() - 3600
        assert w.check().time_remaining >= 0

    def test_experiments_remaining_never_negative(self):
        w = BudgetWatcher(budget_minutes=60, max_experiments=2)
        for _ in range(5):
            w.record_experiment()
        assert w.check().experiments_remaining >= 0
