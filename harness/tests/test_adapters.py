"""Request and response contracts of individual adapters, and the publication dates added to hits."""
from harness import adapters, live_collect, search_api
from harness.adapters.parallel import site_filters


def _reply(status, payload):
    return search_api.VendorCall("ok" if status < 400 else "error", 5, {"url": "x"}, payload,
                                 None if status < 400 else f"HTTP {status}: {payload}",
                                 [{"attempt": 1, "status_code": status, "latency_ms": 5}])


def _scripted(monkeypatch, replies):
    sent = []

    def fake_send(req, **_):
        sent.append(req)
        return replies.pop(0)

    monkeypatch.setattr(search_api, "send", fake_send)
    monkeypatch.setattr(search_api, "assert_public_url", lambda url: None)
    return sent


def test_site_filters_become_include_domains():
    assert site_filters("site:sec.gov/Archives/edgar/data/1 10-Q") == ("10-Q", ["sec.gov/Archives/edgar/data/1"])
    assert site_filters("(site:ecb.europa.eu OR site:federalreserve.gov) EUR USD rate") == (
        "EUR USD rate", ["ecb.europa.eu", "federalreserve.gov"])
    assert site_filters("site:https://www.Investor.ResMed.com/news/ GLP-1") == ("GLP-1", ["investor.resmed.com/news"])
    assert site_filters("site:sec.gov/Archives 10-Q", paths=False) == ("10-Q", ["sec.gov"])
    assert site_filters("Boeing backlog Q2 2026") == ("Boeing backlog Q2 2026", [])


def test_parallel_sends_objective_and_keyword_query(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    sent = _scripted(monkeypatch, [_reply(200, {"results": []}), _reply(200, {"results": []})])
    adapters.search("parallel_advanced", "Trustmark CET1 2Q26 site:investors.trustmark.com/news",
                    objective="Find Trustmark's CET1 ratio at 30 June 2026.")
    assert sent[0].body == {"objective": "Find Trustmark's CET1 ratio at 30 June 2026.",
                            "search_queries": ["Trustmark CET1 2Q26"], "mode": "advanced",
                            "advanced_settings": {"max_results": 10,
                                                  "source_policy": {"include_domains": ["investors.trustmark.com/news"]}}}
    adapters.search("parallel_fast", "Boeing backlog Q2 2026")       # no objective: the query stands in for it
    assert sent[1].body["objective"] == "Boeing backlog Q2 2026" and "source_policy" not in sent[1].body["advanced_settings"]


def test_publication_dates_are_added_to_hits(monkeypatch):
    monkeypatch.setenv("PARALLEL_API_KEY", "k")
    _scripted(monkeypatch, [_reply(200, {"results": [
        {"url": "https://a.example/", "title": "A", "excerpts": ["x"], "publish_date": "2026-07-28"},
        {"url": "https://b.example/", "title": "B", "excerpts": ["y"]}]})])
    hits = adapters.search("parallel_fast", "q").hits
    assert hits[0]["published"] == "2026-07-28" and "published" not in hits[1]
    assert search_api.result_dates({"results": [{"link": "https://c.example/", "timestamp": 1785222000}]}) == {
        "https://c.example/": "2026-07-28"}


def test_keenable_pro_and_realtime(monkeypatch):
    assert {"keenable_pro", "keenable_realtime"} <= set(adapters.BOARD_VENDORS)
    assert adapters.required_env(["keenable_pro"]) == ["KEENABLE_API_KEY"]
    assert live_collect.limit_for("keenable_pro") is live_collect.limit_for("keenable_realtime")
    monkeypatch.setenv("KEENABLE_API_KEY", "k")
    sent = _scripted(monkeypatch, [_reply(200, {"results": [{"url": "https://a.example/", "title": "A", "snippet": "s",
                                                             "published_at": "2026-10-07T00:00:00Z"}],
                                                "usage": {"credits": 2}}),
                                   _reply(200, {"results": []}),
                                   _reply(200, {"url": "https://a.example/", "title": "A", "content": "page"}),
                                   _reply(200, {"url": "https://a.example/", "content": ""})])
    call = adapters.search("keenable_pro", "q", max_results=80)
    assert sent[0].body == {"query": "q", "mode": "pro", "max_results": 50}
    assert call.cost_usd == 0.008 and call.hits[0]["published"] == "2026-10-07"
    assert adapters.search("keenable_realtime", "q").cost_usd == 0.004 and sent[1].body["mode"] == "realtime"
    page = adapters.fetch("keenable_pro", "https://a.example/", objective="o", max_chars=100)
    assert page.page["text"] == "page" and sent[2].params == {"url": "https://a.example/", "max_chars": 100, "live": "false"}
    assert adapters.fetch("keenable_pro", "https://a.example/", objective="o", max_chars=100).status == "error"
