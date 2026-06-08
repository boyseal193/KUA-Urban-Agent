"""
K.U.A. Laundry Acquisition vertical — production package.

This is the canonical, deployed laundromat module. It runs alongside the
self-storage vertical on the same FastAPI app (`main.py`) and uses the same
infrastructure (Supabase REST persistence, `jobs.store` async queue, the
existing worker loop). The reference implementation under
``backend/app/laundry/`` is kept as design / type / unit-test material but
is NOT deployed.

Public surface
--------------

- ``laundry.api.router``                 — FastAPI router (prefix ``/laundry``)
- ``laundry.worker.run_laundry_scan``    — entry point the orchestrator calls
- ``laundry.assumptions.LaundryAssumptions``
- ``laundry.economics.calculate_economics``
- ``laundry.scoring.score_property``
- ``laundry.memo.generate_ic_memo``
"""
__version__ = "2.0.0"
