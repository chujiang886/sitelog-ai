"""Project route skeletons."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects() -> dict[str, object]:
    """Return an empty project page until project persistence is implemented."""

    return {"success": True, "data": {"items": [], "total": 0}}
