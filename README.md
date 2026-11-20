# OB-FinSearch

Measures which web search API helps an agent answer financial research questions (equities, filings, and crypto) accurately. Every tool runs with the same model, search budget, and day.

## Structure

- [`data/`](data/README.md) — Where the public questions live and what each file holds.
- [`harness/`](harness/README.md) — Runs the agent and calls each search API.
- [`tools/`](tools/README.md) — One config file per search tool (11 tools, 17 setups).
- [`judge/`](judge/README.md) — Grades the agent's answers against ground truth.

Coding agents can start with [`AGENTS.md`](AGENTS.md).

## Quick start

Run the offline check (no API keys needed):

```sh
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
```

To run against live APIs, copy `.env.example` to `.env`, add your keys, and run `.venv/bin/finsearch --help`.

## Adding or updating a tool

1. Add or edit `tools/<tool>.yaml`. For a new search API, also add `harness/adapters/<tool>.py`, one line in `harness/adapters/__init__.py`, and its key in `.env.example`.
2. Run the offline check above and open a pull request.
