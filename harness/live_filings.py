"""Live filings: questions about company filings published that day, each sent once to every search API.

The agent gets one search on the board's agent model. Each answer is graded as it finishes by judge/answer_judge.py,
on Claude Sonnet 5.5.
Every row keeps the time it was sent and how long the filing had been public at that moment (age_s), so results can
be read by filing age.

Calls are paced per API key with the live lookup limits (harness/live_collect.py).

Output: runs/live-filings/<stamp>/ with manifest.json, results.jsonl and summary.md. A run can be resumed: finished
rows are skipped.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from judge.answer_judge import FILINGS_JUDGE_MODEL, JUDGE_EFFORT, judge, judge_client
from judge.board_summary import read_rows, write_summary

from . import config
from .agent import run_agent
from .live_collect import limit_for
from .model_client import agent_client

TASK = "live-filings"


def filed_at(q: dict) -> datetime:
    return datetime.fromisoformat(q["filed_at"].replace("Z", "+00:00")).astimezone(timezone.utc)


def run(questions: list[dict], vendor_keys: list[str], *, out_dir: Path, today: str, data_label: str,
        concurrency: int = 32) -> Path:
    cfg, searches, fetches = config.LIVE_FILINGS_BUDGET
    model, effort = config.CLASS_MODELS["single"]
    price_model = config.REFERENCE_MODELS["single"][0]
    manifest_path = out_dir / "manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    done = {(r["question_id"], r["vendor"]) for r in read_rows(out_dir)}
    jobs = [(q, v) for q in questions for v in vendor_keys if (q["id"], v) not in done]
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps({
            "task": TASK, "data": data_label, "vendors": vendor_keys, "today_in_prompt": today,
            "setup": {"config": cfg, "searches": searches, "fetches": fetches, "model": model, "effort": effort},
            "judge": FILINGS_JUDGE_MODEL, "judge_effort": JUDGE_EFFORT, "prices_usd_per_m": config.PRICES,
            "question_ids": [q["id"] for q in questions], "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, indent=2))
    print(f"{len(questions)} questions x {len(vendor_keys)} vendors -> {len(jobs)} asks to do ({len(done)} done), "
          f"{searches} search on {model} ({effort}) -> {out_dir}", flush=True)

    model_client, grader = agent_client(), judge_client(FILINGS_JUDGE_MODEL)
    lock = threading.Lock()

    def work(job):
        q, vendor = job
        limit = limit_for(vendor)
        limit.acquire()
        try:
            sent = datetime.now(timezone.utc)
            result = run_agent(q["id"], q["question"], client=model_client, vendor=vendor, config=cfg,
                               max_searches=searches, max_fetches=fetches, model=model, today=today, effort=effort)
        finally:
            limit.release()
        row = result.to_dict()
        row.update({"repeat": 0, "reasoning_effort": effort, "search_class": "single", "task": TASK,
                    "question": q["question"], "reference_answer": q["answer"], "tolerance": q.get("tolerance", ""),
                    "filed_at": q["filed_at"], "sent_at": sent.isoformat(),
                    "age_s": round((sent - filed_at(q)).total_seconds())})
        try:
            row.update(judge(grader, q, result.answer, model=FILINGS_JUDGE_MODEL))
        except Exception as exc:  # noqa: BLE001 - keep the paid agent run; re-grade later with `rejudge`
            row.update({"correct": False, "reason": "", "judge_error": f"{type(exc).__name__}: {exc}"[:500]})
        row["llm_cost_usd"] = round(config.llm_cost(price_model, row["input_tokens"],
                                                    row.get("cached_input_tokens", 0), row["output_tokens"]), 6)
        row["judge_cost_usd"] = round(config.llm_cost(FILINGS_JUDGE_MODEL, row.get("judge_input_tokens") or 0, 0,
                                                      row.get("judge_output_tokens") or 0), 6)
        return row

    errors = judge_fails = 0
    spent = 0.0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(work, job): job for job in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            q, vendor = futures[fut]
            try:
                row = fut.result()
            except Exception:  # noqa: BLE001 - the ask is retried on resume
                errors += 1
                print(f"  [{i}/{len(jobs)}] {q['id']} {vendor} ERROR\n{traceback.format_exc(limit=3)}", file=sys.stderr)
                continue
            with lock, open(results_path, "a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            spent += row["llm_cost_usd"] + row["judge_cost_usd"] + (row.get("vendor_cost_usd") or 0)
            judge_fails += bool(row.get("judge_error"))
            verdict = "JUDGE FAILED" if row.get("judge_error") else ("correct" if row["correct"] else "wrong")
            print(f"  [{i}/{len(jobs)}] {q['id']} {vendor}: {verdict} (age {row['age_s'] / 3600:.1f}h) | errors {errors}, "
                  f"judge fails {judge_fails}, spent ${spent:.2f}", flush=True)

    path = write_summary(out_dir)
    print(f"summary: {path}")
    if errors:
        print(f"{errors} asks failed; run again with --resume {out_dir} to retry them", file=sys.stderr)
    if judge_fails:
        print(f"{judge_fails} judge calls failed; re-grade with `finsearch rejudge {out_dir}`", file=sys.stderr)
    return out_dir
