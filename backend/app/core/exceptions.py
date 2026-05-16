"""Application errors mapped to HTTP responses."""
from __future__ import annotations


class AppError(Exception):
    """Base application error with HTTP status + machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "app_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, status_code=401, code="unauthorized")


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status_code=403, code="forbidden")


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, status_code=404, code="not_found")
