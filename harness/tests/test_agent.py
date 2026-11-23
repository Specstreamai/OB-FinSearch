"""The agent loop against a scripted model and a fake search API: budgets, fetch guard, answer capture."""
import json
from types import SimpleNamespace as NS

from harness import adapters
from harness.agent import run_agent
from harness.search_api import Adapter, VendorCall


class FakeVendor(Adapter):
    key, provider, env_keys, native_fetch = "fake", "Fake", (), True
    search_unit_cost_usd, fetch_unit_cost_usd = 0.01, 0.001

    def search(self, query, *, max_results=10):
        return VendorCall("ok", 5, {"q": query}, {}, None, [], 0.01,
                          hits=[{"url": "https://seen.example/a", "title": "T", "snippet": f"about {query}"}])

    def fetch(self, url, *, objective, max_chars):
        return VendorCall("ok", 5, {"url": url}, {}, None, [], 0.001,
                          page={"final_url": url, "title": "T", "text": "page", "truncated": False})


adapters.register(FakeVendor())


def call(name, args, cid):
    return NS(type="function_call", name=name, arguments=json.dumps(args), call_id=cid, id=cid)


class ScriptedModel:
    def __init__(self, turns):
        self.turns, self.seen = list(turns), []
        self.responses = self

    def create(self, **kw):
        self.seen.append(kw)
        out = self.turns.pop(0)
        usage = NS(input_tokens=100, output_tokens=10, output_tokens_details=NS(reasoning_tokens=4),
                   input_tokens_details=NS(cached_tokens=20))
        if isinstance(out, str):
            return NS(output=[], output_text=out, usage=usage)
        return NS(output=out, output_text="", usage=usage)


def test_budget_and_fetch_guard():
    model = ScriptedModel([
        [call("web_search", {"query": "q1"}, "c1"), call("web_search", {"query": "q2"}, "c2")],
        [call("web_fetch", {"url": "https://unseen.example", "objective": "x"}, "c3"),
         call("web_fetch", {"url": "https://seen.example/a", "objective": "x"}, "c4")],
        "Answer: 42\nSources: https://seen.example/a",
    ])
    r = run_agent("q", "What?", client=model, vendor="fake", config="c", max_searches=1, max_fetches=2,
                  model="m", effort="high", today="2026-10-03")
    assert r.finished and r.answer.startswith("Answer: 42")
    assert len(r.searches) == 1                      # second search refused: budget 1
    assert len(r.fetches) == 1                       # unseen URL refused
    assert any("unseen" in n for n in r.notes)
    first = model.seen[0]
    assert first["reasoning"] == {"effort": "high"} and first["store"] is False
    assert "Today's date is 2026-10-03." in first["input"][0]["content"]
    assert r.to_dict()["vendor_cost_usd"] == 0.011
    assert r.input_tokens == 300 and r.cached_input_tokens == 60


def test_tools_withdrawn_when_budget_spent():
    model = ScriptedModel([[call("web_search", {"query": "q1"}, "c1")], "Answer: x"])
    run_agent("q", "What?", client=model, vendor="fake", config="c", max_searches=1, max_fetches=0,
              model="m", effort="medium")
    assert [t["name"] for t in model.seen[0]["tools"]] == ["web_search"]
    assert model.seen[1]["tools"] == []


class SlowRetryVendor(FakeVendor):
    key = "fake_retry"

    def search(self, query, *, max_results=10):
        attempts = [{"attempt": 1, "status_code": 429, "latency_ms": 40}, {"attempt": 2, "status_code": 200, "latency_ms": 30}]
        return VendorCall("ok", 1100, {"q": query}, {}, None, attempts, 0.01,
                          hits=[{"url": "https://seen.example/a", "title": "T", "snippet": "s"}])


adapters.register(SlowRetryVendor())


def test_search_latency_excludes_retries_and_tokens_are_kept_per_turn():
    model = ScriptedModel([[call("web_search", {"query": "q1"}, "c1"), call("web_search", {"query": "q2"}, "c2")],
                           "Answer: 1"])
    run = run_agent("q", "Q?", client=model, vendor="fake_retry", config="c", max_searches=2, max_fetches=0,
                    model="m", effort="high", today="2026-11-23")
    d = run.to_dict()
    assert [s.latency_ms for s in run.searches] == [30, 30] and [s.total_ms for s in run.searches] == [1100, 1100]
    assert d["search_ms"] == 60 and d["search_retry_ms"] == 2140 and not d["vendor_error"]
    assert run.wall_ms == run.llm_ms + 30                       # same-turn searches count once, as if in parallel
    assert len(run.turn_usage) == 2 and run.input_tokens == 200 and run.cached_input_tokens == 40
    assert run.output_tokens == 20 and run.reasoning_tokens == 8 and run.model_wait_ms == 0


class FakeObjectiveVendor(Adapter):
    key, provider, env_keys, objective_search = "fake_objective", "Fake objective", (), True

    def __init__(self):
        self.seen = []

    def search(self, query, *, max_results=10, objective=None):
        self.seen.append((query, objective))
        return VendorCall("ok", 5, {}, {}, None, [], 0.0,
                          hits=[{"url": "https://a.example/", "title": "T", "snippet": "s", "published": "2026-07-28"}])


def test_objective_search_api_gets_both_fields_and_dates_reach_the_model():
    vendor = adapters.register(FakeObjectiveVendor())
    model = ScriptedModel([[call("web_search", {"objective": "Find X's 2Q26 revenue.", "search_query": "X 2Q26 revenue"}, "c1")],
                           "Answer: 1\nSources: https://a.example/"])
    r = run_agent("q", "What?", client=model, vendor="fake_objective", config="c", max_searches=1, max_fetches=0,
                  model="m", effort="high")
    tool = model.seen[0]["tools"][0]
    assert tool["parameters"]["required"] == ["objective", "search_query"]
    assert vendor.seen == [("X 2Q26 revenue", "Find X's 2Q26 revenue.")]
    assert r.searches[0].query == "X 2Q26 revenue" and r.searches[0].objective == "Find X's 2Q26 revenue."
    out = json.loads(model.seen[1]["input"][-1]["output"])
    assert out["results"][0]["published"] == "2026-07-28"
    other = ScriptedModel(["Answer: 1"])
    run_agent("q", "What?", client=other, vendor="fake", config="c", max_searches=1, max_fetches=0, model="m", effort="high")
    assert other.seen[0]["tools"][0]["parameters"]["required"] == ["query"]


def test_tool_calls_written_as_text_are_cut_from_the_answer():
    model = ScriptedModel(['to=functions.web_search {"query": "x"}\nAnswer: 42\nSources: https://seen.example/a'])
    r = run_agent("q", "What?", client=model, vendor="fake", config="c", max_searches=1, max_fetches=0,
                  model="m", effort="high")
    assert r.answer == "Answer: 42\nSources: https://seen.example/a"
    assert model.seen[0]["max_output_tokens"] == 64_000
