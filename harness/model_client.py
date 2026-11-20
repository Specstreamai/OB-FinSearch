"""The agent's model client: any OpenAI-compatible Responses API endpoint."""

from __future__ import annotations

import os
from typing import Any


def agent_client(timeout: int = 240) -> Any:
    """OpenAI client for the agent, from OPENAI_API_KEY. Uses the Responses API with reasoning items."""
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set (see .env.example)")
    return OpenAI(timeout=timeout, max_retries=1)
