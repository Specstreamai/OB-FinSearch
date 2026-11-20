"""Tako search and contents. Live lookup also asks for Tako's `data` source, so its price cards come back and
are placed ahead of the web results."""

from __future__ import annotations

from typing import Any

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers

CARD_URL = "tako://card"   # Tako cards are data, not a page to fetch


class Tako(Adapter):
    env_keys = ("TAKO_API_KEY",)
    native_fetch = True

    def search_request(self, query, max_results):
        return HttpRequest("POST", "https://tako.com/api/v3/search", json_headers(**{"X-API-Key": env("TAKO_API_KEY")}),
                           {"query": query, "effort": "fast",
                            "sources": {"web": {"count": min(max_results, 20), "highlights": True}}})

    def parse_hits(self, payload, max_results):
        return dedupe([hit(i.get("url"), i.get("title"), i.get("snippet"),
                           {"source_name": i.get("source_name"), "publish_date": i.get("publish_date")})
                       for i in payload.get("web_results") or []], max_results)

    def live_search_request(self, query, max_results):
        """Live lookup: the `data` source too, so Tako's curated price cards come back with the web results."""
        return HttpRequest("POST", "https://tako.com/api/v3/search", json_headers(**{"X-API-Key": env("TAKO_API_KEY")}),
                           {"query": query, "effort": "fast",
                            "sources": {"data": {"count": 5, "include_contents": True},
                                        "web": {"count": min(max_results, 20), "highlights": True}}})

    def live_parse_hits(self, payload, max_results):
        return card_hits(payload) + self.parse_hits(payload, max_results)

    def fetch_request(self, url, objective, max_chars):
        return HttpRequest("POST", "https://tako.com/api/v1/contents", json_headers(**{"X-API-Key": env("TAKO_API_KEY")}),
                           {"url": url, "mode": "inline", "max_chars": max_chars}, timeout=120)

    def parse_page(self, payload, url):
        item = ((payload or {}).get("contents") or [{}])[0]
        return item.get("data") or "", item.get("source_url") or url, ""


def card_hits(payload: Any) -> list[dict[str, Any]]:
    """Tako data cards as hits: the description, the source, and the last rows of the card's dataset."""
    cards = payload.get("cards") if isinstance(payload, dict) else None
    hits = []
    for i, c in enumerate(cards or []):
        if not isinstance(c, dict):
            continue
        parts = [str(c.get("description") or "").strip(), str(c.get("semantic_description") or "").strip()]
        content = c.get("content") if isinstance(c.get("content"), dict) else {}
        ds = content.get("dataset") if isinstance(content.get("dataset"), dict) else {}
        cols = [str(x.get("name") if isinstance(x, dict) else x) for x in ds.get("columns") or []]
        rows = ds.get("rows") or []
        if cols and rows:
            parts.append("Latest data rows (" + " | ".join(cols) + "): "
                         + "; ".join(" | ".join(str(v) for v in r) for r in rows[-5:] if isinstance(r, list)))
        parts.append("(Tako data card; not a web page, cannot be fetched.)")
        snippet = " ".join(p for p in parts if p)
        if snippet:
            hits.append(hit(c.get("webpage_url") or f"{CARD_URL}/{i}", c.get("title") or "Tako data card", snippet,
                            {"kind": "card", "card_id": c.get("card_id"), "n_rows": len(rows)}))
    return hits
