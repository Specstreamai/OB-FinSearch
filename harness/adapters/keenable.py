"""Keenable search, in `pro` or `realtime` mode, and its indexed-page fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Keenable(Adapter):
    """Keenable search. Fetch reads Keenable's indexed copy of the page (live=false); a page that is not indexed, or
    comes back empty, is a failed fetch. Keenable reports the credits each call used; they are priced at
    usd_per_credit from tools/keenable.yaml."""
    env_keys = ("KEENABLE_API_KEY",)
    native_fetch = True

    def __init__(self, mode: str, usd_per_credit: float):
        self.mode, self.usd_per_credit = mode, usd_per_credit

    def reported_cost(self, payload):
        usage = payload.get("usage") if isinstance(payload, dict) else None
        credits = usage.get("credits") if isinstance(usage, dict) else None
        if isinstance(credits, bool) or not isinstance(credits, (int, float)) or credits < 0:
            return None
        return credits * self.usd_per_credit

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.keenable.ai/v1/search",
                           json_headers(**{"X-API-Key": env("KEENABLE_API_KEY")}),
                           {"query": query, "mode": self.mode, "max_results": max(1, min(max_results, 50))})

    def parse_hits(self, payload, max_results):
        rows = payload.get("results") if isinstance(payload, dict) else None
        return dedupe([hit(r.get("url"), r.get("title"), r.get("snippet") or r.get("description"),
                           {"published_at": r.get("published_at"), "acquired_at": r.get("acquired_at")})
                       for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)], max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("GET", "https://api.keenable.ai/v1/fetch", {"X-API-Key": env("KEENABLE_API_KEY")},
                           params={"url": url, "max_chars": int(max_chars), "live": "false"})

    def parse_page(self, payload, url):
        item = payload if isinstance(payload, dict) else {}
        return item.get("content") or "", item.get("url") or url, item.get("title") or ""
