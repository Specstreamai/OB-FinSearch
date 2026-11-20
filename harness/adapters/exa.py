"""Exa search and contents. Live lookup asks for `livecrawl: always`, so highlights come from a fresh crawl
rather than a cached copy."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Exa(Adapter):
    env_keys = ("EXA_API_KEY",)
    native_fetch = True

    def __init__(self, kind: str):
        self.kind = kind

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://api.exa.ai/search", json_headers(**{"x-api-key": env("EXA_API_KEY")}),
                           {"query": query, "type": self.kind, "numResults": max_results,
                            "contents": {"highlights": True}},
                           timeout=120 if self.kind == "deep" else 60)

    def live_search_request(self, query, max_results):
        """Live lookup: a fresh crawl of each result page instead of Exa's cached copy."""
        return HttpRequest("POST", "https://api.exa.ai/search", json_headers(**{"x-api-key": env("EXA_API_KEY")}),
                           {"query": query, "type": self.kind, "numResults": max_results,
                            "contents": {"highlights": True, "livecrawl": "always"}},
                           timeout=120)

    def parse_hits(self, payload, max_results):
        hits = []
        for item in payload.get("results") or []:
            highlights = item.get("highlights") or []
            snippet = " ".join(x for x in highlights if isinstance(x, str)) or item.get("text")
            hits.append(hit(item.get("url"), item.get("title"), snippet))
        return dedupe(hits, max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://api.exa.ai/contents", json_headers(**{"x-api-key": env("EXA_API_KEY")}),
                           {"urls": [url], "text": {"maxCharacters": max_chars, "includeHtmlTags": False}})

    def parse_page(self, payload, url):
        item = ((payload or {}).get("results") or [{}])[0]
        return item.get("text") or "", item.get("url") or url, item.get("title") or ""
