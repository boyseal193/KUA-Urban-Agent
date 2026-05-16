"""Excel export — wraps legacy `excel_exporter` at repository root."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from excel_exporter import export_scan_to_excel as _legacy_export  # noqa: E402


def export_scan_excel(
    *,
    successful_results: List[Dict[str, Any]],
    grouped: Dict[str, Any],
    search_url: str,
    filters_used: Dict[str, Any],
) -> str:
    """Writes under repo `exports/` (ensure volume mount in Docker for persistence)."""
    return _legacy_export(
        results=successful_results,
        top_deals=grouped.get("approved_candidates", []),
        manual_review=grouped.get("manual_review_deals", []),
        rejected_history=grouped.get("rejected_deals", []),
        errors=grouped.get("failed_results", []),
        filters_used=filters_used,
        search_url=search_url,
    )
