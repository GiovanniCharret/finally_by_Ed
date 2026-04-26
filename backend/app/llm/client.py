"""LLM client: LiteLLM -> OpenRouter -> Cerebras with structured output."""

from __future__ import annotations

import os
from typing import Any

import litellm

from .models import LLMResponse

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM client is misconfigured (e.g. missing API key)."""


async def call_llm(messages: list[dict[str, Any]]) -> LLMResponse:
    """Call the LLM via LiteLLM with structured-output parsing.

    Reads OPENROUTER_API_KEY from the environment. Raises
    LLMConfigurationError when the key is missing so callers can surface a
    clean error to the user.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "OPENROUTER_API_KEY is not set; cannot call LLM. "
            "Set the env var or run with LLM_MOCK=true."
        )

    response = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        api_key=api_key,
        response_format=LLMResponse,
        reasoning_effort="low",
        temperature=0.7,
        extra_body=EXTRA_BODY,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty response.")

    return LLMResponse.model_validate_json(content)
