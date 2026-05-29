"""
perplexity_client.py — Perplexity Deep Research API
Phase 2: ใช้เสริม Literature Agent + Research Q Agent
ต้องมี PERPLEXITY_API_KEY ใน .env
"""
import os
import httpx
from typing import AsyncGenerator

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

def is_available() -> bool:
    return bool(os.getenv("PERPLEXITY_API_KEY"))

async def search(
    query: str,
    model: str = "sonar-deep-research",  # หรือ "sonar-pro"
) -> AsyncGenerator[str, None]:
    """
    Deep research ด้วย Perplexity
    คืน text + citations
    """
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        yield "⚠️ ไม่พบ PERPLEXITY_API_KEY — ข้าม Perplexity search"
        return

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a medical literature search assistant. Focus on Hematology and Precision Medicine. Always include PubMed links and DOIs."
            },
            {
                "role": "user",
                "content": query,
            }
        ],
        "stream": True,
        "return_citations": True,
        "return_related_questions": True,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            PERPLEXITY_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue


async def search_papers(topic: str) -> str:
    """One-shot paper search — คืน full text"""
    result = ""
    async for chunk in search(
        f"Find recent research papers (2020-2025) about: {topic}\n"
        f"Focus on Hematology. Include PubMed links and DOIs for each paper."
    ):
        result += chunk
    return result
