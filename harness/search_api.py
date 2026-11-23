"""The search-API adapter interface and the shared HTTP plumbing.

An adapter turns a query into one HTTP request and the response into a list of hits
(url, title, snippet, and the publication date when the API returns one). Vendors with a documented page-extraction endpoint also implement fetch.
There is deliberately no generic HTTP fetch fallback: a vendor without a native fetch is search-only,
so every vendor is measured on what its own API returns.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import requests

REDACTED = "***REDACTED***"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class VendorCall:
    """One search or fetch call: what was sent, what came back, and what it cost."""
    status: str                       # ok | error | unavailable
    latency_ms: int
    raw_request: dict[str, Any]
    raw_response: Any
    error: str | None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    hits: list[dict[str, Any]] | None = None
    page: dict[str, Any] | None = None


@dataclass
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    timeout: int = 90


def json_headers(**extra: str) -> dict[str, str]:
    return {**extra, "Content-Type": "application/json"}


def hit(url: Any, title: Any, snippet: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"url": str(url or ""), "title": str(title or ""), "snippet": str(snippet or "")[:4000],
            "metadata": metadata or {}}


def dedupe(hits: list[dict[str, Any]], max_results: int) -> list[dict[str, Any]]:
    out, seen = [], set()
    for h in hits:
        url = h["url"].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(h)
        if len(out) >= max_results:
            break
    return out


def reported_cost(payload: Any) -> float | None:
    """The call's dollar cost when the vendor reports it in the response (Exa, some others)."""
    if not isinstance(payload, dict):
        return None
    cost = payload.get("costDollars")
    candidate = cost.get("total") if isinstance(cost, dict) else None
    if candidate is None and isinstance(payload.get("usage"), dict):
        candidate = payload["usage"].get("total_cost_usd")
    try:
        total = float(candidate)
    except (TypeError, ValueError):
        return None
    return total if total >= 0 else None


DATE_KEYS = ("published_at", "publishedDate", "publish_date", "page_age", "date", "timestamp")


def _day(value: Any) -> str | None:
    """A date value as YYYY-MM-DD: ISO strings keep their date part, Unix timestamps are read as UTC."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        try:
            return datetime.fromtimestamp(int(value), timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    m = re.match(r"\d{4}-\d{2}-\d{2}", str(value).strip())
    return m.group(0) if m else None


def result_dates(payload: Any) -> dict[str, str]:
    """URL -> publication date, from every result object in a response that carries both."""
    dates: dict[str, str] = {}
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            url = node.get("url") or node.get("link")
            day = next((d for d in (_day(node.get(k)) for k in DATE_KEYS) if d), None)
            if isinstance(url, str) and day:
                dates.setdefault(url, day)
            stack.extend(node.values())
    return dates


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _redact(headers: dict[str, str]) -> dict[str, str]:
    return {k: REDACTED if any(t in k.lower() for t in ("key", "token", "authorization", "secret")) else v
            for k, v in headers.items()}


def _json_or_text(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"_raw": str(getattr(response, "text", ""))[:100_000]}


def send(req: HttpRequest, *, retries: int = 3,
         request_fn: Callable[..., Any] = requests.request,
         sleep_fn: Callable[[float], None] = time.sleep) -> VendorCall:
    """Send with up to `retries` retries on 429/5xx and network errors (backoff 1, 2, 4 s)."""
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    payload: Any = None
    error: str | None = None
    for attempt in range(1, retries + 2):
        t0 = time.perf_counter()
        try:
            response = request_fn(method=req.method, url=req.url, headers=req.headers, json=req.body,
                                  params=req.params, timeout=req.timeout)
            payload = _json_or_text(response)
            attempts.append({"attempt": attempt, "status_code": response.status_code,
                             "latency_ms": round((time.perf_counter() - t0) * 1000)})
            if response.ok:
                error = None
                break
            error = f"HTTP {response.status_code}: {str(payload)[:500]}"
            if response.status_code not in RETRYABLE_STATUS or attempt > retries:
                break
        except Exception as exc:  # noqa: BLE001 - recorded; the agent sees an error result
            error = f"{type(exc).__name__}: {exc}"
            attempts.append({"attempt": attempt, "status_code": None,
                             "latency_ms": round((time.perf_counter() - t0) * 1000), "error": error})
            if attempt > retries:
                break
        sleep_fn(min(2 ** (attempt - 1), 8))
    return VendorCall(
        status="ok" if error is None else "error",
        latency_ms=round((time.perf_counter() - started) * 1000),
        raw_request={"method": req.method, "url": req.url, "headers": _redact(req.headers),
                     "body": req.body, "params": req.params},
        raw_response=payload, error=error, attempts=attempts,
    )


def assert_public_url(url: str) -> None:
    """Fetch only public http(s) URLs: no credentials, localhost or private networks."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("web_fetch requires a public absolute http(s) URL")
    if parsed.hostname.lower() == "localhost":
        raise ValueError("web_fetch blocks localhost and private networks")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("web_fetch blocks localhost and private networks")


class Adapter:
    """Subclass this to add a search API. Implement the two search methods, and the two fetch methods too if the
    API has a page-extraction endpoint (and set native_fetch). The key, name, prices and live-lookup pacing of
    each setup come from tools/<tool>.yaml (see harness/adapters/__init__.py)."""

    key: str = ""                          # setup name used on the command line and the board
    provider: str = ""                     # display name
    env_keys: tuple[str, ...] = ()         # environment variables the adapter needs
    search_unit_cost_usd: float | None = None   # list price per search, used when the response has no cost
    fetch_unit_cost_usd: float | None = None
    live_limit: dict[str, float] | None = None  # live-lookup pacing per API key: rps, per_minute, concurrent
    native_fetch: bool = False
    objective_search: bool = False         # the API takes a research objective with the keyword query; the agent
                                           # then writes both, and search_request gets `objective`

    # --- search ---
    def search_request(self, query: str, max_results: int) -> HttpRequest:
        raise NotImplementedError

    def parse_hits(self, payload: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    # --- live lookup (optional) ---
    def live_search_request(self, query: str, max_results: int) -> HttpRequest:
        """The request live lookup sends. By default the same as search_request. Override it to switch on a
        vendor's freshness options (a live crawl, a data source) for live lookup only: historical and
        multi-hop lookup never call it, so their boards are unaffected."""
        return self.search_request(query, max_results)

    def live_parse_hits(self, payload: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
        return self.parse_hits(payload, max_results)

    # --- fetch (optional) ---
    def fetch_request(self, url: str, objective: str, max_chars: int) -> HttpRequest:
        raise NotImplementedError

    def parse_page(self, payload: Any, url: str) -> tuple[str, str, str]:
        """(text, final_url, title) of the fetched page."""
        raise NotImplementedError

    # --- shared behaviour ---
    def fetch_cost(self) -> float | None:
        return self.fetch_unit_cost_usd

    def reported_cost(self, payload: Any) -> float | None:
        """The call's cost as the response reports it, or None to use the list price."""
        return reported_cost(payload)

    def search(self, query: str, *, max_results: int = 10, live: bool = False,
               objective: str | None = None) -> VendorCall:
        """live=True is live lookup: the live_* hooks are used instead of search_request / parse_hits.
        `objective` reaches search_request only on an objective_search API."""
        if live:
            req = self.live_search_request(query, max_results)
        elif self.objective_search:
            req = self.search_request(query, max_results, objective=objective)
        else:
            req = self.search_request(query, max_results)
        call = send(req)
        if call.status == "ok":
            payload = call.raw_response if isinstance(call.raw_response, dict) else {}
            call.hits = self.live_parse_hits(payload, max_results) if live else self.parse_hits(payload, max_results)
            dates = result_dates(call.raw_response)
            for h in call.hits:
                if dates.get(h.get("url")):
                    h["published"] = dates[h["url"]]
            reported = self.reported_cost(call.raw_response)
            call.cost_usd = reported if reported is not None else self.search_unit_cost_usd
        else:
            call.hits, call.cost_usd = [], 0.0
        return call

    def fetch(self, url: str, *, objective: str, max_chars: int) -> VendorCall:
        if not self.native_fetch:
            return VendorCall("unavailable", 0, {"url": url, "vendor": self.key}, None,
                              "this search API has no native page fetch", [], None)
        assert_public_url(url)
        call = send(self.fetch_request(url, objective, max_chars))
        if call.status == "ok":
            try:
                text, final_url, title = self.parse_page(call.raw_response, url)
                if not str(text).strip():
                    raise RuntimeError(f"{self.key} fetch returned no page content")
                call.page = {"requested_url": url, "final_url": str(final_url or url), "title": str(title or ""),
                             "text": str(text)[:max_chars], "truncated": len(str(text)) > max_chars}
            except Exception as exc:  # noqa: BLE001
                call.status, call.error = "error", f"{type(exc).__name__}: {exc}"
        reported = self.reported_cost(call.raw_response)
        call.cost_usd = (reported if reported is not None else self.fetch_cost()) if call.status == "ok" else 0.0
        return call
