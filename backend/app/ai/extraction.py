"""Structured extraction from raw listing text (legacy OpenAI `extractor.py`)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from extractor import extract_property_from_text as _extract_sync  # noqa: E402


def extract_listing(raw_text: str) -> Dict[str, Any]:
    return _extract_sync(raw_text)


async def extract_listing_async(raw_text: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_extract_sync, raw_text)
