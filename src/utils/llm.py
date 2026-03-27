"""
Unified LLM call wrapper supporting Anthropic Claude and OpenAI GPT.

Usage:
    from src.utils.llm import call_llm

    response = await call_llm(
        provider="anthropic",
        model="claude-sonnet-4-6",
        system_prompt="You are a ...",
        user_message="Explain X",
        temperature=0.3,
    )
    print(response.content)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Provider = Literal["anthropic", "openai"]


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: Provider

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


async def call_llm(
    provider: Provider,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    max_retries: int = 2,
) -> LLMResponse:
    """
    Call an LLM and return a unified LLMResponse.

    Retries up to max_retries times on transient errors, appending the error
    message to the prompt on subsequent attempts so the model can self-correct.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        effective_message = user_message
        if attempt > 0 and last_error:
            effective_message = (
                f"{user_message}\n\n"
                f"[Previous attempt failed with: {last_error}. Please try again.]"
            )

        try:
            if provider == "anthropic":
                return await _call_anthropic(
                    model, system_prompt, effective_message, temperature, max_tokens
                )
            elif provider == "openai":
                return await _call_openai(
                    model, system_prompt, effective_message, temperature, max_tokens
                )
            else:
                raise ValueError(f"Unknown provider: {provider!r}")
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    max_retries + 1,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
            else:
                raise


async def _call_anthropic(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    import anthropic

    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return LLMResponse(
        content=message.content[0].text,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        model=model,
        provider="anthropic",
    )


async def _call_openai(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    completion = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    choice = completion.choices[0]
    usage = completion.usage
    return LLMResponse(
        content=choice.message.content or "",
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=model,
        provider="openai",
    )
