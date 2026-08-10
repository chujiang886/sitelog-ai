"""CSRF 双提交防护（Phase 3.8.29 T1）。

## 机制

状态变更请求（POST/PUT/PATCH/DELETE）必须携带头 ``X-CSRF-Token``，其值与
``boip_csrf_token`` Cookie 完全一致。二者都由同一后端签发、同源，外部站点
无法读取 Cookie（非 HttpOnly 的 CSRF cookie 也被同源策略限制），因此跨站
请求要么拿不到 token，要么 Cookie 因 SameSite 不被携带 —— 双保险。

## 与 SameSite 的关系

``SameSite=Lax/Strict`` 已挡掉绝大多数跨站自动携带；CSRF 双提交是**纵深防御**，
覆盖「同源但非预期来源」「SameSite=None 的跨站部署」等残留面。二者并存，
不互相替代。

## 安全方法豁免

GET/HEAD/OPTIONS 不改变状态，且凭据 Cookie 即便被携带也无副作用，故跳过校验。
这避免了给只读接口强加 CSRF 头、也避免「GET 也要 token」这类反模式。

## 配置门控（fail-closed 友好）

``effective_csrf_enabled`` 在生产环境恒为 True；非生产可由
``CSRF_PROTECTION_ENABLED`` 显式关闭以便本地联调与既有测试。关闭时本依赖
为 no-op，绝不静默放行逻辑漏洞——它只是把校验决策交还给部署方。
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.auth_cookies import read_csrf_cookie
from app.core.config import get_settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def csrf_protect(request: Request) -> None:
    """FastAPI 依赖：对状态变更请求强制 CSRF 双提交校验。

    校验通过返回 ``None``；违反则抛 ``403``。由 ``effective_csrf_enabled`` 门控。
    """

    settings = get_settings()
    if not settings.effective_csrf_enabled:
        return
    if request.method in _SAFE_METHODS:
        return

    expected = read_csrf_cookie(request, settings=settings)
    provided = request.headers.get(settings.csrf_header_name)
    if not expected or not provided:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 校验失败：缺少令牌（Cookie 或请求头）。",
        )
    # 常量时间比较，避免时序侧信道。
    if not _constant_time_equal(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 校验失败：令牌不匹配。",
        )


def _constant_time_equal(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = ["csrf_protect"]
