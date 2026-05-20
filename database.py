"""Supabase client bootstrap.

Loads SUPABASE_URL + SUPABASE_KEY from the environment (or .env when running
locally) and exposes a single shared `supabase` client.

Production hardening:
  * Never logs the raw URL or key.
  * Raises a clear configuration error instead of crashing with KeyError.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

log = logging.getLogger("kua.database")

# Load .env from this folder when running locally; on Railway the env vars
# come from the platform and .env will not exist.
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is not set. Configure it in Railway → Variables "
        "(or in a local .env file)."
    )

if not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_KEY is not set. Configure it in Railway → Variables "
        "(use the service role key on the backend)."
    )

# Surface only the URL host for ops visibility, never the full URL or key.
try:
    from urllib.parse import urlparse

    _host = urlparse(SUPABASE_URL).hostname or "unknown"
    log.info("Supabase client configured (host=%s)", _host)
except Exception:
    pass

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
