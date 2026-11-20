"""Nimble search and extract. Extract has no public list price: set NIMBLE_EXTRACT_USD_PER_REQUEST to price it."""

from __future__ import annotations

import math
import os

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers


class Nimble(Adapter):
    env_keys = ("NIMBLE_API_KEY",)
    native_fetch = True

    def __init__(self, depth: str):
        self.depth = depth

    def fetch_cost(self):
        raw = os.environ.get("NIMBLE_EXTRACT_USD_PER_REQUEST", "").strip()
        if not raw:
            return None
        value = float(raw)
        if not math.isfinite(value) or value < 0:
            raise ValueError("NIMBLE_EXTRACT_USD_PER_REQUEST must be finite and nonnegative")
        return value

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://sdk.nimbleway.com/v2/search",
                           json_headers(Authorization=f"Bearer {env('NIMBLE_API_KEY')}"),
                           {"query": query, "search_depth": self.depth, "full_content": False,
                            "focus": "general", "max_results": max_results})

    def parse_hits(self, payload, max_results):
        rows = payload.get("results")
        hits = [hit(r["url"].strip(), r.get("title"), r.get("description"))
                for r in (rows if isinstance(rows, list) else [])
                if isinstance(r, dict) and isinstance(r.get("url"), str)]
        return dedupe(hits, max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://sdk.nimbleway.com/v2/extract",
                           json_headers(Authorization=f"Bearer {env('NIMBLE_API_KEY')}"),
                           {"url": url, "formats": ["markdown"]})

    def parse_page(self, payload, url):
        if not isinstance(payload, dict) or payload.get("status") not in (None, "success"):
            raise RuntimeError("Nimble Extract returned an unsuccessful response")
        status = payload.get("status_code")
        if status is not None and not 200 <= int(status) < 300:
            raise RuntimeError(f"Nimble Extract upstream HTTP {status}")
        data = payload.get("data") or {}
        text = data.get("markdown") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Nimble Extract returned no markdown content")
        return text, payload.get("url") or url, ""
