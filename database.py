import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Force load .env from the SAME folder as this file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

print("ENV FILE EXISTS:", env_path.exists())
print("SUPABASE_URL RAW:", os.environ.get("SUPABASE_URL"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise ValueError("Missing SUPABASE_URL in .env")

if not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)