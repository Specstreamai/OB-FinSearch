from harness import search_api


def test_api_key_headers_are_redacted():
    class Resp:
        ok, status_code = True, 200

        def json(self):
            return {}

    vc = search_api.send(search_api.HttpRequest("GET", "https://x.example", {"X-API-Key": "k-secret", "x-api-key": "k2"}),
                         request_fn=lambda **_: Resp())
    assert vc.raw_request["headers"] == {"X-API-Key": search_api.REDACTED, "x-api-key": search_api.REDACTED}
    assert "k-secret" not in str(vc.raw_request)
