"""ARQ jobs for the laundry vertical (independent from storage worker)."""
from app.laundry.workers.tasks import run_laundry_scan_job

__all__ = ["run_laundry_scan_job"]
