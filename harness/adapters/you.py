"""You.com web search with highlights, and its contents endpoint."""

from __future__ import annotations

from typing import Any

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers

KNOWLEDGE_URL = "you://knowledge"   # knowledge blocks have no page to fetch


class You(Adapter):
    """You.com web search with highlights. With `core` set it also asks for the knowledge block, which often
    holds the figure itself with an as-of time; each block is added as a hit ahead of the web results."""
    env_keys = ("YOU_API_KEY",)
    native_fetch = True

    def __init__(self, core: bool):
        self.core = core

    def search_request(self, query, max_results):
        body = {"count": min(max_results, 20), "extraction": {"extraction_mode": "highlights"}, "query": query}
        if self.core:
            body["knowledge"] = "core"
        return HttpRequest("POST", "https://ydc-index.io/v1/search",
                           json_headers(**{"X-API-Key": env("YOU_API_KEY")}), body)

    def parse_hits(self, payload, max_results):
        results = payload.get("results") or {}
        hits = []
        for item in results.get("web") or []:
            contents = item.get("contents") or {}
            snippets = contents.get("highlights") or item.get("snippets") or []
            snippet = "\n".join(v for v in snippets if isinstance(v, str))
            hits.append(hit(item.get("url"), item.get("title"), snippet or item.get("description"),
                            {"page_age": item.get("page_age")}))
        return knowledge_hits(payload) + dedupe(hits, max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://ydc-index.io/v1/contents",
                           json_headers(**{"X-API-Key": env("YOU_API_KEY")}),
                           {"urls": [url], "formats": ["markdown", "metadata"]})

    def parse_page(self, payload, url):
        item = (payload if isinstance(payload, list) else [{}])[0]
        return item.get("markdown") or item.get("html") or "", item.get("url") or url, item.get("title") or ""


def knowledge_hits(payload: Any) -> list[dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, dict) else None
    hits = []
    for i, item in enumerate((results or {}).get("knowledge") or []):
        if not isinstance(item, dict):
            continue
        sources = ", ".join(a.get("name", "") for a in item.get("attribution") or [] if isinstance(a, dict))
        parts = [str(item.get("description") or "").strip()]
        if item.get("as_of"):
            parts.append(f"(as of {item['as_of']})")
        if sources:
            parts.append(f"Sources: {sources}.")
        parts.append("(Answer box; not a web page, cannot be fetched.)")
        snippet = " ".join(p for p in parts if p)
        if snippet:
            hits.append({"url": f"{KNOWLEDGE_URL}/{i}", "title": str(item.get("title") or "You.com knowledge"),
                         "snippet": snippet[:4000],
                         "metadata": {"kind": "knowledge", "type": item.get("type"), "as_of": item.get("as_of"),
                                      "attribution": item.get("attribution")}})
    return hits
