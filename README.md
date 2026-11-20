# OB-FinSearch

Measures which web search API helps an agent answer live financial research questions (equities, filings, and crypto) accurately under the same model and budget.

## Structure

- `finsearch/` — Agent loop (`agent.py`), runner (`runner.py`), search tool adapters (`vendors/`), live data collectors (`live/`), prompts (`prompts/`), and judge (`judge.py`).
- `tests/` — Offline unit tests covering the agent, tool adapters, and judge.
- `benchmark.yaml` — Benchmark metadata and win condition.

Coding agents can start with [`AGENTS.md`](AGENTS.md).

## Quick start

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
```

Copy `.env.example` to `.env`, add your model and search API keys, and run `.venv/bin/python -m finsearch --help`.

## Adding or updating a tool

1. Add or edit the search adapter in `finsearch/vendors/adapters.py` and add its key to `.env.example`.
2. Run `.venv/bin/pytest` and open a pull request.
