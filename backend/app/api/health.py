"""Backend health-check endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.schemas.health import HealthData, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return liveness information without touching external dependencies."""

    return HealthResponse(
        data=HealthData(
            status="ok",
            service="backend",
            ts=datetime.now(UTC).isoformat(),
        )
    )
