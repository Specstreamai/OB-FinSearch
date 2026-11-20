"""Perplexity search. Search only: no page fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Perplexity(Adapter):
    env_keys = ("PERPLEXITY_API_KEY",)

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.perplexity.ai/search",
                           json_headers(Authorization=f"Bearer {env('PERPLEXITY_API_KEY')}"),
                           {"query": query, "max_results": min(max_results, 20), "search_context_size": "high"})

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url"), i.get("title"), i.get("snippet"),
                           {"date": i.get("date"), "last_updated": i.get("last_updated")})
                       for i in payload.get("results") or []], max_results)
