"""Tavily search and extract."""

from __future__ import annotations

from typing import Any

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Tavily(Adapter):
    env_keys = ("TAVILY_API_KEY",)
    native_fetch = True

    def __init__(self, depth: str, extra: dict[str, Any] | None = None):
        self.depth, self.extra = depth, extra or {}

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.tavily.com/search",
                           json_headers(Authorization=f"Bearer {env('TAVILY_API_KEY')}"),
                           {"query": query, "max_results": max_results, "search_depth": self.depth, **self.extra})

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url"), i.get("title"), i.get("content"), {"score": i.get("score")})
                       for i in payload.get("results") or []], max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://api.tavily.com/extract",
                           json_headers(Authorization=f"Bearer {env('TAVILY_API_KEY')}"),
                           {"urls": [url], "extract_depth": "advanced"})

    def parse_page(self, payload, url):
        item = ((payload or {}).get("results") or [{}])[0]
        return item.get("raw_content") or item.get("content") or "", item.get("url") or url, ""
