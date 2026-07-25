"""FastAPI exception handlers producing the BOIP error envelope."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError


def _error_response(code: str, message: str, status_code: int, detail: Any | None = None) -> JSONResponse:
    """Build a response matching the project-wide error contract."""

    error_body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        error_body["detail"] = detail
    body: dict[str, Any] = {"success": False, "error": error_body}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(
        status_code=status_code,
        content=body,
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Handle explicitly raised application errors."""

    return _error_response(exc.code, exc.message, exc.status_code)


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions, including framework-generated 404 responses."""

    detail: Any = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    return _error_response(f"HTTP_{exc.status_code}", message, exc.status_code, detail=detail)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle malformed path, query, or request payload values."""

    return _error_response("VALIDATION_ERROR", "Request validation failed", 422)


async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
    """Prevent internal exception details from leaking to API clients."""

    return _error_response("INTERNAL_ERROR", "Internal server error", 500)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all handlers on a FastAPI application instance."""

    handlers: dict[type[Exception], Callable[..., Any]] = {
        AppError: app_error_handler,
        HTTPException: http_error_handler,
        StarletteHTTPException: http_error_handler,
        RequestValidationError: validation_error_handler,
        Exception: unhandled_error_handler,
    }
    for exception_type, handler in handlers.items():
        app.add_exception_handler(exception_type, handler)
