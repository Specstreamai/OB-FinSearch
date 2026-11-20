"""TinyFish search and fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class TinyFish(Adapter):
    env_keys = ("TINYFISH_API_KEY",)
    native_fetch = True

    def search_request(self, query, max_results):
        return HttpRequest("GET", "https://api.search.tinyfish.ai",
                           {"X-API-Key": env("TINYFISH_API_KEY"), "Accept": "application/json"},
                           params={"query": query}, timeout=45)

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url"), i.get("title"), i.get("snippet"),
                           {"site_name": i.get("site_name"), "date": i.get("date")})
                       for i in payload.get("results") or []], max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://api.fetch.tinyfish.ai", json_headers(**{"X-API-Key": env("TINYFISH_API_KEY")}),
                           {"urls": [url], "purpose": objective, "format": "markdown"}, timeout=120)

    def parse_page(self, payload, url):
        item = ((payload or {}).get("results") or [{}])[0]
        return item.get("text") or "", item.get("final_url") or item.get("url") or url, item.get("title") or ""
