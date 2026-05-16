"""LLM provider abstraction for memo / future extraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseLLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        raise NotImplementedError


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o") -> None:
        import os

        self.model = os.environ.get("OPENAI_MEMO_MODEL", model)

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        import asyncio
        import os
        from openai import OpenAI

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        def _call() -> str:
            r = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
            )
            return r.choices[0].message.content or ""

        return await asyncio.to_thread(_call)


class ClaudeProvider(BaseLLMProvider):
    name = "claude"

    def __init__(self, model: str = "claude-3-5-sonnet-20241022") -> None:
        import os

        self.model = os.environ.get("ANTHROPIC_MEMO_MODEL", model)

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        import asyncio
        import os
        from anthropic import Anthropic

        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        def _call() -> str:
            msg = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if not msg.content:
                return ""
            return "".join(getattr(b, "text", "") for b in msg.content)

        return await asyncio.to_thread(_call)


class LocalProvider(BaseLLMProvider):
    """Stub for Ollama / vLLM. Point `LOCAL_LLM_URL` and `LOCAL_LLM_MODEL`."""

    name = "local"

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        import os

        import httpx

        url = os.environ.get("LOCAL_LLM_URL", "http://localhost:11434/v1/chat/completions")
        model = os.environ.get("LOCAL_LLM_MODEL", "llama3")
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                url,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


def get_provider() -> BaseLLMProvider:
    import os

    p = os.environ.get("LLM_PROVIDER", "openai").lower()
    if p == "claude":
        return ClaudeProvider()
    if p == "local":
        return LocalProvider()
    return OpenAIProvider()
