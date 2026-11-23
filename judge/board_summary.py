"""Board numbers from a run's results.jsonl.

Per (task, vendor): accuracy is the mean over repeats of each repeat's accuracy, sd the sample standard
deviation across repeats, ci the 95% normal interval over all graded runs, flip the share of questions whose
verdict differs between repeats. Rows whose judge call failed are left out (re-grade them with `rejudge`),
not counted wrong. An answer whose every search call failed counts as wrong (run it again with
`finsearch run --resume <dir> --retry-vendor-errors`), except in live filings, where a day can't be re-run: there
it is left out and counted per vendor. Rows that carry age_s (live filings) also get accuracy per vendor by filing age.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

LIVE_FILINGS = "live-filings"   # harness/live_filings.py TASK
AGE_BANDS = ((0, 7200, "under 2 h"), (7200, 21600, "2 to 6 h"), (21600, None, "6 h and over"))   # seconds


def age_band(age_s: float) -> str:
    return next(label for lo, hi, label in AGE_BANDS if age_s >= lo and (hi is None or age_s < hi))


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0
    return m, sd


def compute_summary(rows: list[dict]) -> dict:
    acc: dict = defaultdict(lambda: defaultdict(list))
    per_q: dict = defaultdict(list)
    graded = [r for r in rows if not r.get("judge_error") and not (r.get("vendor_error") and r["task"] == LIVE_FILINGS)]
    for r in graded:
        correct = bool(r["correct"]) and not r.get("vendor_error")
        for task in (r["task"], "all"):
            acc[(task, r["vendor"])][r.get("repeat", 0)].append(correct)
        per_q[(r["task"], r["vendor"], r["question_id"])].append(correct)
    cells = []
    for (task, vendor), reps in sorted(acc.items()):
        per_rep = [sum(v) / len(v) for v in reps.values()]
        m, sd = _mean_sd(per_rep)
        n_runs = sum(len(v) for v in reps.values())
        ci = 1.96 * math.sqrt(m * (1 - m) / n_runs) if n_runs else 0.0
        qs = [v for k, v in per_q.items() if k[1] == vendor and (task == "all" or k[0] == task)]
        multi = [v for v in qs if len(v) > 1]
        flip = sum(1 for v in multi if len(set(v)) > 1) / max(1, len(multi))
        cells.append({"task": task, "vendor": vendor, "questions": max(len(v) for v in reps.values()),
                      "repeats": len(reps), "accuracy": m, "sd": sd, "ci": ci, "flip": flip, "n_runs": n_runs})
    by_age: dict = defaultdict(list)
    for r in graded:
        if r.get("age_s") is not None:
            by_age[(r["vendor"], age_band(r["age_s"]))].append(r["correct"])
    order = [label for *_, label in AGE_BANDS]
    age = [{"vendor": v, "band": b, "accuracy": sum(x) / len(x), "n": len(x)}
           for (v, b), x in sorted(by_age.items(), key=lambda kv: (kv[0][0], order.index(kv[0][1])))]
    cost: dict = defaultdict(float)
    for r in rows:
        cost[(r["vendor"], "llm")] += r.get("llm_cost_usd", 0)
        cost[(r["vendor"], "judge")] += r.get("judge_cost_usd", 0)
        cost[(r["vendor"], "vendor_api")] += r.get("vendor_cost_usd", 0) or 0
    return {"cells": cells, "age": age, "cost": dict(cost), "usage": usage_summary(rows), "n_rows": len(rows),
            "n_graded": len(graded), "judge_errors": sum(1 for r in rows if r.get("judge_error")),
            "vendor_errors": sum(1 for r in rows if r.get("vendor_error"))}


def _pct(xs: list[float], q: float) -> float | None:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, math.ceil(q * len(xs)) - 1)] if xs else None


def usage_summary(rows: list[dict]) -> list[dict]:
    """Per vendor: answers, answers whose every search failed, searches per answer, per-call search latency of the
    attempt that returned (median, p95), failed calls, time lost to retries, per-answer wall time and tokens."""
    by_vendor: dict = defaultdict(list)
    for r in rows:
        by_vendor[r["vendor"]].append(r)
    out = []
    for vendor, rs in sorted(by_vendor.items()):
        calls = [c for r in rs for c in r.get("searches") or []]
        ok_ms = [c["latency_ms"] for c in calls if c.get("status") == "ok"]
        walls = [r["wall_ms"] for r in rs if r.get("wall_ms")]
        out.append({
            "vendor": vendor, "answers": len(rs), "vendor_errors": sum(1 for r in rs if r.get("vendor_error")),
            "searches_per_answer": len(calls) / len(rs), "search_calls": len(calls),
            "failed_calls": sum(1 for c in calls if c.get("status") != "ok"),
            "search_ms_median": _pct(ok_ms, 0.5), "search_ms_p95": _pct(ok_ms, 0.95),
            "retry_ms": sum(r.get("search_retry_ms") or 0 for r in rs),
            "wall_ms_median": _pct(walls, 0.5),
            **{k: sum(r.get(k) or 0 for r in rs) for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                                                            "reasoning_tokens", "judge_input_tokens", "judge_output_tokens")},
        })
    return out


def usage_lines(usage: list[dict]) -> list[str]:
    def num(x: float | None, scale: float = 1) -> str:
        return "" if x is None else f"{x / scale:,.1f}" if scale != 1 else f"{x:,.0f}"

    lines = ["", "## Search calls, latency and tokens", "",
             "Search latency is per call, for the attempt that returned; failed attempts and backoff are in Retry s. "
             "Wall time is model time plus, per turn, the slowest search, without rate-limit backoff. "
             "Answers whose every search failed are left out of accuracy.", "",
             "| Vendor | Answers | Every search failed | Searches / answer | Failed calls | Search ms median | Search ms p95 | "
             "Retry s | Wall s median | Input tok | Cached tok | Output tok | Reasoning tok | Judge in tok | Judge out tok |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for u in usage:
        lines.append(f"| {u['vendor']} | {u['answers']} | {u['vendor_errors']} | {u['searches_per_answer']:.1f} | "
                     f"{u['failed_calls']} | {num(u['search_ms_median'])} | {num(u['search_ms_p95'])} | "
                     f"{u['retry_ms'] / 1000:,.1f} | {num(u['wall_ms_median'], 1000)} | {u['input_tokens']:,} | "
                     f"{u['cached_input_tokens']:,} | {u['output_tokens']:,} | {u['reasoning_tokens']:,} | "
                     f"{u['judge_input_tokens']:,} | {u['judge_output_tokens']:,} |")
    return lines


def read_rows(out_dir: Path) -> list[dict]:
    path = out_dir / "results.jsonl"
    if not path.exists():
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_summary(out_dir: Path) -> Path:
    s = compute_summary(read_rows(out_dir))
    lines = ["# Finance search run", "", f"Run directory: `{out_dir}`", "",
             "Accuracy is the mean over repeats; SD is across repeats; the 95% CI uses all graded runs. "
             "Flip rate is the share of questions with different verdicts across repeats.", "",
             "| Task | Vendor | Questions | Repeats | Accuracy | SD | 95% CI | Flip rate |",
             "|---|---|---|---|---|---|---|---|"]
    for c in s["cells"]:
        lines.append(f"| {c['task']} | {c['vendor']} | {c['questions']} | {c['repeats']} | {c['accuracy']:.1%} | "
                     f"{c['sd'] * 100:.1f} pts | ±{c['ci'] * 100:.1f} pts | {c['flip']:.0%} |")
    if s["age"]:
        lines += ["", "## Accuracy by filing age", "", "| Vendor | Filing age | Answers | Accuracy |", "|---|---|---|---|"]
        lines += [f"| {a['vendor']} | {a['band']} | {a['n']} | {a['accuracy']:.1%} |" for a in s["age"]]
    lines += ["", "## Cost (USD)", "", "| Vendor | LLM | Judge | Search API | Total |", "|---|---|---|---|---|"]
    for v in sorted({k[0] for k in s["cost"]}):
        parts = [s["cost"].get((v, k), 0.0) for k in ("llm", "judge", "vendor_api")]
        lines.append(f"| {v} | ${parts[0]:.2f} | ${parts[1]:.2f} | ${parts[2]:.2f} | ${sum(parts):.2f} |")
    lines += usage_lines(s["usage"])
    lines += ["", f"Runs: {s['n_rows']}; graded: {s['n_graded']}; judge errors (left out of accuracy, "
                  f"re-grade with `finsearch rejudge`): {s['judge_errors']}; answers whose every search failed "
                  f"(counted wrong, left out in live filings; re-run with `--resume <dir> --retry-vendor-errors`): "
                  f"{s['vendor_errors']}"]
    path = out_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(
        {**s, "cost": [{"vendor": k[0], "kind": k[1], "usd": v} for k, v in s["cost"].items()]}, indent=1))
    return path
