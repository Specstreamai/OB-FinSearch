"""Live filings with a fake agent and judge: one search, one ask per vendor, filing age on each row, resume."""
import json
from types import SimpleNamespace as NS

from harness import config, live_filings

QUESTIONS = [
    {"id": "f1", "question": "Q1?", "answer": "A1", "tolerance": "exact", "filed_at": "2026-11-17T21:00:00Z"},
    {"id": "f2", "question": "Q2?", "answer": "A2", "tolerance": "", "filed_at": "2026-11-17T16:00:00-05:00"},
]


def _fake(monkeypatch, calls):
    def run_agent(qid, question, **kw):
        calls.append(kw)
        return NS(answer="A1", to_dict=lambda: {"question_id": qid, "vendor": kw["vendor"], "answer": "A1",
                                                "input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10,
                                                "vendor_cost_usd": 0.01, "n_searches": 1, "n_fetches": 0})

    monkeypatch.setattr(live_filings, "run_agent", run_agent)
    monkeypatch.setattr(live_filings, "agent_client", lambda: None)
    monkeypatch.setattr(live_filings, "judge_client", lambda model: calls.append({"judge_model": model}))
    monkeypatch.setattr(live_filings, "judge", lambda client, q, answer, model: {"correct": answer == q["answer"],
                                                                                "reason": "r", "judge_model": model})


def test_one_search_one_ask_per_vendor(tmp_path, monkeypatch):
    calls = []
    _fake(monkeypatch, calls)
    out = tmp_path / "run"
    live_filings.run(QUESTIONS, ["exa_instant", "exa_deep"], out_dir=out, today="2026-11-17", data_label="x")
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and {(r["question_id"], r["vendor"]) for r in rows} == {
        (q["id"], v) for q in QUESTIONS for v in ("exa_instant", "exa_deep")}
    assert calls[0] == {"judge_model": "claude-sonnet-5-5"}
    asks = calls[1:]
    assert all(c["max_searches"] == config.LIVE_FILINGS_BUDGET[1] == 1 and c["max_fetches"] == 0 for c in asks)
    assert all(r["judge_model"] == "claude-sonnet-5-5" for r in rows)
    assert all(r["task"] == live_filings.TASK and r["age_s"] > 0 for r in rows)
    assert {r["question_id"]: r["correct"] for r in rows} == {"f1": True, "f2": False}
    assert json.loads((out / "manifest.json").read_text())["task"] == live_filings.TASK
    assert "Accuracy by filing age" in (out / "summary.md").read_text()


def test_resume_skips_finished_asks(tmp_path, monkeypatch):
    calls = []
    _fake(monkeypatch, calls)
    out = tmp_path / "run"
    live_filings.run(QUESTIONS[:1], ["exa_instant"], out_dir=out, today="2026-11-17", data_label="x")
    live_filings.run(QUESTIONS, ["exa_instant"], out_dir=out, today="2026-11-17", data_label="x")
    assert len([c for c in calls if "vendor" in c]) == 2
    assert len((out / "results.jsonl").read_text().splitlines()) == 2


def test_age_is_measured_from_the_filing_time():
    assert live_filings.filed_at(QUESTIONS[1]).isoformat() == "2026-11-17T21:00:00+00:00"
