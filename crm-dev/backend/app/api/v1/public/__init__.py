# app/api/v1/public/__init__.py
from .slots import router as slots_router
from .bookings import router as public_bookings_router
from .tables import router as tables_public

__all__ = ["slots_router", "public_bookings_router", "tables_public"]