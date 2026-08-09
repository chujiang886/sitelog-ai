"""企业身份认证与授权异常族（Phase 3.8.28 T1）。

设计原则 —— **只抛不兜**：
本模块的每一个异常都代表"身份链路上出现了无法安全继续的情况"。所有异常
一律由调用方转成 HTTP 4xx 并终止请求，**任何一处都不允许降级为匿名主体、
默认责任人或只读访问**。治理动作的责任归属不存在"大概是谁"这种状态。

HTTP 语义约定（由 ``dependencies.py`` 统一翻译）：
- 401：没证明你是谁（缺 token / 签名坏 / 过期 / 用户失效）
- 403：证明了你是谁，但你不能做这件事（非真人 / 缺权限 / 跨组织）
- 400：请求本身就构造错了（携带已废止的身份请求头）
- 500：服务端身份基础设施没配好（缺 JWT_SECRET 等）——绝不因此放行
"""

from __future__ import annotations


class IdentityError(Exception):
    """身份链路异常基类。"""


class IdentityConfigError(IdentityError):
    """身份基础设施未正确配置（如 JWT_SECRET 缺失、OIDC 未配 JWKS）。

    这类错误**不得**被当成"认证失败"静默处理成 401 后放行只读页面：
    配置缺失时系统无法判断任何人的身份，唯一安全的行为是整体拒绝。
    """


class IdentityUnauthenticatedError(IdentityError):
    """未提供可用凭据（缺 Authorization 头、scheme 不对、token 为空）。"""


class IdentityTokenInvalidError(IdentityError):
    """凭据存在但不可信（签名错、结构坏、类型不对、声明缺失）。"""


class IdentityTokenExpiredError(IdentityTokenInvalidError):
    """凭据已过期。

    单独成类是因为过期在运维语义上与"伪造"完全不同（前者要求重新登录，
    后者是攻击信号），但在放行语义上两者一致：都拒绝。
    """


class IdentitySubjectInactiveError(IdentityError):
    """凭据本身有效，但其对应主体在权威数据源中已失效（停用/软删/不存在）。

    这是"令牌尚未过期但人已离职"的场景。治理系统必须以数据库为准，
    不能因为 token 还在有效期内就继续承认其责任能力。
    """


class IdentityNotHumanError(IdentityError):
    """主体不是真实自然人（红线⑥）。

    治理动作的责任必须落到人身上。AI / 服务账号 / 机器人无论持有何种
    合法凭据，都不得成为治理主体。
    """


class IdentityPermissionDeniedError(IdentityError):
    """主体是合法真人，但缺少本次治理动作所需权限（默认拒绝）。"""


class IdentityCrossOrgError(IdentityError):
    """主体试图访问其归属组织之外的治理事实。"""


class IdentityRedLineViolationError(IdentityError):
    """检测到红线违例（如出现 auto_approve 类权限名）。

    与"权限不足"不同：这不是"这个人不能做"，而是"这件事任何人都不该
    通过授权获得"。出现即视为凭据整体不可信，全量拒绝。
    """


class IdentityHeaderForgeryError(IdentityError):
    """请求携带了已废止的身份请求头（``x-actor-id`` / ``x-actor-kind``）。

    Phase 3.8.28 之前这两个头**就是**身份来源，任何人都能随手伪造。
    本阶段改为服务端派生后，继续容忍这两个头会造成两种危险：

    1. 运维/前端误以为它们仍然生效，据此搭出"切换责任人"的工具，
       实际切换的是一个被忽略的值 —— 典型的混淆代理（confused deputy）；
    2. 攻击者用旧手法探测时收到 200，误判为仍可绕过，安全信号被淹没。

    因此选择**显式报错**而不是静默忽略：让废止这件事发出声音。
    """


__all__ = [
    "IdentityError",
    "IdentityConfigError",
    "IdentityUnauthenticatedError",
    "IdentityTokenInvalidError",
    "IdentityTokenExpiredError",
    "IdentitySubjectInactiveError",
    "IdentityNotHumanError",
    "IdentityPermissionDeniedError",
    "IdentityCrossOrgError",
    "IdentityRedLineViolationError",
    "IdentityHeaderForgeryError",
]
