"""认证路由（Phase 2.2 / 2.2.6）。

- ``POST /api/auth/login``：邮箱+密码 → 签发 access token（匿名可访问）；
- ``GET /api/auth/me``：返回当前登录用户主体（需认证）。

统一返回项目信封 ``{success, data}``；认证失败由 ``security.get_current_user``
经 ``error_handler`` 包装为 ``{success:false, error:{code,message}}``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    AuthConfigError,
    CurrentUser,
    create_access_token,
    DEFAULT_TOKEN_TTL_MINUTES,
    get_current_user,
    resolve_principals,
    verify_password,
)
from app.db.models.user import User
from app.db.session import async_get_db


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """登录请求体。"""

    email: str
    password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(async_get_db),
) -> dict[str, object]:
    """校验邮箱+密码，成功签发 HS256 access token。"""

    user = (
        await db.scalars(select(User).filter_by(email=body.email))
    ).one_or_none()
    # 统一错误文案，避免泄露用户是否存在
    if (
        user is None
        or user.deleted_at is not None
        or user.status != "active"
        or not verify_password(body.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    roles, permissions = await resolve_principals(db, user)
    primary_role = roles[0] if roles else "customer"
    try:
        token = create_access_token(
            sub=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            role=primary_role,
            roles=roles,
            permissions=sorted(permissions),
        )
    except AuthConfigError as exc:  # JWT_SECRET 未配置
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "success": True,
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": DEFAULT_TOKEN_TTL_MINUTES * 60,
        },
    }


@router.get("/me")
async def me(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    """返回当前登录用户主体（id / tenant_id / email / roles / permissions）。"""

    return {
        "success": True,
        "data": {
            "id": str(current_user.id),
            "tenant_id": str(current_user.tenant_id),
            "email": current_user.email,
            "roles": current_user.roles,
            "permissions": sorted(current_user.permissions),
        },
    }


__all__ = ["LoginRequest", "router"]
