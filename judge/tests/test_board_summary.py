import math

from judge.board_summary import compute_summary


def row(q, v, rep, ok, task="historical-lookup", **kw):
    return {"question_id": q, "vendor": v, "repeat": rep, "correct": ok, "task": task, **kw}


def test_mean_sd_flip_and_judge_errors():
    rows = [row("a", "x", 0, True), row("b", "x", 0, False),
            row("a", "x", 1, True), row("b", "x", 1, True),
            row("a", "x", 2, True), row("b", "x", 2, True, judge_error="parse")]
    s = compute_summary(rows)
    cell = next(c for c in s["cells"] if c["task"] == "historical-lookup")
    per_rep = [0.5, 1.0, 1.0]
    m = sum(per_rep) / 3
    sd = math.sqrt(sum((x - m) ** 2 for x in per_rep) / 2)
    assert math.isclose(cell["accuracy"], m) and math.isclose(cell["sd"], sd)
    assert cell["flip"] == 0.5                     # b flips (False, True); a doesn't
    assert s["judge_errors"] == 1 and s["n_graded"] == 5


def test_all_row_pools_tasks():
    rows = [row("a", "x", 0, True), row("m", "x", 0, False, task="multi-hop-lookup")]
    cells = {c["task"]: c for c in compute_summary(rows)["cells"]}
    assert cells["all"]["accuracy"] == 0.5 and cells["all"]["questions"] == 2


def test_filing_age_bands():
    rows = [row("a", "x", 0, True, task="live-filings", age_s=600),
            row("b", "x", 0, False, task="live-filings", age_s=9000),
            row("c", "x", 0, True, task="live-filings", age_s=9000),
            row("d", "x", 0, True, task="live-filings", age_s=40000, judge_error="parse")]
    age = {a["band"]: a for a in compute_summary(rows)["age"]}
    assert age["under 2 h"]["accuracy"] == 1.0 and age["2 to 6 h"]["accuracy"] == 0.5
    assert "6 h and over" not in age                # judge errors are left out
    assert compute_summary([row("a", "x", 0, True)])["age"] == []


def test_answers_whose_every_search_failed_count_as_wrong():
    failed = [{"status": "error", "latency_ms": 900}]
    rows = [row("a", "x", 0, True, searches=[{"status": "ok", "latency_ms": 100}], wall_ms=2000, input_tokens=10),
            row("b", "x", 0, True, searches=failed, vendor_error=True, wall_ms=3000, input_tokens=5)]
    s = compute_summary(rows)
    cell = next(c for c in s["cells"] if c["task"] == "historical-lookup")
    assert cell["accuracy"] == 0.5 and s["vendor_errors"] == 1 and s["n_graded"] == 2   # wrong even if judged correct
    u = s["usage"][0]
    assert u["vendor_errors"] == 1 and u["failed_calls"] == 1 and u["search_ms_median"] == 100
    assert u["input_tokens"] == 15 and u["wall_ms_median"] == 2000


def test_live_filings_vendor_errors_are_left_out():
    rows = [row("a", "x", 0, True, task="live-filings", age_s=600),
            row("b", "x", 0, False, task="live-filings", age_s=600, vendor_error=True)]
    s = compute_summary(rows)
    cell = next(c for c in s["cells"] if c["task"] == "live-filings")
    assert cell["accuracy"] == 1.0 and s["n_graded"] == 1 and s["vendor_errors"] == 1
