"""FastAPI routers for the laundry vertical (all mounted under ``/laundry``)."""
from app.laundry.api.router import router as laundry_router

__all__ = ["laundry_router"]
