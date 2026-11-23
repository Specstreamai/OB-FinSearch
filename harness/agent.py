"""The search agent: the model calls web_search (and, in search_fetch mode, web_fetch) until it answers or its
budget runs out.

Only searches and fetches are budgeted; turns are capped only as a safety net. A fetch is allowed only for a URL
that appeared in an earlier search result, so the model can't skip search by recalling URLs. Reasoning items
are carried between turns (store=False plus encrypted reasoning), so the model keeps its plan.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import adapters
from .config import FETCH_MAX_CHARS, MAX_RESULTS, SAFETY_MAX_TURNS
from .search_api import VendorCall

SYSTEM_PROMPT = (Path(__file__).parent / "agent_prompt.txt").read_text().rstrip("\n")

WEB_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": "Search the web. Returns up to 10 web results with url, title, snippet and the publication date when the provider gives one, plus any data records the search provider adds.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The search query."}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}

# For search APIs that take a research objective with a keyword query (Adapter.objective_search): the model writes
# both. Field descriptions follow the API's own documentation.
OBJECTIVE_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": WEB_SEARCH_TOOL["description"],
    "parameters": {
        "type": "object",
        "properties": {
            "objective": {"type": "string", "description": (
                "Natural-language description of the underlying question or goal driving the search. Used together "
                "with search_queries to focus results on the most relevant content. Should be self-contained with "
                "enough context to understand the intent of the search.")},
            "search_query": {"type": "string", "description": (
                "Concise keyword search query, 3-6 words each. Only one query is required. Used together with "
                "objective to focus results on the most relevant content.")},
        },
        "required": ["objective", "search_query"],
        "additionalProperties": False,
    },
    "strict": True,
}

WEB_FETCH_TOOL = {
    "type": "function",
    "name": "web_fetch",
    "description": (
        "Fetch the text of a page that appeared in an earlier search result. "
        "Use it when the snippet doesn't contain the figure you need."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "A URL from an earlier search result."},
            "objective": {"type": "string", "description": "What you need from the page."},
        },
        "required": ["url", "objective"],
        "additionalProperties": False,
    },
    "strict": True,
}


@dataclass
class SearchRecord:
    seq: int
    query: str
    status: str
    latency_ms: int
    cost_usd: float | None
    hits: list[dict[str, Any]]
    error: str | None
    raw_response: Any = None
    total_ms: int = 0         # latency_ms plus failed attempts and retry backoff
    attempts: int = 1
    objective: str = ""       # objective search APIs only: the objective the model wrote; query is its search_query


@dataclass
class FetchRecord:
    seq: int
    url: str
    objective: str
    status: str
    latency_ms: int
    cost_usd: float | None
    final_url: str = ""
    title: str = ""
    text: str = ""
    truncated: bool = False
    error: str | None = None
    raw_response: Any = None
    total_ms: int = 0
    attempts: int = 1


@dataclass
class RunResult:
    question_id: str
    vendor: str
    config: str
    max_searches: int
    max_fetches: int
    model: str
    answer: str = ""
    finished: bool = False
    notes: list[str] = field(default_factory=list)
    searches: list[SearchRecord] = field(default_factory=list)
    fetches: list[FetchRecord] = field(default_factory=list)
    turns: int = 0
    llm_ms: int = 0           # model time, without our rate-limit backoff
    model_wait_ms: int = 0    # rate-limit backoff on the model (ours, not the search API's)
    wall_ms: int = 0          # model time plus, per turn, the slowest search or fetch (same-turn calls as if parallel), no backoff
    elapsed_ms: int = 0       # clock time of the whole run, backoff and sequential calls included
    turn_usage: list[dict[str, int]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["n_searches"] = len(self.searches)
        d["n_fetches"] = len(self.fetches)
        d["vendor_cost_usd"] = round(
            sum(s.cost_usd or 0 for s in self.searches) + sum(f.cost_usd or 0 for f in self.fetches), 6
        )
        d["search_ms"] = sum(s.latency_ms for s in self.searches)
        d["fetch_ms"] = sum(f.latency_ms for f in self.fetches)
        d["search_retry_ms"] = sum(s.total_ms - s.latency_ms for s in self.searches)
        d["vendor_error"] = bool(self.searches) and all(s.status != "ok" for s in self.searches)
        return d


def _get(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def _as_input(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):   # SDK object: keep every field (reasoning items need encrypted_content)
        return item.model_dump(exclude_none=True)
    return {k: v for k, v in {
        "type": _get(item, "type"),
        "id": _get(item, "id"),
        "call_id": _get(item, "call_id"),
        "name": _get(item, "name"),
        "arguments": _get(item, "arguments"),
    }.items() if v is not None}


def _tool_output(call: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": _get(call, "call_id") or _get(call, "id"),
        "output": json.dumps(payload, ensure_ascii=False),
    }


def _args(call: Any) -> dict[str, Any]:
    raw = _get(call, "arguments", "")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}



RETRY_COUNTS: dict[int, int] = {}  # status code -> retries so far (read by the runner for live error counts)


def _timing(vc: Any) -> tuple[int, int, int]:
    """(latency of the attempt that returned, total including failed attempts and backoff, attempts made)."""
    attempts = [a for a in (getattr(vc, "attempts", None) or []) if isinstance(a, dict) and a.get("latency_ms") is not None]
    if not attempts:
        return vc.latency_ms, vc.latency_ms, 1
    return int(attempts[-1]["latency_ms"]), vc.latency_ms, len(attempts)


# After its budget is spent the model sometimes writes tool calls out as text ("to=functions.web_search {...}")
# before its answer; the saved answer keeps only the part from its last "Answer:" on.
_TOOL_TEXT = re.compile(r"to=(functions\.|web\.|multi_tool_use\.|web_search)")


def _final_text(text: str) -> str:
    text = text.strip()
    if _TOOL_TEXT.search(text) and "Answer:" in text:
        return text[text.rfind("Answer:"):].strip()
    return text


def _create_with_backoff(client: Any, max_wait_s: float = 600, wait: list[float] | None = None, **kwargs: Any) -> Any:
    """responses.create, retrying 429s and transient server errors with exponential backoff (up to ~10 min)."""
    delay, waited = 5.0, 0.0
    while True:
        try:
            return client.responses.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            if status not in (429, 500, 502, 503, 504) or waited >= max_wait_s:
                raise
            RETRY_COUNTS[status] = RETRY_COUNTS.get(status, 0) + 1
            time.sleep(delay)
            waited += delay
            if wait is not None:
                wait.append(delay)
            delay = min(delay * 2, 60.0)

def run_agent(
    question_id: str,
    question: str,
    *,
    client: Any,
    vendor: str,
    config: str,
    max_searches: int,
    max_fetches: int,
    model: str,
    today: str | None = None,
    effort: str,
) -> RunResult:
    run = RunResult(question_id, vendor, config, max_searches, max_fetches, model)
    fetch_clause = f" and up to {max_fetches} web_fetch call(s)" if max_fetches else " (no page fetching)"
    system = SYSTEM_PROMPT.format(today=today or date.today().isoformat(), max_searches=max_searches, fetch_clause=fetch_clause)
    conversation: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    search_tool = OBJECTIVE_SEARCH_TOOL if adapters.get(vendor).objective_search else WEB_SEARCH_TOOL
    tools = [search_tool] + ([WEB_FETCH_TOOL] if max_fetches else [])
    seen_urls: set[str] = set()
    started = time.perf_counter()

    for _turn in range(SAFETY_MAX_TURNS):
        budget_left = len(run.searches) < max_searches or len(run.fetches) < max_fetches
        t0 = time.perf_counter()
        waits: list[float] = []
        response = _create_with_backoff(
            client,
            wait=waits,
            model=model,
            reasoning={"effort": effort},
            tools=tools if budget_left else [],
            input=conversation,
            max_output_tokens=64_000,
            store=False,
            include=["reasoning.encrypted_content"],   # store=False: carry reasoning between turns ourselves
        )
        waited_ms = int(sum(waits) * 1000)
        run.llm_ms += int((time.perf_counter() - t0) * 1000) - waited_ms
        run.model_wait_ms += waited_ms
        turn_llm_ms = int((time.perf_counter() - t0) * 1000) - waited_ms
        run.turns += 1
        usage = _get(response, "usage")
        if usage is not None:
            run.input_tokens += int(_get(usage, "input_tokens", 0) or 0)
            run.output_tokens += int(_get(usage, "output_tokens", 0) or 0)
            details = _get(usage, "output_tokens_details")
            run.reasoning_tokens += int(_get(details, "reasoning_tokens", 0) or 0) if details is not None else 0
            in_details = _get(usage, "input_tokens_details")
            run.cached_input_tokens += int(_get(in_details, "cached_tokens", 0) or 0) if in_details is not None else 0
            run.turn_usage.append({
                "input": int(_get(usage, "input_tokens", 0) or 0),
                "cached_input": int(_get(in_details, "cached_tokens", 0) or 0) if in_details is not None else 0,
                "output": int(_get(usage, "output_tokens", 0) or 0),
                "reasoning": int(_get(details, "reasoning_tokens", 0) or 0) if details is not None else 0,
            })

        calls = [i for i in (_get(response, "output") or []) if _get(i, "type") == "function_call"]
        run.wall_ms += turn_llm_ms
        turn_tool_ms = 0
        if not calls:
            run.answer = _final_text(_get(response, "output_text") or "")
            run.finished = True
            break
        for item in _get(response, "output") or []:   # keep reasoning so the model doesn't lose its plan
            conversation.append(_as_input(item))
        for call in calls:
            name, args = _get(call, "name"), _args(call)
            if name == "web_search":
                if len(run.searches) >= max_searches:
                    conversation.append(_tool_output(call, {"error": "search budget exhausted; no more tool calls are possible. Write your final answer now, in the Answer / Sources format, with what you have"}))
                    continue
                query = str(args.get("search_query") or args.get("query") or "").strip()
                objective = str(args.get("objective") or "").strip()
                vc = adapters.search(vendor, query, max_results=MAX_RESULTS, objective=objective or None)
                hits = vc.hits or []
                latency, total, n_attempts = _timing(vc)
                turn_tool_ms = max(turn_tool_ms, latency)
                seen_urls.update(h["url"] for h in hits if str(h.get("url") or "").startswith(("http://", "https://")))
                run.searches.append(SearchRecord(
                    len(run.searches) + 1, query, vc.status, latency, vc.cost_usd, hits, vc.error, vc.raw_response,
                    total_ms=total, attempts=n_attempts, objective=objective,
                ))
                payload = {"results": [{"url": h["url"], "title": h["title"], "snippet": h["snippet"],
                                        **({"published": h["published"]} if h.get("published") else {})} for h in hits]}
                if vc.status != "ok":
                    payload = {"error": vc.error or vc.status, "results": []}
                conversation.append(_tool_output(call, payload))
            elif name == "web_fetch":
                url = str(args.get("url") or "").strip()
                objective = str(args.get("objective") or "")
                if len(run.fetches) >= max_fetches:
                    conversation.append(_tool_output(call, {"error": "fetch budget exhausted; no more tool calls are possible. Write your final answer now, in the Answer / Sources format, with what you have"}))
                    continue
                if url not in seen_urls:
                    run.notes.append(f"rejected fetch of unseen URL: {url}")
                    conversation.append(_tool_output(call, {"error": "you can only fetch URLs that appeared in earlier search results"}))
                    continue
                try:
                    vc = adapters.fetch(vendor, url, objective=objective, max_chars=FETCH_MAX_CHARS)
                except Exception as exc:  # noqa: BLE001 - recorded, the run continues
                    vc = VendorCall("error", 0, {"url": url}, None, f"{type(exc).__name__}: {exc}", [], 0.0)
                page = vc.page or {}
                latency, total, n_attempts = _timing(vc)
                turn_tool_ms = max(turn_tool_ms, latency)
                run.fetches.append(FetchRecord(
                    len(run.fetches) + 1, url, objective, vc.status, latency, vc.cost_usd,
                    page.get("final_url", ""), page.get("title", ""), page.get("text", ""),
                    bool(page.get("truncated")), vc.error, None, total_ms=total, attempts=n_attempts,
                ))
                payload = {"url": page.get("final_url", url), "title": page.get("title", ""), "text": page.get("text", "")}
                if vc.status != "ok":
                    payload = {"error": vc.error or vc.status}
                conversation.append(_tool_output(call, payload))
            else:
                conversation.append(_tool_output(call, {"error": f"unknown tool {name}"}))
        run.wall_ms += turn_tool_ms
    else:
        run.notes.append("hit the safety turn cap without a final answer")

    run.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return run
