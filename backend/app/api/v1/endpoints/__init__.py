"""API v1 endpoint routers."""
from app.api.v1.endpoints.analyse import router as analyse_router
from app.api.v1.endpoints.deals import router as deals_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.notes import router as notes_router
from app.api.v1.endpoints.property import router as property_router
from app.api.v1.endpoints.scan import router as scan_router

__all__ = [
    "health_router",
    "analyse_router",
    "scan_router",
    "deals_router",
    "property_router",
    "notes_router",
]
