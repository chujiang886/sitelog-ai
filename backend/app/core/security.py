"""RBAC 安全基础设施（Phase 2.2 / 2.2.6）。

职责：
- 密码哈希（pbkdf2_hmac，标准库实现，零新增依赖）；
- JWT（HS256，标准库实现，secret 仅来自环境变量 JWT_SECRET）；
- ``CurrentUser`` 数据类；
- ``get_current_user`` / ``require_permission`` 两个 FastAPI 依赖；
- RBAC 目录（roles/permissions/role_permissions）幂等种子。

设计红线：
- JWT secret 仅来自 ``.env``（config.jwt_secret），为空则 fail-closed；
- 不提交任何 secret；测试用 secret 仅存在于测试 fixture；
- 权限在登录时解析并嵌入 JWT，运行时由 require_permission 校验，无需每次查库。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.rbac import Permission, Role, RolePermission, UserRole
from app.db.models.user import User
from app.db.session import async_get_db


# --------------------------------------------------------------------------- #
# 常量与目录                                                                    #
# --------------------------------------------------------------------------- #


PBKDF2_ROUNDS = 100_000  # infrastructure-config（硬编码扫描白名单标记）
HASH_ALGO = "sha256"
JWT_ALGO = "HS256"
DEFAULT_TOKEN_TTL_MINUTES = 60  # infrastructure-config

RBAC_ROLES: tuple[str, ...] = ("admin", "designer", "viewer")

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "upload:create",
        "upload:read",
        "analysis:create",
        "analysis:read",
        "report:create",
        "report:read",
        "user:manage",
        "tenant:manage",
    },
    "designer": {
        "upload:create",
        "upload:read",
        "analysis:create",
        "analysis:read",
        "report:create",
        "report:read",
    },
    "viewer": {
        "upload:read",
        "analysis:read",
        "report:read",
    },
}

ALL_PERMISSIONS: list[str] = sorted(
    {perm for perms in ROLE_PERMISSIONS.values() for perm in perms}
)


# --------------------------------------------------------------------------- #
# 异常                                                                         #
# --------------------------------------------------------------------------- #


class AuthError(ValueError):
    """认证/授权失败基类（token 非法、过期、secret 缺失等）。"""


class AuthConfigError(AuthError):
    """认证基础设施未正确配置（如 JWT_SECRET 缺失）。"""


# --------------------------------------------------------------------------- #
# 密码哈希                                                                      #
# --------------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    """返回 ``pbkdf2_sha256$rounds$salt$hash`` 格式的存储串。"""

    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(HASH_ALGO, password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_{HASH_ALGO}${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """常量时间比对；格式非法或算法不匹配一律返回 False。"""

    try:
        algo, rounds_s, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != f"pbkdf2_{HASH_ALGO}":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        rounds = int(rounds_s)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(HASH_ALGO, password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(dk.hex(), hash_hex)


# --------------------------------------------------------------------------- #
# JWT（HS256，标准库实现）                                                      #
# --------------------------------------------------------------------------- #


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _get_jwt_secret() -> str:
    """JWT secret 仅来自环境变量；为空则 fail-closed。"""

    secret = get_settings().jwt_secret
    if not secret:
        raise AuthConfigError("JWT_SECRET is not configured")
    return secret


def create_access_token(
    *,
    sub: str | uuid.UUID,
    tenant_id: str | uuid.UUID,
    email: str,
    role: str,
    roles: list[str],
    permissions: list[str],
    expires_minutes: int = DEFAULT_TOKEN_TTL_MINUTES,
) -> str:
    """签发 HS256 access token，权限嵌入 payload。"""

    secret = _get_jwt_secret()
    header = {"alg": JWT_ALGO, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "tenant_id": str(tenant_id),
        "email": email,
        "role": role,
        "roles": list(roles),
        "permissions": list(permissions),
        "iat": now,
        "exp": now + expires_minutes * 60,
        "type": "access",
    }
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    """校验并解析 HS256 token；任何失败抛 ``AuthError``。"""

    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise AuthError("Malformed token")
    signing_input = f"{header_b64}.{payload_b64}"
    secret = _get_jwt_secret()
    expected = hmac.new(
        secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256
    ).digest()
    try:
        got = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        raise AuthError("Token signature invalid")
    if not hmac.compare_digest(expected, got):
        raise AuthError("Token signature invalid")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        raise AuthError("Token payload invalid")
    exp = payload.get("exp")
    if not isinstance(exp, int) or int(time.time()) > exp:
        raise AuthError("Token expired")
    if payload.get("type") != "access":
        raise AuthError("Wrong token type")
    return payload


# --------------------------------------------------------------------------- #
# 当前用户与权限依赖                                                            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """经认证解析出的当前用户主体。"""

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    roles: list[str]
    permissions: set[str]


async def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: AsyncSession = Depends(async_get_db),
) -> CurrentUser:
    """解析 Bearer token，校验用户存在且 active，返回 ``CurrentUser``。"""

    if not authorization:
        raise HTTPException(
            status_code=401, detail="Missing Authorization header"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401, detail="Invalid Authorization header scheme"
        )

    try:
        claims = decode_access_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        user_id = uuid.UUID(claims["sub"])
        tenant_id = uuid.UUID(claims["tenant_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token claims") from None

    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None or user.status != "active":
        raise HTTPException(status_code=401, detail="User inactive or not found")

    return CurrentUser(
        id=user.id,
        tenant_id=tenant_id,
        email=str(claims.get("email", "")),
        roles=list(claims.get("roles", [])),
        permissions=set(claims.get("permissions", [])),
    )


def require_permission(permission: str):
    """依赖工厂：校验当前用户拥有 ``permission``，否则 403。

    用法：``current_user: CurrentUser = Depends(require_permission("upload:create"))``
    """

    async def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if permission not in current_user.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: requires '{permission}'",
            )
        return current_user

    return _dependency


# --------------------------------------------------------------------------- #
# 权限解析（登录时调用）                                                         #
# --------------------------------------------------------------------------- #


async def resolve_principals(db: AsyncSession, user: User) -> tuple[list[str], set[str]]:
    """解析用户在某租户下的角色与权限集合。"""

    role_id_rows = await db.scalars(
        select(UserRole.role_id).where(
            UserRole.user_id == user.id, UserRole.tenant_id == user.tenant_id
        )
    )
    role_ids = list(role_id_rows.all())
    if not role_ids:
        return [], set()

    name_rows = await db.scalars(select(Role.name).where(Role.id.in_(role_ids)))
    roles = list(name_rows.all())

    perm_rows = await db.scalars(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    )
    permissions = set(perm_rows.all())
    return roles, permissions


# --------------------------------------------------------------------------- #
# RBAC 目录种子（供 seed.py 同步调用；测试见 conftest 异步版本）                 #
# --------------------------------------------------------------------------- #


def seed_rbac_catalog(db) -> None:
    """幂等写入 roles / permissions / role_permissions（不提交，由调用方提交）。"""

    role_objs: dict[str, Role] = {}
    for name in RBAC_ROLES:
        existing = db.query(Role).filter_by(name=name).one_or_none()
        if existing is None:
            existing = Role(name=name)
            db.add(existing)
            db.flush()
        role_objs[name] = existing

    perm_objs: dict[str, Permission] = {}
    for name in ALL_PERMISSIONS:
        existing = db.query(Permission).filter_by(name=name).one_or_none()
        if existing is None:
            existing = Permission(name=name)
            db.add(existing)
            db.flush()
        perm_objs[name] = existing

    for role_name, perms in ROLE_PERMISSIONS.items():
        role = role_objs[role_name]
        for perm_name in perms:
            perm = perm_objs[perm_name]
            link = db.query(RolePermission).filter_by(
                role_id=role.id, permission_id=perm.id
            ).one_or_none()
            if link is None:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))


def assign_user_role(db, user: User, role_name: str, tenant_id: uuid.UUID) -> None:
    """幂等把用户关联到指定角色的 user_roles 行（不提交）。"""

    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        return
    existing = db.query(UserRole).filter_by(
        user_id=user.id, role_id=role.id, tenant_id=tenant_id
    ).one_or_none()
    if existing is None:
        db.add(
            UserRole(
                user_id=user.id, role_id=role.id, tenant_id=tenant_id
            )
        )


__all__ = [
    "ALL_PERMISSIONS",
    "AuthConfigError",
    "AuthError",
    "CurrentUser",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "hash_password",
    "RBAC_ROLES",
    "require_permission",
    "resolve_principals",
    "ROLE_PERMISSIONS",
    "seed_rbac_catalog",
    "assign_user_role",
    "verify_password",
]
