"""Application exception types for consistent API error responses."""


class AppError(Exception):
    """Base application error with a stable error code."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__("NOT_FOUND", message, status_code=404)
