# judge

Grades the agent's answers against ground truth. No search or agent code lives here.

- `answer_judge.py` — Asks Claude Opus 5.5 whether each answer matches the reference answer within its tolerance.
- `answer_judge_prompt.txt` — Instructions the judge sees.
- `board_summary.py` — Turns graded results into the board: accuracy per tool and task, how much it moves between repeats, and cost.
- `live_grade.py` — Live lookup: reads the price out of each tool's results and checks it against the answer key.
- `live_answer_keys.py` — Reads the live lookup answer keys (official stock closes and coin prices) from a file, Hugging Face, or a fixed test price.
- `live_extract_equity_prompt.txt` — Instructions for reading a stock's closing price out of search results.
- `live_extract_crypto_prompt.txt` — Instructions for reading a coin's price out of search results.
- `tests/` — Offline tests for the board math, live grading, and answer keys.
