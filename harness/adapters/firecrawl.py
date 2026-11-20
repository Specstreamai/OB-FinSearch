"""Firecrawl search and scrape."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Firecrawl(Adapter):
    env_keys = ("FIRECRAWL_API_KEY",)
    native_fetch = True

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.firecrawl.dev/v2/search",
                           json_headers(Authorization=f"Bearer {env('FIRECRAWL_API_KEY')}"),
                           {"query": query, "limit": max_results})

    def parse_hits(self, payload, max_results):
        data = payload.get("data") or {}
        rows = (data.get("web") or data.get("results") or []) if isinstance(data, dict) else data
        return dedupe([hit(i.get("url") or i.get("link"), i.get("title"), i.get("description") or i.get("snippet"))
                       for i in rows or []], max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://api.firecrawl.dev/v2/scrape",
                           json_headers(Authorization=f"Bearer {env('FIRECRAWL_API_KEY')}"),
                           {"url": url, "formats": ["markdown"], "onlyMainContent": True})

    def parse_page(self, payload, url):
        item = (payload or {}).get("data") or {}
        meta = item.get("metadata") or {}
        return item.get("markdown") or "", meta.get("sourceURL") or url, meta.get("title") or ""
