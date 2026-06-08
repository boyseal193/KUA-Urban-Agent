"""
AI sub-package for the laundry vertical.

Sub-modules are intentionally **not** imported here. Each consumer imports
``from app.laundry.ai.extraction import extract_listing`` (or memo /
due_diligence) directly so that simply touching the package does not pull in
the heavy LLM-provider dependency chain.
"""

__all__ = []
