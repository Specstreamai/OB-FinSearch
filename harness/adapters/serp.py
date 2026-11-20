"""Google results through a RapidAPI SERP endpoint. Search only: no page fetch."""

from __future__ import annotations

from ..search_api import Adapter, HttpRequest, dedupe, env, hit


class Serp(Adapter):
    env_keys = ("RAPIDAPI_KEY",)

    def search_request(self, query, max_results):
        return HttpRequest("GET", "https://google-search74.p.rapidapi.com/",
                           {"x-rapidapi-key": env("RAPIDAPI_KEY"), "x-rapidapi-host": "google-search74.p.rapidapi.com"},
                           params={"query": query, "limit": max_results}, timeout=45)

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url") or i.get("link"), i.get("title"), i.get("description") or i.get("snippet"))
                       for i in payload.get("results") or []], max_results)
