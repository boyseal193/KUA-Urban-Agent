"""
K.U.A. Laundry Acquisition Engine.

A fully independent vertical that mirrors the architecture of the storage
pipeline but never imports from it. Anything in :mod:`app.laundry` is safe to
delete, refactor or replace without touching the storage code path.

Public sub-packages:

* ``app.laundry.assumptions`` — adjustable financial / operating constants
* ``app.laundry.economics``   — deterministic underwriting math
* ``app.laundry.scoring``     — location + opportunity scoring engine
* ``app.laundry.ai``          — LLM extraction + memo + due diligence
* ``app.laundry.scanners``    — URL / text / area discovery
* ``app.laundry.services``    — pipeline + scan orchestration
* ``app.laundry.exports``     — Excel / CSV / JSON / ZIP packages
* ``app.laundry.workers``     — ARQ background jobs (laundry-only)
* ``app.laundry.api``         — FastAPI routers under ``/laundry/*``
"""
from __future__ import annotations

__all__ = ["VERSION"]

VERSION = "1.0.0"
