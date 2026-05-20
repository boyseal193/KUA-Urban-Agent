"""Structured errors for the K.U.A. job store.

DatabaseSetupError now carries BOTH missing tables and missing columns so
the frontend can render an exact "what to fix" message instead of failing
one column at a time.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class DatabaseSetupError(Exception):
    """Raised when required Supabase pipeline tables or columns are missing."""

    def __init__(
        self,
        missing_tables: Optional[List[str]] = None,
        missing_columns: Optional[Dict[str, List[str]]] = None,
        message: Optional[str] = None,
    ):
        self.missing_tables: List[str] = list(missing_tables or [])
        self.missing_columns: Dict[str, List[str]] = {
            t: list(cols) for t, cols in (missing_columns or {}).items() if cols
        }

        if message:
            self.message = message
        else:
            parts: List[str] = []
            if self.missing_tables:
                if len(self.missing_tables) == 1:
                    parts.append(f"missing {self.missing_tables[0]} table")
                else:
                    parts.append(
                        "missing tables: " + ", ".join(self.missing_tables)
                    )
            if self.missing_columns:
                col_descriptions = [
                    f"{t}({', '.join(cols)})" for t, cols in self.missing_columns.items()
                ]
                parts.append("missing columns: " + "; ".join(col_descriptions))

            if not parts:
                self.message = "Database setup incomplete."
            else:
                self.message = (
                    "Database setup incomplete: "
                    + "; ".join(parts)
                    + ". Run jobs/schema.sql in the Supabase SQL Editor."
                )

        super().__init__(self.message)


class StoreError(Exception):
    """Raised when a Supabase store operation fails for a non-setup reason."""

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
