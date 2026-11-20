# harness

Runs the benchmark and calls the search APIs. No grading code lives here.

- `cli.py` — Command-line runner behind `finsearch` (`vendors`, `run`, `rejudge`, `summary`, `live-collect`, `live-grade`).
- `config.py` — Models, search and fetch limits, model prices, and run defaults.
- `questions.py` — Loads questions from Hugging Face, a local folder, or one file.
- `agent.py` — Runs the agent loop: the model searches until it answers or runs out of searches.
- `agent_prompt.txt` — Instructions the agent sees.
- `model_client.py` — Connects to the agent's model.
- `runner.py` — Runs every question with every tool, sends each answer to the judge, and saves results under `runs/`.
- `live_collect.py` — Live lookup: asks every tool for stock and coin prices at set delays after a market moment.
- `search_api.py` — Shared code for all search adapters: the HTTP call, retries, cost, and page fetch rules.
- `adapters/` — One `<tool>.py` per search API, plus `__init__.py`, which lists them and reads each tool's setups and prices from `tools/<tool>.yaml`.
- `tests/` — Offline tests for the agent loop, question loading, live collection, and adapters.
