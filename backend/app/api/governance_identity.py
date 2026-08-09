"""治理身份端点（Phase 3.8.28 T3）—— 前端身份链路的服务端一侧。

只有两个端点，且都不产生治理事实：

- ``GET /governance/me``       当前主体（前端据此渲染，不据此授权）
- ``GET /governance/catalog``  治理角色/权限目录（只读，供管理界面展示）

## 为什么前端需要 /governance/me

Phase 3.8.27 的前端 ``IdentityProvider`` 用一张**硬编码**的角色→权限表算出
"这个人能点哪些按钮"。那张表回答不了两个问题：这个人是谁（StaticDev 直接
写死），以及他现在还是不是这个角色（前端无从得知授权变更）。

现在两个问题都由后端回答：前端拿到 token 后调用本端点，得到后端从数据库
重新算出的身份与权限，用于渲染。**渲染不是授权** —— 每个治理请求后端都会
独立再判一次，前端算错了只会让按钮显示得不对，不会让动作真的发生。

## /governance/me 为什么不需要治理权限

它只要求"认证通过"，不要求任何治理权限。一个登录了但没有任何治理角色的
用户，应当能看到"你没有治理权限"这句话，而不是一个 403 白屏 —— 后者会让
人怀疑是系统坏了，反而增加运维噪音。返回体里 ``permissions`` 为空数组，
前端据此把整个治理区置灰，语义清晰。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.identity import (
    GOVERNANCE_ROLE_PERMISSIONS,
    GOVERNANCE_ROLES,
    ALL_GOVERNANCE_PERMISSIONS,
    GovernancePrincipal,
    get_current_principal,
)
from app.identity.seed import (
    GOVERNANCE_PERMISSION_DESCRIPTIONS,
    GOVERNANCE_ROLE_DESCRIPTIONS,
)

router = APIRouter(prefix="/governance", tags=["governance-identity"])


@router.get("/me")
def whoami(
    principal: GovernancePrincipal = Depends(get_current_principal),
) -> dict:
    """返回当前治理主体。认证即可访问，无需治理权限。"""

    data = principal.to_public_dict()
    data["has_governance_access"] = bool(principal.permissions)
    return data


@router.get("/catalog")
def governance_catalog(
    principal: GovernancePrincipal = Depends(get_current_principal),
) -> dict:
    """治理角色与权限目录（只读）。

    要求认证是为了不把内部权限词表暴露给未认证访问者 —— 它本身不是秘密，
    但它是一份"系统有哪些闸门"的清单，没必要匿名可取。
    """

    del principal  # 仅用于门控
    return {
        "permissions": [
            {
                "name": perm.value,
                "description": GOVERNANCE_PERMISSION_DESCRIPTIONS.get(perm, ""),
            }
            for perm in ALL_GOVERNANCE_PERMISSIONS
        ],
        "roles": [
            {
                "name": role,
                "description": GOVERNANCE_ROLE_DESCRIPTIONS.get(role, ""),
                "permissions": sorted(
                    p.value for p in GOVERNANCE_ROLE_PERMISSIONS[role]
                ),
            }
            for role in GOVERNANCE_ROLES
        ],
    }


__all__ = ["router"]
