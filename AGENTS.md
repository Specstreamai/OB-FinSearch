# AGENTS.md — OB-FinSearch

Quick navigation guide for coding agents working in `OB-FinSearch`.

## Structure (Zero Overlap)

| Folder | Owns | Files |
|---|---|---|
| **`data/`** | Where the public questions live and their format | `data/README.md` |
| **`harness/`** | Execution only: CLI, run settings, question loading, agent loop, runner, live collection, live filings, search adapters | `harness/cli.py`, `harness/config.py`, `harness/questions.py`, `harness/agent.py`, `harness/agent_prompt.txt`, `harness/model_client.py`, `harness/runner.py`, `harness/live_collect.py`, `harness/live_filings.py`, `harness/search_api.py`, `harness/adapters/` |
| **`tools/`** | Tool setups & pricing (one file per tool for clean PRs) | `tools/<tool>.yaml` (12 tools, 19 setups) |
| **`judge/`** | Grading only: answer judge and prompt, board math, live grading and answer keys | `judge/answer_judge.py`, `judge/answer_judge_prompt.txt`, `judge/board_summary.py`, `judge/live_grade.py`, `judge/live_answer_keys.py`, `judge/live_extract_*_prompt.txt` |

Tests sit next to the code they check, in `harness/tests/` and `judge/tests/`. Benchmark order & win condition live at the root in `benchmark.yaml`.

## Commands

```sh
# Offline tests (no API keys)
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
```

## Guidelines

- **Keep folders strictly separated:** Question format in `data/`; execution in `harness/`; per-tool configs in `tools/<tool>.yaml`; grading in `judge/`.
- **Adding or tuning a tool:** Edit `tools/<tool>.yaml` (and `harness/adapters/<tool>.py` for a new search API), then run `pytest`.
- **No secrets or raw run logs in git:** Keep API keys in `.env` and run outputs in `runs/` (both gitignored).
- **Consistent terminology:** Use `tool`, `setup`, `question`, `ground truth`, `judge`, `board`.
