# tests

Offline tests for the harness. Run them all from the repo root with `.venv/bin/pytest`.

- `conftest.py` — Sets placeholder API keys so adapters can build requests without real keys.
- `test_agent.py` — The agent loop with a scripted model: search and fetch limits, and the rule that only seen pages can be fetched.
- `test_questions.py` — Loading questions and live lookup items from local files.
- `test_live_collect.py` — Market close times and how live lookup fills in its queries.
- `test_live_lookup_requests.py` — Exa and Tako send different requests in live lookup; other tools do not.
- `test_keenable.py` — Keenable requests, results, cost from reported credits, and fetch from its index.
- `test_search_api.py` — API keys are hidden in the saved request.
