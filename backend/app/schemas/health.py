"""Pydantic response models shared by health and error handlers."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthData(BaseModel):
    """Liveness details for the current service."""

    status: Literal["ok"]
    service: Literal["backend"]
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class HealthResponse(BaseModel):
    """Successful health response using the standard API envelope."""

    success: Literal[True] = True
    data: HealthData


class ErrorDetail(BaseModel):
    """Machine-readable and human-readable error information."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Failed API response using the standard API envelope."""

    success: Literal[False] = False
    error: ErrorDetail


class ApiResponse(BaseModel):
    """Generic successful response model for future endpoints."""

    success: Literal[True] = True
    data: Any
