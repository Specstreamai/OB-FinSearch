"""The grader: Claude compares the agent's answer with the reference answer and tolerance.

Claude Opus 5.5 grades Historical and Multi-Hop Lookup; Claude Sonnet 5.5 grades live company filings. The judge runs on
the Anthropic API (ANTHROPIC_API_KEY) or, with JUDGE_BACKEND=bedrock, on Amazon Bedrock (AWS_BEARER_TOKEN_BEDROCK or the
standard AWS credentials, AWS_REGION; install the `bedrock` extra). Same models and prompt on both.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

JUDGE_MODEL = "claude-opus-5-5"
FILINGS_JUDGE_MODEL = "claude-sonnet-5-5"
JUDGE_EFFORT = "medium"
JUDGE_BACKEND = (os.environ.get("JUDGE_BACKEND") or "anthropic").lower()
# Bedrock: model -> (client class name, Bedrock model id). Opus 5.5 is served on the Mantle endpoint.
BEDROCK = {JUDGE_MODEL: ("AnthropicBedrockMantle", "anthropic.claude-opus-5-5"),
           FILINGS_JUDGE_MODEL: ("AnthropicBedrock", "us.anthropic.claude-sonnet-5-5")}
JUDGE_PROMPT = (Path(__file__).parent / "answer_judge_prompt.txt").read_text().rstrip("\n")


def judge_client(model: str = JUDGE_MODEL) -> Any:
    import anthropic

    if JUDGE_BACKEND == "bedrock":
        return getattr(anthropic, BEDROCK[model][0])(aws_region=os.environ.get("AWS_REGION") or "us-east-1",
                                                      max_retries=4)
    if JUDGE_BACKEND != "anthropic":
        raise RuntimeError(f"JUDGE_BACKEND must be anthropic or bedrock, not {JUDGE_BACKEND!r}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set (see .env.example)")
    return anthropic.Anthropic(max_retries=4)


def parse_judge_payload(text: str) -> dict[str, Any]:
    """The first JSON object that carries a correct/incorrect verdict.

    A reply can mention other braces before that object. Taking the first `{`
    through the last `}` makes a real verdict unreadable.
    """
    decoder = json.JSONDecoder()
    body = text or ""
    index = 0
    while True:
        start = body.find("{", index)
        if start < 0:
            return {}
        try:
            payload, end = decoder.raw_decode(body, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict) and "correct" in payload:
            return payload
        index = end


def judge(client: Any, q: dict[str, Any], candidate: str, model: str = JUDGE_MODEL) -> dict[str, Any]:
    prompt = JUDGE_PROMPT.format(
        question=q["question"], answer=q["answer"], tolerance=q.get("tolerance", ""),
        trap=f"\nTrap (likely wrong answer):\n{q['trap']}\n" if q.get("trap") else "",
        candidate=candidate or "(no answer)",
    )
    t0 = time.perf_counter()
    response = client.messages.create(
        model=BEDROCK[model][1] if JUDGE_BACKEND == "bedrock" else model,
        max_tokens=8000,
        output_config={"effort": JUDGE_EFFORT},
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    base = {"judge_model": model, "judge_ms": latency_ms,
            "judge_input_tokens": response.usage.input_tokens, "judge_output_tokens": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        return base | {"correct": False, "reason": "judge refused", "judge_error": "refusal"}
    text = "".join(b.text for b in response.content if b.type == "text")
    verdict = parse_judge_payload(text)
    if "correct" not in verdict:
        return base | {"correct": False, "reason": f"unparseable judge output: {text[:200]}", "judge_error": "parse"}
    return base | {"correct": bool(verdict["correct"]), "reason": str(verdict.get("reason", ""))}
