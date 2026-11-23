# tests

Offline tests for the judge. Run them all from the repo root with `.venv/bin/pytest`.

- `test_answer_judge.py` — Reading the judge's verdict out of its reply, even when other braces come first; the judge model, the trap line, and Bedrock model ids.
- `test_board_summary.py` — Board math: accuracy across repeats, answers that change between repeats, failed judge calls, filing age bands, and answers whose every search failed.
- `test_live_grade.py` — Live lookup grading for stocks and coins, the answer key readers, and the cost table.
