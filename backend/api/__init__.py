from backend.api.routes import (
    search_router, aircraft_router, pipeline_router, analytics_router
)
from backend.api.documents_api import router as documents_router

__all__ = [
    "documents_router", "search_router",
    "aircraft_router", "pipeline_router", "analytics_router",
]
