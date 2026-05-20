"""Structured errors for the K.U.A. job store."""

from __future__ import annotations

from typing import List, Optional


class DatabaseSetupError(Exception):
    """Raised when required Supabase pipeline tables are missing."""

    def __init__(self, missing_tables: List[str], message: Optional[str] = None):
        self.missing_tables = missing_tables
        if message:
            self.message = message
        elif len(missing_tables) == 1:
            self.message = (
                f"Database setup incomplete: missing {missing_tables[0]} table. "
                "Run jobs/schema.sql in the Supabase SQL Editor."
            )
        else:
            self.message = (
                "Database setup incomplete: missing "
                + ", ".join(missing_tables)
                + " tables. Run jobs/schema.sql in the Supabase SQL Editor."
            )
        super().__init__(self.message)


class StoreError(Exception):
    """Raised when a Supabase store operation fails."""

    def __init__(
        self,
        message: str,
        *,
        table: str,
        operation: str,
        retryable: bool = False,
        cause: Optional[Exception] = None,
    ):
        self.table = table
        self.operation = operation
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
