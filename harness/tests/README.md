# tests

Offline tests for the harness. Run them all from the repo root with `.venv/bin/pytest`.

- `conftest.py` — Sets placeholder API keys so adapters can build requests without real keys.
- `test_agent.py` — The agent loop with a scripted model: search and fetch limits, the rule that only seen pages can be fetched, search latency without retries, tokens per turn, the objective-and-query search tool, publication dates in results, and tool calls written as text cut from the answer.
- `test_adapters.py` — Adapter requests and replies: Parallel objective and included domains, Keenable modes and credit pricing, and publication dates on results.
- `test_questions.py` — Loading questions, live lookup items and live filings questions from local files.
- `test_live_collect.py` — Market close times and how live lookup fills in its queries.
- `test_live_filings.py` — Live filings with a fake agent and judge: one search, one ask per tool, filing age on each row, and resume.
- `test_live_lookup_requests.py` — Exa and Tako send different requests in live lookup; other tools do not.
