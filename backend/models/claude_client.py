"""
claude_client.py — Anthropic API wrapper
- streaming support
- prompt caching headers
- model_used logging
"""
import os
from typing import AsyncGenerator
import anthropic

_client: anthropic.AsyncAnthropic | None = None

def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client

async def call(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int = 4096,
) -> str:
    """One-shot call — return full text"""
    client = get_client()
    response = await client.messages.create(
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.content[0].text

async def stream(
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """Streaming call — yield text chunks"""
    client = get_client()
    async with client.messages.stream(
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    ) as s:
        async for text in s.text_stream:
            yield text
