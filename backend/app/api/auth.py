"""认证路由（Phase 2.2 / 2.2.6；Phase 3.8.29 T1/T4 生产安全强化）。

- ``POST /api/auth/login``    邮箱+密码 → 签发 access token，并种下 **HttpOnly**
  ``boip_access_token`` Cookie + 非 HttpOnly 的 ``boip_csrf_token`` Cookie；
  响应体仍返回 ``access_token``（供 API 客户端走 Bearer 路径）。
- ``POST /api/auth/logout``   清除凭据与 CSRF Cookie（fail-closed：无论如何先清）。
- ``POST /api/auth/refresh``  在宽限期内用旧 token 换取新 token，重种 Cookie。
- ``GET  /api/auth/me``      当前登录用户主体（需认证）。

统一返回项目信封 ``{success, data}``；认证失败由 ``security.get_current_user``
经 ``error_handler`` 包装为 ``{success:false, error:{code,message}}``。

安全事件（login / logout / token_refresh）追加写入 ``AuditLog``（append-only，
见 ``app.core.security_audit``），用于事后还原"谁在何时登入/登出/续期"。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_cookies import (
    clear_auth_cookie,
    clear_csrf_cookie,
    generate_csrf_token,
    resolve_raw_token,
    set_auth_cookie,
    set_csrf_cookie,
)
from app.core.config import get_settings
from app.core.csrf import csrf_protect
from app.core.security import (
    AuthConfigError,
    AuthError,
    CurrentUser,
    create_access_token,
    DEFAULT_TOKEN_TTL_MINUTES,
    get_current_user,
    peek_access_token,
    resolve_principals,
    verify_password,
)
from app.core.security_audit import record_security_event
from app.db.models.user import User
from app.db.session import async_get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """登录请求体。"""

    email: str
    password: str


def _extract_token(request: Request) -> str | None:
    """取本次请求的裸凭据 —— 复用全局唯一的优先级规则。

    这里**必须**与 ``security.get_current_user`` / ``identity.dependencies``
    走同一个 :func:`resolve_raw_token`：显式 ``Authorization`` 头优先、Cookie
    只在完全没给头时兜底、显式非法头不回落。

    早期版本在本文件里另写了一份"Cookie 优先"的解析，后果不是风格问题而是
    真实事故：浏览器登录过 A、脚本带着 B 的 Bearer 头调 ``/refresh``，
    实际续的是 A 的会话、审计也记成 A —— 责任人张冠李戴。``/logout`` 同理，
    会把"另一个人"标记为登出。凭据解析只能有一处实现。
    """

    return resolve_raw_token(
        request,
        request.headers.get("Authorization"),
        settings=get_settings(),
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(async_get_db),
) -> dict[str, object]:
    """校验邮箱+密码，成功签发 HS256 access token 并种下 HttpOnly Cookie。"""

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
    settings = get_settings()
    try:
        token = create_access_token(
            sub=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            role=primary_role,
            roles=roles,
            permissions=sorted(permissions),
            expires_minutes=settings.token_ttl_minutes or DEFAULT_TOKEN_TTL_MINUTES,
        )
    except AuthConfigError as exc:  # JWT_SECRET 未配置
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 凭据 Cookie：HttpOnly + Secure(生产) + SameSite，JS 读不到明文。
    set_auth_cookie(response, token, settings=settings)
    # CSRF 双提交令牌：非 HttpOnly，供前端在变更请求里回传。
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token, settings=settings)

    # 审计：登录成功（append-only）。
    await record_security_event(
        db,
        action="login",
        tenant_id=user.tenant_id,
        actor_id=user.id,
        target_id=str(user.id),
        detail=f"email={user.email}",
    )

    return {
        "success": True,
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "csrf_token": csrf_token,
            "expires_in": (settings.token_ttl_minutes or DEFAULT_TOKEN_TTL_MINUTES)
            * 60,
        },
    }


@router.post("/logout", dependencies=[Depends(csrf_protect)])
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(async_get_db),
) -> dict[str, object]:
    """清除凭据与 CSRF Cookie。fail-closed：先清 Cookie，再尽力记录审计。"""

    actor_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    token = _extract_token(request)
    if token:
        try:
            payload = peek_access_token(token)
            actor_id = uuid.UUID(payload["sub"]) if payload.get("sub") else None
            tenant_id = (
                uuid.UUID(payload["tenant_id"])
                if payload.get("tenant_id")
                else None
            )
        except Exception:  # noqa: BLE001 - 登出不应因解析失败而失败
            actor_id, tenant_id = None, None

    clear_auth_cookie(response, settings=get_settings())
    clear_csrf_cookie(response, settings=get_settings())

    if actor_id is not None:
        await record_security_event(
            db,
            action="logout",
            tenant_id=tenant_id,
            actor_id=actor_id,
            target_id=str(actor_id),
        )

    return {"success": True, "data": {"logged_out": True}}


@router.post("/refresh", dependencies=[Depends(csrf_protect)])
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(async_get_db),
) -> dict[str, object]:
    """在宽限期内用旧 token 换取新 token，并重种 Cookie。

    安全规则：
    - 签名非法的 token 没有刷新资格（返回 401）；
    - 已过期但仍在 ``REFRESH_GRACE_MINUTES`` 宽限内的 token 允许刷新；
    - 超过宽限期一律拒绝。
    """

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="缺少可刷新的凭据。")

    settings = get_settings()
    try:
        payload = peek_access_token(token)
    except AuthError as exc:  # 签名非法
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if payload.get("expired"):
        exp = payload.get("exp") or 0
        grace = settings.refresh_grace_minutes or 0
        import time

        if int(time.time()) - int(exp) > grace * 60:
            raise HTTPException(
                status_code=401, detail="令牌已过期且超出刷新宽限期。"
            )

    # 复用原载荷的关键字段签发新 token（权限/组织仍以数据库为准，这里只续期）。
    try:
        new_token = create_access_token(
            sub=payload.get("sub", ""),
            tenant_id=payload.get("tenant_id", ""),
            email=str(payload.get("email", "")),
            role=str(payload.get("role", "")),
            roles=list(payload.get("roles", []) or []),
            permissions=list(payload.get("permissions", []) or []),
            expires_minutes=settings.token_ttl_minutes or DEFAULT_TOKEN_TTL_MINUTES,
        )
    except AuthConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    set_auth_cookie(response, new_token, settings=settings)
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token, settings=settings)

    actor_id = (
        uuid.UUID(payload["sub"]) if payload.get("sub") else None
    )
    tenant_id = (
        uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else None
    )
    await record_security_event(
        db,
        action="token_refresh",
        tenant_id=tenant_id,
        actor_id=actor_id,
        target_id=str(actor_id or ""),
    )

    return {
        "success": True,
        "data": {
            "access_token": new_token,
            "token_type": "bearer",
            "csrf_token": csrf_token,
            "expires_in": (settings.token_ttl_minutes or DEFAULT_TOKEN_TTL_MINUTES)
            * 60,
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
