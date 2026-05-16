"""
LLM provider package.

Concrete classes are defined in ``base.py``; per-vendor modules satisfy the
requested folder layout and give stable import paths:

* ``app.ai.providers.openai_provider``
* ``app.ai.providers.claude_provider``
* ``app.ai.providers.local_provider``
"""
from app.ai.providers.base import (
    BaseLLMProvider,
    ClaudeProvider,
    LocalProvider,
    OpenAIProvider,
    get_provider,
)

# Re-import side-effect: keep thin modules importable in isolation.
import app.ai.providers.claude_provider  # noqa: F401
import app.ai.providers.local_provider  # noqa: F401
import app.ai.providers.openai_provider  # noqa: F401

__all__ = [
    "BaseLLMProvider",
    "OpenAIProvider",
    "ClaudeProvider",
    "LocalProvider",
    "get_provider",
]
