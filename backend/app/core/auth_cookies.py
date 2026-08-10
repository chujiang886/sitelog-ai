"""HttpOnly Cookie 与 CSRF 双提交令牌（Phase 3.8.29 T1）。

## 为什么用 HttpOnly Cookie 取代 sessionStorage

3.8.28 的 token 存在 ``sessionStorage``，JS 任意脚本可读 —— 一旦页面有 XSS，
治理凭据即被盗。改成 HttpOnly Cookie 后：

- 浏览器自动携带，JS **读不到**明文（``document.cookie`` 里看不到它）；
- 但 Cookie 会被**自动附带**到同源请求，所以后端必须额外做 CSRF 防护
  （这是 Bearer 头方案不需要、Cookie 方案必须补的一层）。

## 两条 Cookie 的职责

- ``boip_access_token``（HttpOnly, Secure, SameSite）：身份凭据本身，JS 不可读；
- ``boip_csrf_token``（**非** HttpOnly）：CSRF 双提交令牌，明文给 JS 读，
  由 JS 在状态变更请求里以 ``X-CSRF-Token`` 头回传；后端比对二者一致才放行。

非 HttpOnly 的 CSRF cookie 被读走也无Credential泄露风险——它只是一个一次性
随机串，单独拿着它无法伪装身份（没有 HttpOnly 凭据 cookie 的配合）。

## SameSite 策略

- ``lax``（默认）：阻止跨站 POST 自动携带，兼容同站开发（localhost:3000→:8000
  属同站），是最低安全基线；
- ``strict``：更强，连同站顶级跳转也不带，适合高安全后台；
- ``none``：仅当真的跨站（不同注册域）且**必须**带 Secure 时使用。

策略由环境变量驱动，开发缺省 lax、生产由配置决定，绝不硬编码。
"""

from __future__ import annotations

import os
import secrets
from typing import Mapping

from fastapi import Request
from starlette.responses import Response

from app.core.config import get_settings

#: 凭据 Cookie 缺省名（与 config.auth_cookie_name 同源，供测试断言）。
DEFAULT_AUTH_COOKIE_NAME = "boip_access_token"
DEFAULT_CSRF_COOKIE_NAME = "boip_csrf_token"
DEFAULT_CSRF_HEADER_NAME = "X-CSRF-Token"

__all__ = [
    "DEFAULT_AUTH_COOKIE_NAME",
    "DEFAULT_CSRF_COOKIE_NAME",
    "DEFAULT_CSRF_HEADER_NAME",
    "generate_csrf_token",
    "build_cookie_params",
    "set_auth_cookie",
    "clear_auth_cookie",
    "set_csrf_cookie",
    "clear_csrf_cookie",
    "read_csrf_cookie",
    "read_auth_cookie",
    "resolve_raw_token",
    "resolve_bearer_credential",
]


def generate_csrf_token() -> str:
    """生成密码学随机 CSRF 令牌（32 字节 hex）。"""

    return secrets.token_hex(32)


def _samesite_normalized(value: str) -> str:
    """把 SameSite 配置收敛为 Starlette 接受的小写值。"""

    v = (value or "lax").strip().lower()
    if v not in ("lax", "strict", "none"):
        return "lax"
    return v


def build_cookie_params(
    *,
    name: str,
    value: str,
    http_only: bool,
    settings=None,
) -> dict[str, object]:
    """按当前环境构造 ``Response.set_cookie`` 参数。"""

    settings = settings or get_settings()
    params: dict[str, object] = {
        "key": name,
        "value": value,
        "httponly": http_only,
        "samesite": _samesite_normalized(settings.cookie_samesite),
        "secure": settings.effective_cookie_secure,
        "path": "/",
    }
    # domain 仅在显式配置时设置（空字符串会让 Starlette 不写 Domain 属性）。
    domain = (settings.cookie_domain or "").strip()
    if domain:
        params["domain"] = domain
    return params


def set_auth_cookie(
    response: Response, token: str, *, settings=None
) -> None:
    """在响应上种下 HttpOnly 身份凭据 Cookie。"""

    settings = settings or get_settings()
    response.set_cookie(
        **build_cookie_params(
            name=settings.auth_cookie_name,
            value=token,
            http_only=True,
            settings=settings,
        )
    )


def clear_auth_cookie(response: Response, *, settings=None) -> None:
    """清除身份凭据 Cookie（登出 / 失效）。"""

    settings = settings or get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        domain=(settings.cookie_domain or "").strip() or None,
    )


def set_csrf_cookie(response: Response, token: str, *, settings=None) -> None:
    """种下非 HttpOnly 的 CSRF 双提交令牌 Cookie。"""

    settings = settings or get_settings()
    response.set_cookie(
        **build_cookie_params(
            name=settings.csrf_cookie_name,
            value=token,
            http_only=False,
            settings=settings,
        )
    )


def clear_csrf_cookie(response: Response, *, settings=None) -> None:
    settings = settings or get_settings()
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=(settings.cookie_domain or "").strip() or None,
    )


def read_csrf_cookie(request: Request, *, settings=None) -> str | None:
    settings = settings or get_settings()
    value = request.cookies.get(settings.csrf_cookie_name)
    return value or None


def read_auth_cookie(request: Request, *, settings=None) -> str | None:
    settings = settings or get_settings()
    value = request.cookies.get(settings.auth_cookie_name)
    return value or None


def _bearer_token_from_header(authorization: str | None) -> str | None:
    """从 ``Authorization`` 头取裸 token；非 Bearer 或空则 None。"""

    if not authorization or not str(authorization).strip():
        return None
    scheme, _, token = str(authorization).partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def resolve_raw_token(
    request: Request,
    authorization: str | None = None,
    *,
    settings=None,
) -> str | None:
    """解析本次请求的裸凭据 token —— **Authorization 头优先，Cookie 兜底**。

    优先级不可反转，理由是安全语义而非实现便利：

    - ``Authorization`` 头是**调用方显式声明**的身份，脚本 / 服务端 / 测试都靠它；
    - Cookie 是**浏览器自动附带**的环境凭据，调用方并未在本次请求里表态。

    若让 Cookie 压过显式头，会出现两类真实故障：
    ① 同一浏览器登录过 A，再用 B 的 Bearer 头调接口，实际以 A 的身份执行 ——
       这是**跨主体越权**，在多租户治理场景等同于责任人张冠李戴；
    ② 自动化客户端无法覆盖残留会话，调试与审计都会指向错误的 actor。

    因此：显式优先、隐式兜底。Cookie 仅在调用方**完全没给** Authorization
    头时才生效。

    ### 「显式头存在即独占」规则

    若 ``Authorization`` 头存在但不是合法 Bearer（如 ``Basic xxx``、
    ``Bearer `` 空值），**不回落 Cookie**，直接判无凭据。原因同上：调用方
    已经显式表态用某种方式认证，我们不支持就该拒绝；此时若悄悄改用浏览器
    残留 Cookie 的身份执行，调用方以为自己是 X、系统却记成 Y，审计链直接
    失真。宁可 401 让调用方改正，也不做静默的身份替换。
    """

    if authorization is not None and str(authorization).strip():
        # 显式头独占：有效则用它，无效则到此为止，不看 Cookie。
        return _bearer_token_from_header(authorization)
    return read_auth_cookie(request, settings=settings)


def resolve_bearer_credential(
    request: Request,
    authorization: str | None = None,
    *,
    settings=None,
) -> str | None:
    """同 :func:`resolve_raw_token`，但返回规范化的 ``"Bearer <token>"``。

    身份服务 ``IdentityAuthenticationService.authenticate`` 只认 ``Bearer``
    前缀的凭据串。Cookie 里存的是**裸 token**（没有前缀），若直接透传会被
    ``extract_bearer_token`` 判成"不支持的认证方式 ''"而拒绝 —— 即 Cookie
    通道在治理接口上完全不通。这里统一补回前缀，让两条通道等价。

    对**显式但非法**的头（如 ``Basic xxx``）原样透传，好让身份服务给出
    精确的"不支持的认证方式 'Basic'"，而不是笼统的"缺少请求头"。
    """

    if authorization is not None and str(authorization).strip():
        header_token = _bearer_token_from_header(authorization)
        if header_token:
            return f"Bearer {header_token}"
        # 显式头独占且非法：原样交给身份服务产生精确错误，绝不回落 Cookie。
        return str(authorization)

    cookie_token = read_auth_cookie(request, settings=settings)
    if not cookie_token:
        return None
    return f"Bearer {cookie_token}"
