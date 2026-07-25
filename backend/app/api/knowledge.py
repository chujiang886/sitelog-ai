"""Knowledge base route skeletons."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/rules")
async def list_knowledge_rules() -> dict[str, object]:
    """Return an empty rule page until knowledge storage is implemented."""

    return {"success": True, "data": {"items": [], "total": 0}}
