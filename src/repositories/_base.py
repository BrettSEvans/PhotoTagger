"""Base repository class with shared connection and lock."""

import sqlite3
import threading


class BaseRepository:
    """Base class for all repositories - provides shared DB connection and lock."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        """Initialize with shared connection and lock."""
        self._conn = conn
        self._lock = lock
