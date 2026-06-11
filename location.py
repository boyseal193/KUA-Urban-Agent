"""Storage vertical geocoding — delegates to shared ``geocoding`` module."""
from __future__ import annotations

from geocoding import geocode_address, geocoding_status, resolve_coordinates

__all__ = ["geocode_address", "geocoding_status", "resolve_coordinates"]
