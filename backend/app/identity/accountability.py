"""治理动作身份绑定（Phase 3.8.28 T4）。

## 要解决的问题

到 Phase 3.8.27 为止，治理审计里能看到"某个 actor_id 在某时做了某事"。缺的
那一项是**以什么身份做的**。这不是锦上添花：治理复盘时真正要回答的问题是
"这个人当时有没有资格下这个结论"，而 actor_id 只能回答"是谁"。一个人今天
是 governance-reviewer、下周被降为 governance-viewer，事后翻审计只看到 id，
就必须去人事系统里反查他在那个时间点的角色 —— 而角色变更未必留痕到那个
精度。所以责任必须在**动作发生的那一刻**连同角色一起固化。

## 责任五元组

``user_id / role / timestamp / action / resource``，另附 ``org_id`` /
``actor_kind`` / ``authenticated_via`` 三项还原上下文。全部来自
``GovernancePrincipal`` —— 也就是全部来自后端从凭据 + 数据库派生的结论，
**没有一项能由请求方指定**。

## 为什么单独落一条记录而不是塞进业务审计的 detail

两种做法都实现过一遍，最后选了"单独一条"，理由是可查性：

- 塞进 detail：每类治理动作的 detail 格式由各自的业务代码决定，问责信息
  会以七八种形态散落在不同分类里，事后想"列出张三本季度所有以 reviewer
  身份做出的治理动作"就得写七八个解析分支；
- 单独一条：所有问责记录格式一致、动作名固定为
  ``governance_accountability``，一次过滤就能拿全，且**新增一类治理动作
  不会遗漏问责**（忘了调用是显式缺失，不是格式不兼容）。

代价是审计记录条数翻倍。治理审计的量级是"人工动作"，不是"系统事件"，这个
代价可以接受。

## 与红线的关系

本模块只**记录**责任，不产生任何治理效力：它不改状态、不做判断、不授予
权限。``action`` 取值来自调用方对自己动作的描述，禁语扫描仍然生效 ——
一条声称自己是 ``auto_approve`` 的问责记录不该被安静地写下去。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.identity.errors import IdentityRedLineViolationError
from app.identity.permissions import FORBIDDEN_PERMISSION_PATTERNS
from app.identity.principal import GovernancePrincipal

#: 问责记录的固定动作名。审计里按它一次性捞全所有问责留痕。
GOVERNANCE_ACCOUNTABILITY_ACTION = "governance_accountability"

#: 责任五元组字段（顺序即序列化顺序，测试按此钉死）。
ACCOUNTABILITY_FIELDS: tuple[str, ...] = (
    "user_id",
    "role",
    "timestamp",
    "action",
    "resource",
)

#: 附加上下文字段（不属于五元组，但缺了就无法还原"这次责任是怎么成立的"）。
ACCOUNTABILITY_CONTEXT_FIELDS: tuple[str, ...] = (
    "org_id",
    "actor_kind",
    "authenticated_via",
)

_DETAIL_KEY = "detail"


def _assert_action_clean(action: str, resource: str) -> None:
    """动作/对象名命中禁语即拒绝写入（红线②/③/④/⑤）。

    这里拒绝的是**记录行为本身**。有人试图留下一条 ``auto_approve`` 的问责
    痕迹，说明上游存在一个不该存在的动作；把它写进审计等于给这个动作发了
    一张"确实发生过且被系统承认"的凭证。宁可让调用链在此处炸掉。
    """

    for raw in (action, resource):
        low = str(raw or "").strip().lower()
        if not low:
            continue
        for pattern in FORBIDDEN_PERMISSION_PATTERNS:
            if pattern in low:
                raise IdentityRedLineViolationError(
                    f"治理动作名 {raw!r} 命中禁语 {pattern!r}："
                    "治理系统不存在自动审批/自动执行动作，拒绝为其留下问责记录。"
                )


def accountability_context(
    principal: GovernancePrincipal, *, action: str, resource: str
) -> dict[str, Any]:
    """构造责任五元组 + 上下文（全部来自后端裁定的主体）。"""

    _assert_action_clean(action, resource)
    return principal.to_audit_context(action=action, resource=resource)


def format_accountability(
    context: Mapping[str, Any], *, detail: str = ""
) -> str:
    """把责任上下文序列化成一行可解析文本。

    形如::

        user_id=<id>;role=<r1,r2>;timestamp=<iso>;action=<a>;resource=<r>;
        org_id=<o>;actor_kind=user;authenticated_via=jwt;detail=<自由文本>

    ``detail`` **恒为最后一项**，因此其内容里出现 ``;`` 或 ``=`` 不会破坏
    解析（见 ``parse_accountability``）。这一点很重要：detail 里经常是人写的
    研判理由，不能对它的字符做限制，也不能因为它含分号就把责任信息解析歪。
    """

    parts = [
        f"{key}={context.get(key, '')}"
        for key in ACCOUNTABILITY_FIELDS + ACCOUNTABILITY_CONTEXT_FIELDS
    ]
    text = ";".join(parts)
    if detail:
        text = f"{text};{_DETAIL_KEY}={detail}"
    return text


def parse_accountability(text: str) -> dict[str, str]:
    """解析 ``format_accountability`` 的输出（审计工具与测试使用）。"""

    known = ACCOUNTABILITY_FIELDS + ACCOUNTABILITY_CONTEXT_FIELDS
    out: dict[str, str] = {}
    rest = str(text or "")
    for key in known:
        prefix = f"{key}="
        if not rest.startswith(prefix):
            # 容忍缺项：解析器不该因为一条历史格式的记录而整体失败。
            continue
        rest = rest[len(prefix) :]
        value, sep, remainder = rest.partition(";")
        out[key] = value
        rest = remainder if sep else ""
    if rest.startswith(f"{_DETAIL_KEY}="):
        out[_DETAIL_KEY] = rest[len(_DETAIL_KEY) + 1 :]
    return out


#: 审计方法映射。刻意穷举而不做前缀拼接兜底 —— 出现第五类说明治理模型变了，
#: 应当有人显式来改这张表，而不是让一个拼错的 kind 悄悄写进一个新分类里。
#:
#: ``view`` 与前三者性质不同：读不产生治理后果，只产生知情范围。它之所以也在
#: 表里，是因为**有些读路径没有现成的 VIEW 审计可供嵌入**（典型是驾驶舱，
#: 它写的是 ``record_dashboard_query``，不带角色）。这类路径只能单独落一条。
#: 已有 VIEW 审计的路径（``/governance/ops/*``）仍应把五元组嵌进 detail，
#: 不要为了"统一"而平白翻倍记录数。
_AUDIT_METHOD_BY_KIND: Mapping[str, str] = {
    "create": "record_agent_governance_workflow_create",
    "review": "record_agent_governance_workflow_review",
    "execution": "record_agent_governance_workflow_execution",
    "view": "record_agent_governance_workflow_view",
}


def record_accountability(
    audit: Any,
    principal: GovernancePrincipal,
    *,
    action: str,
    resource: str,
    kind: str = "execution",
    detail: str = "",
    record_id: str = "",
    ts: str = "",
) -> Optional[dict[str, Any]]:
    """写入一条问责记录，返回被写入的责任上下文。

    ``audit`` 为 ``None`` 时返回 ``None`` 且不报错：审计服务缺席是装配问题，
    应当由装配处解决；在治理动作的执行路径上因为"没接审计"而抛异常，等于
    让一个可观测性缺口升级成功能故障。但责任上下文仍然构造并返回，调用方
    可以据此自行落库或告警。
    """

    context = accountability_context(principal, action=action, resource=resource)
    if audit is None:
        return context

    method_name = _AUDIT_METHOD_BY_KIND.get(str(kind).strip())
    if method_name is None:
        raise ValueError(
            f"未知问责动作类别 {kind!r}；可选：{sorted(_AUDIT_METHOD_BY_KIND)}"
        )
    writer = getattr(audit, method_name)
    writer(
        record_id=record_id or f"acct-{principal.actor_id}-{resource}",
        actor_id=principal.actor_id,
        action=GOVERNANCE_ACCOUNTABILITY_ACTION,
        target=resource,
        detail=format_accountability(context, detail=detail),
        ts=ts or str(context.get("timestamp", "")),
    )
    return context


__all__ = [
    "ACCOUNTABILITY_CONTEXT_FIELDS",
    "ACCOUNTABILITY_FIELDS",
    "GOVERNANCE_ACCOUNTABILITY_ACTION",
    "accountability_context",
    "format_accountability",
    "parse_accountability",
    "record_accountability",
]
