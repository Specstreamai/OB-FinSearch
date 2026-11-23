"""Parallel search and extract."""

from __future__ import annotations

import re

from ..search_api import Adapter, HttpRequest, dedupe, env, hit, json_headers

_SITE_RE = re.compile(r"(?<![-\w])site:(\"[^\"]*\"|[^\s()]+)", re.I)


def site_filters(query: str, *, paths: bool = True) -> tuple[str, list[str]]:
    """Take the `site:` filters out of a query: (query without them, entries for source_policy.include_domains).

    Entries keep their path unless paths=False; scheme, port, query string, fragment and a leading "www." or "*." are
    dropped, as source_policy accepts none of them. An OR left joining two removed filters is dropped too."""
    found: list[str] = []

    def take(m: re.Match[str]) -> str:
        raw = re.sub(r"^https?://", "", m.group(1).strip("\"'()"), flags=re.I).split("?", 1)[0].split("#", 1)[0]
        host, _, path = raw.partition("/")
        host = host.split(":", 1)[0].lower().removeprefix("*.").removeprefix("www.").strip(".")
        path = path.rstrip("/")
        entry = f"{host}/{path}" if paths and path else host
        if host and entry not in found:
            found.append(entry)
        return " "

    rest = _SITE_RE.sub(take, query)
    rest = re.sub(r"\(\s*(?:OR\s*)*\)", " ", rest)
    rest = re.sub(r"^\s*OR\b|\bOR\s*$", " ", re.sub(r"\bOR(\s+OR\b)+", "OR", re.sub(r"\s+", " ", rest)).strip())
    return re.sub(r"\s+", " ", rest).strip(), found


class Parallel(Adapter):
    """Parallel search. The agent writes an objective and one keyword query; a `site:` filter in the query is sent
    as source_policy.include_domains."""
    env_keys = ("PARALLEL_API_KEY",)
    native_fetch = True
    objective_search = True

    def __init__(self, mode: str):
        self.mode = mode

    def search_request(self, query, max_results, objective=None):
        search_query, include = site_filters(query)
        settings = {"max_results": max_results}
        if include:
            settings["source_policy"] = {"include_domains": include}
        return HttpRequest("POST", "https://api.parallel.ai/v1/search",
                           json_headers(**{"x-api-key": env("PARALLEL_API_KEY")}),
                           {"objective": (objective or "").strip() or query,
                            "search_queries": [search_query or " ".join(include) or query],
                            "mode": self.mode, "advanced_settings": settings},
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
