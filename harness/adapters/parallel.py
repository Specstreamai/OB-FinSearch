"""Parallel search and extract."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Parallel(Adapter):
    env_keys = ("PARALLEL_API_KEY",)
    native_fetch = True

    def __init__(self, mode: str):
        self.mode = mode

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.parallel.ai/v1/search",
                           json_headers(**{"x-api-key": env("PARALLEL_API_KEY")}),
                           {"objective": query, "search_queries": [query], "mode": self.mode,
                            "advanced_settings": {"max_results": max_results}},
                           timeout=120 if self.mode == "advanced" else 60)

    def parse_hits(self, payload, max_results):
        hits = [hit(i.get("url"), i.get("title"), "\n".join(x for x in i.get("excerpts") or [] if isinstance(x, str)))
                for i in payload.get("results") or []]
        return dedupe(hits, max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://api.parallel.ai/v1/extract",
                           json_headers(**{"x-api-key": env("PARALLEL_API_KEY")}),
                           {"urls": [url], "objective": objective, "max_chars_total": max_chars,
                            "advanced_settings": {"full_content": True}}, timeout=120)

    def parse_page(self, payload, url):
        item = ((payload or {}).get("results") or [{}])[0]
        return (item.get("full_content") or "\n".join(item.get("excerpts") or []),
                item.get("url") or url, item.get("title") or "")
