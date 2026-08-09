"""Phase 3.8.26 治理驾驶舱层 —— 结构级禁名（红线③/④/⑤/⑥ 收口点之一）。

治理驾驶舱是**只读查询 + 单一人工确认入口**，绝不持有任何「自动治理 / 自动审批 /
自动执行 / 自动关闭 / 自动生成策略 / 代替责任人」能力。本模块把 3.8.25 编排层已验证的
禁名集（``_WORKFLOW_FORBIDDEN``，166 项）叠加本层专属增量，形成驾驶舱禁名集。

所有禁名以「方法名子串」形式匹配：``_RedLineForbiddenMixin`` 在调用命中禁名的方法时
直接抛 ``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。
"""

from __future__ import annotations

from agents.enterprise.governance_workflow.forbidden import _WORKFLOW_FORBIDDEN

# 驾驶舱层专属禁名增量：聚焦「代替人工点击 / 批量自动确认 / 触碰知识或策略」。
_DASHBOARD_EXTRA_FORBIDDEN = (
    # —— 代替人工点击 / 自动确认（红线③/⑥）——
    "auto_confirm",
    "auto_confirm_review",
    "auto_approve_review",
    "batch_confirm",
    "confirm_on_behalf",
    "click_for_user",
    "auto_resolve",
    "auto_review",
    # —— 自动执行 / 关闭治理动作（红线④）——
    "auto_execute",
    "auto_close",
    "auto_archive",
    "auto_complete",
    # —— 生成策略 / 改知识（红线⑤）——
    "generate_policy",
    "modify_knowledge",
    "update_knowledge",
    "rewrite_knowledge",
    "auto_draft_decision",
)


def _dedupe(*sequences):
    seen = set()
    out = []
    for seq in sequences:
        for item in seq:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return tuple(out)


# 驾驶舱禁名集 = 3.8.25 编排层禁名（含 3.8.21 问责层 98 项）∪ 本层增量。
_DASHBOARD_FORBIDDEN = _dedupe(_WORKFLOW_FORBIDDEN, _DASHBOARD_EXTRA_FORBIDDEN)

# 供测试 / 文档引用。
DASHBOARD_FORBIDDEN_COUNT = len(_DASHBOARD_FORBIDDEN)

__all__ = [
    "_DASHBOARD_FORBIDDEN",
    "_DASHBOARD_EXTRA_FORBIDDEN",
    "DASHBOARD_FORBIDDEN_COUNT",
]
