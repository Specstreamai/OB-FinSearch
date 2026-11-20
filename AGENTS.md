# AGENTS.md — OB-FinSearch

Quick navigation guide for coding agents working in `OB-FinSearch`.

## Where to Look

| Looking for | Path |
|---|---|
| Benchmark metadata | `benchmark.yaml` |
| Agent loop & CLI runner | `finsearch/agent.py`, `finsearch/runner.py` |
| Search tool adapters | `finsearch/vendors/adapters.py`, `finsearch/vendors/base.py` |
| Judge & prompts | `finsearch/judge.py`, `finsearch/prompts/` |
| Live collection & grading | `finsearch/live/` |
| Offline unit tests | `tests/` |

## Commands

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
```

## Guidelines

- Keep API keys in `.env` and run outputs out of git.
- Run `pytest` before opening a pull request.
