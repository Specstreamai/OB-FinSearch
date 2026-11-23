import json

from harness.runner import done_runs


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_resume_retries_only_answers_whose_every_search_failed(tmp_path):
    rows = [{"question_id": "a", "vendor": "x", "repeat": 0, "correct": True},
            {"question_id": "b", "vendor": "x", "repeat": 0, "correct": False, "vendor_error": True}]
    write(tmp_path / "results.jsonl", rows)
    assert done_runs(tmp_path) == {("a", "x", 0), ("b", "x", 0)}          # plain resume keeps both
    assert done_runs(tmp_path, retry_vendor_errors=True) == {("a", "x", 0)}
    kept = [json.loads(line) for line in open(tmp_path / "results.jsonl")]
    assert [r["question_id"] for r in kept] == ["a"]                       # the failed row is gone from the file
    backups = list(tmp_path.glob("results.before_vendor_retry_*.jsonl"))
    assert len(backups) == 1 and len(backups[0].read_text().splitlines()) == 2
