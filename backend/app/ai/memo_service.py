"""IC memo orchestration (sync legacy + optional async LLM path)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

import structlog

log = structlog.get_logger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from memo import generate_ic_memo as _generate_ic_memo_sync  # noqa: E402

from app.ai.providers.base import get_provider


class MemoService:
    async def generate_ic_memo(
        self,
        property_data: dict,
        economics: Dict[str, Any],
        score: Dict[str, Any],
        *,
        use_llm_rewrite: bool = False,
    ) -> str:
        """
        Primary path: deterministic memo from `memo.py` (institutional template).

        Optional: `use_llm_rewrite=True` runs a second pass through the configured
        LLM provider for stylistic polish (keeps facts unchanged — operator review required).
        """
        base = await asyncio.to_thread(_generate_ic_memo_sync, property_data, economics, score)
        if not use_llm_rewrite:
            return base

        provider = get_provider()
        system = (
            "You are an institutional real estate IC memo editor. "
            "Preserve all numbers and facts exactly. Improve clarity and tone only. "
            "Output valid Markdown."
        )
        user = base
        try:
            return await provider.complete(system, user)
        except Exception as e:
            log.warning("memo.llm_rewrite_failed", error=str(e))
            return base


memo_service = MemoService()
