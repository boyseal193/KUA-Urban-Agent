"""Shared SlowAPI limiter (bind to ``app.state.limiter`` in ``main``)."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

# Instantiated at import; ensure working directory / env is loaded before importing app.main
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_settings().RATE_LIMIT_DEFAULT],
)
