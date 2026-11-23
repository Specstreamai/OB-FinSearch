from judge.answer_judge import parse_judge_payload


def test_verdict_after_other_braces_is_read():
    text = 'Checked the set {1, 2}.\n{"correct": true, "reason": "within tolerance"}'
    assert parse_judge_payload(text) == {"correct": True, "reason": "within tolerance"}


def test_prose_without_a_verdict_is_empty():
    assert parse_judge_payload("no json here") == {}


def test_an_earlier_object_without_correct_is_skipped():
    text = '{"note": "see {a}"} {"correct": false, "reason": "wrong year"}'
    assert parse_judge_payload(text)["correct"] is False


class FakeClient:
    def __init__(self):
        self.sent = []
        self.messages = self

    def create(self, **kw):
        from types import SimpleNamespace as NS
        self.sent.append(kw)
        return NS(stop_reason="end_turn", model="x", usage=NS(input_tokens=10, output_tokens=2),
                  content=[NS(type="text", text='{"correct": true, "reason": "ok"}')])


def test_judge_model_and_trap_reach_the_prompt(monkeypatch):
    from judge import answer_judge as aj
    client = FakeClient()
    q = {"question": "Q?", "answer": "A", "tolerance": "exact", "trap": "B"}
    r = aj.judge(client, q, "A", model=aj.FILINGS_JUDGE_MODEL)
    assert client.sent[0]["model"] == "claude-sonnet-5-5" and r["judge_model"] == "claude-sonnet-5-5"
    assert "Trap (likely wrong answer):\nB" in client.sent[0]["messages"][0]["content"]
    aj.judge(client, {"question": "Q?", "answer": "A"}, "A")
    assert client.sent[1]["model"] == "claude-opus-5-5" and "Trap (likely wrong answer)" not in client.sent[1]["messages"][0]["content"]
    monkeypatch.setattr(aj, "JUDGE_BACKEND", "bedrock")
    aj.judge(client, q, "A", model=aj.FILINGS_JUDGE_MODEL)
    aj.judge(client, q, "A")
    assert [s["model"] for s in client.sent[2:]] == ["us.anthropic.claude-sonnet-5-5", "anthropic.claude-opus-5-5"]
