"""Database package — schema, lazy init, and async connection helper."""

from .database import get_db, init_db

__all__ = ["get_db", "init_db"]
