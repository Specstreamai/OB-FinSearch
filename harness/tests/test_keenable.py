from harness import adapters, live_collect, search_api


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


def test_keenable_is_one_arm_on_the_board():
    assert "keenable" in adapters.BOARD_VENDORS
    assert not any(v.startswith("keenable_") for v in adapters.BOARD_VENDORS)
    assert adapters.get("keenable").provider == "Keenable"
    assert adapters.required_env(["keenable"]) == ["KEENABLE_API_KEY"]
    assert live_collect.live_limits()["keenable"] == {"rps": 8, "concurrent": 8}
    assert live_collect.limit_for("keenable") is live_collect.limit_for("keenable")


def test_keenable_search_request_contract(monkeypatch):
    monkeypatch.setenv("KEENABLE_API_KEY", "k-secret")
    req = adapters.get("keenable").search_request("AAPL close 2026-10-07", 10)
    assert (req.method, req.url) == ("POST", "https://api.keenable.ai/v1/search")
    assert req.headers == {"X-API-Key": "k-secret", "Content-Type": "application/json"}
    assert req.body == {"query": "AAPL close 2026-10-07", "mode": "pro", "max_results": 10}
    assert adapters.get("keenable").search_request("q", 80).body["max_results"] == 50
    assert adapters.get("keenable").search_request("q", 0).body["max_results"] == 1


def test_keenable_parse_hits_prefers_snippet_and_dedupes():
    k = adapters.get("keenable")
    payload = {"results": [
        {"title": "A", "url": "https://a.example/", "description": "", "snippet": "long snippet",
         "published_at": "2026-10-07"},
        {"title": "B", "url": "https://b.example/", "description": "desc only", "snippet": ""},
        {"title": "no url", "description": "x", "snippet": "y"},
        {"title": "A again", "url": "https://a.example/", "snippet": "dup"},
        "junk",
    ]}
    hits = k.parse_hits(payload, 10)
    assert [(h["url"], h["snippet"]) for h in hits] == [("https://a.example/", "long snippet"),
                                                       ("https://b.example/", "desc only")]
    assert hits[0]["metadata"]["published_at"] == "2026-10-07"
    assert k.parse_hits({}, 10) == [] and k.parse_hits({"results": None}, 10) == []
    assert k.parse_hits(None, 10) == []


def test_keenable_search_cost_uses_credits_else_list_price(monkeypatch):
    _scripted(monkeypatch, [_reply(200, {"results": [], "usage": {"credits": 2}}), _reply(200, {"results": []}),
                            _reply(500, {"error": "boom"})])
    assert adapters.search("keenable", "q").cost_usd == 0.008
    assert adapters.search("keenable", "q").cost_usd == 0.004
    assert adapters.search("keenable", "q").cost_usd == 0.0
    k = adapters.get("keenable")
    assert k.reported_cost({"usage": {"credits": True}}) is None
    assert k.reported_cost({"usage": {"credits": "2"}}) is None and k.reported_cost(None) is None


def test_keenable_fetch_reads_the_indexed_copy(monkeypatch):
    sent = _scripted(monkeypatch, [_reply(200, {"url": "https://a.example/", "title": "A", "content": "page text",
                                                "published_at": 1791331200})])
    vc = adapters.fetch("keenable", "https://a.example/", objective="o", max_chars=30000)
    assert vc.status == "ok" and vc.page["text"] == "page text" and vc.page["title"] == "A"
    assert len(sent) == 1 and (sent[0].method, sent[0].url) == ("GET", "https://api.keenable.ai/v1/fetch")
    assert sent[0].params == {"url": "https://a.example/", "max_chars": 30000, "live": "false"}
    assert vc.cost_usd == 0.004


def test_keenable_fetch_not_indexed_or_empty_is_a_failed_fetch(monkeypatch):
    for reply in (_reply(404, {"detail": "not indexed"}), _reply(200, {"url": "https://a.example/", "content": ""}),
                  _reply(401, {"detail": "bad key"})):
        sent = _scripted(monkeypatch, [reply])
        vc = adapters.fetch("keenable", "https://a.example/", objective="o", max_chars=100)
        assert vc.status == "error" and vc.page is None and vc.cost_usd == 0.0
        assert len(sent) == 1 and sent[0].params["live"] == "false"
