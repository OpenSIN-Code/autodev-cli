# program.md — current research goal (editable by human)

This is the current objective. The agent reads it on every loop
iteration; mutate freely to swap research directions.

## Objective
Lower the *first-token* time of `autodev/cli.py` from baseline 3.1s to
under 2.0s without breaking the test suite.

## Metric
- **Target**: `import_latency_seconds`
- **Baseline**: 3.1
- **Measurement**: `python -c "import time; t=time.perf_counter(); import autodev.cli; print(f'import_latency_seconds={time.perf_counter()-t:.3f}')"`

## Budget
- Time: 60 minutes wall-clock
- Max experiments: 12

## Verification Gate
```bash
pytest -q && python -c "import time; t=time.perf_counter(); import autodev.cli; assert time.perf_counter()-t < 2.0"
```

## Allowed Files
- `autodev/cli.py`
- `autodev/agent_loop.py`

## Constraints
- Maintain ≥ 95% test coverage on `autodev/`
- No new runtime dependencies beyond those already declared in `pyproject.toml`
- Preserve the `--json` output contract for downstream MCP/SIN-Code consumers
