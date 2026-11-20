"""Brave web search. Search only: no page fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit


class Brave(Adapter):
    env_keys = ("BRAVE_SEARCH_API_KEY",)

    def search_request(self, query, max_results):
        return HttpRequest("GET", "https://api.search.brave.com/res/v1/web/search",
                           {"X-Subscription-Token": env("BRAVE_SEARCH_API_KEY"), "Accept": "application/json"},
                           params={"q": query, "count": min(max_results, 20), "result_filter": "web"}, timeout=45)

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url"), i.get("title"), i.get("description") or i.get("snippet"))
                       for i in (payload.get("web") or {}).get("results") or []], max_results)
