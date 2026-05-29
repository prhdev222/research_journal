"""Provider adapters for optional AI team members.

api_key priority: explicit param > env var > error
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    text: str
    model: str = ""


async def call_openrouter(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> ProviderResponse:
    key = api_key or _require_env("OPENROUTER_API_KEY")
    selected_model = model or os.getenv("OPENROUTER_DEFAULT_MODEL") or "openai/gpt-4.1-mini"
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    text = await _call_openai_compatible("openrouter", base_url, key, selected_model, prompt, system_prompt)
    return ProviderResponse("openrouter", text, selected_model)


async def call_zai(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> ProviderResponse:
    key = api_key or _require_env("ZAI_API_KEY")
    base_url = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
    selected_model = model or os.getenv("ZAI_DEFAULT_MODEL") or "glm-4.5"
    text = await _call_openai_compatible("zai", base_url, key, selected_model, prompt, system_prompt)
    return ProviderResponse("zai", text, selected_model)


async def call_gemini(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> ProviderResponse:
    key = api_key or _require_env("GEMINI_API_KEY")
    selected_model = model or os.getenv("GEMINI_DEFAULT_MODEL") or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{url}?key={key}", json={"contents": contents})
        res.raise_for_status()
    data = res.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    return ProviderResponse("gemini", text, selected_model)


async def _call_openai_compatible(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
        )
        res.raise_for_status()
    data = res.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured — add API key via team setup or set env var")
    return value
