"""Keenable search in `pro` mode (its standard index-based setup). Fetch reads Keenable's indexed copy
(GET /v1/fetch, live=false); a page that is not indexed or comes back empty is a failed fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Keenable(Adapter):
    env_keys = ("KEENABLE_API_KEY",)
    native_fetch = True

    def __init__(self, usd_per_credit: float):
        self.usd_per_credit = usd_per_credit

    def reported_cost(self, payload):
        """Keenable reports the credits a call used; each costs usd_per_credit from tools/keenable.yaml."""
        usage = payload.get("usage") if isinstance(payload, dict) else None
        credits = usage.get("credits") if isinstance(usage, dict) else None
        if isinstance(credits, bool) or not isinstance(credits, (int, float)) or credits < 0:
            return None
        return credits * self.usd_per_credit

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.keenable.ai/v1/search",
                           json_headers(**{"X-API-Key": env("KEENABLE_API_KEY")}),
                           {"query": query, "mode": "pro", "max_results": max(1, min(max_results, 50))})

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
