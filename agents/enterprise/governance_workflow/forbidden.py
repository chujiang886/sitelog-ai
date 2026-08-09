"""Phase 3.8.25 治理工作流编排层 forbidden 方法名（结构级红线）。

设计原则：**复用而非重建**。Phase 3.8.21 已建成治理问责层
``agents.enterprise.agent_governance_workflow``，其 ``_GOVERNANCE_FORBIDDEN``
已覆盖 98 项「自动整改 / 自动分配 / 自动改权限 / 代替责任人」禁名。本层在其之上
**增量补充**编排语义专属禁名（自动审批 / 自动执行 / 自动关闭问题 / 自动生成策略 /
自动修改知识），合并去重后作为编排服务的 ``_FORBIDDEN``。

红线映射（fail-closed）：
① ``engineering_enabled`` 必须为 False —— 由 ``safety_invariants_ok()`` 在
   构造/写路径断言，不在本文件。
② 禁输出 ``engineering_approved`` —— 继承自 3.8.21（已含 ``approve`` /
   ``engineering_approved`` / ``sign`` / ``authorize`` / ``record_human_approval``）。
③ 禁 AI 自动治理 / 自动审批 / 自动关闭问题 —— 本文件
   ``_AUTO_APPROVAL_FORBIDDEN`` + ``_AUTO_CLOSURE_FORBIDDEN``。
④ 禁 AI 自动执行治理动作 / 自动应用知识 —— 本文件 ``_AUTO_EXECUTION_FORBIDDEN``。
⑤ 禁 AI 自动生成治理策略 —— 本文件 ``_POLICY_FORBIDDEN``。
⑥ 禁 AI 代替治理责任人 —— 继承自 3.8.21 + 本文件 ``_ACCOUNTABILITY_FORBIDDEN``。
"""

from __future__ import annotations

from agents.enterprise.agent_governance_workflow import _GOVERNANCE_FORBIDDEN


# 红线③：禁止 AI 自动审批 / 自动研判 / 绕过人工确认。
_AUTO_APPROVAL_FORBIDDEN = (
    "auto_approve",
    "auto_approve_workflow",
    "approve_workflow",
    "auto_review",
    "review_automatically",
    "auto_confirm",
    "confirm_automatically",
    "auto_human_confirm",
    "auto_judge",
    "judge_automatically",
    "auto_adjudicate",
    "adjudicate_workflow",
    "bypass_human_review",
    "skip_human_review",
    "skip_human_confirmation",
    "waive_human_review",
    "auto_signoff_workflow",
)

# 红线④：禁止 AI 自动执行治理动作 / 自动应用治理知识。
_AUTO_EXECUTION_FORBIDDEN = (
    "auto_execute",
    "auto_execute_workflow",
    "execute_workflow_automatically",
    "auto_run_workflow",
    "run_workflow_automatically",
    "auto_perform_action",
    "perform_governance_action_automatically",
    "auto_trigger_execution",
    "trigger_execution_automatically",
    "auto_apply_knowledge",
    "auto_execute_knowledge",
    "auto_update_knowledge",
    "auto_merge_knowledge",
    "apply_knowledge_automatically",
    "auto_remediate_workflow",
)

# 红线③衍生：禁止 AI 自动关闭 / 自动归档治理工作流。
_AUTO_CLOSURE_FORBIDDEN = (
    "auto_close_workflow",
    "close_workflow",
    "auto_complete_workflow",
    "complete_workflow",
    "auto_finish_workflow",
    "finish_workflow",
    "auto_archive",
    "auto_archive_workflow",
    "archive_automatically",
    "auto_finalize",
    "finalize_workflow",
    "auto_terminate_workflow",
    "terminate_workflow",
    "auto_close_issue",
    "close_issue_automatically",
)

# 红线⑤：禁止 AI 自动生成 / 推荐治理策略。
_POLICY_FORBIDDEN = (
    "generate_policy",
    "auto_generate_policy",
    "recommend_policy",
    "auto_recommend_policy",
    "propose_policy",
    "auto_propose_policy",
    "draft_policy",
    "auto_draft_policy",
    "synthesize_policy",
    "policy_recommendation",
)

# 红线⑥：禁止 AI 代替治理责任人（编排语义专属补充）。
_ACCOUNTABILITY_FORBIDDEN = (
    "act_as_reviewer",
    "take_review_responsibility",
    "assume_review_responsibility",
    "auto_assign_reviewer",
    "assign_reviewer_automatically",
    "auto_decide_workflow",
    "decide_workflow",
    "auto_conclude",
    "conclude_workflow_automatically",
    "auto_accept_workflow_result",
    "accept_workflow_result_automatically",
)


def _dedupe(*groups: "tuple[str, ...]") -> "tuple[str, ...]":
    """合并多组禁名并保序去重（避免与 3.8.21 既有禁名重复登记）。"""
    seen: dict[str, None] = {}
    for group in groups:
        for name in group:
            seen.setdefault(name, None)
    return tuple(seen)


# 编排层专属新增禁名（不含 3.8.21 已覆盖部分），供测试单独核验增量。
_ORCHESTRATION_FORBIDDEN = _dedupe(
    _AUTO_APPROVAL_FORBIDDEN,
    _AUTO_EXECUTION_FORBIDDEN,
    _AUTO_CLOSURE_FORBIDDEN,
    _POLICY_FORBIDDEN,
    _ACCOUNTABILITY_FORBIDDEN,
)

# 本层最终 forbidden 集合 = 3.8.21 问责层禁名 ∪ 编排层新增禁名。
_WORKFLOW_FORBIDDEN = _dedupe(_GOVERNANCE_FORBIDDEN, _ORCHESTRATION_FORBIDDEN)


__all__ = [
    "_WORKFLOW_FORBIDDEN",
    "_ORCHESTRATION_FORBIDDEN",
    "_AUTO_APPROVAL_FORBIDDEN",
    "_AUTO_EXECUTION_FORBIDDEN",
    "_AUTO_CLOSURE_FORBIDDEN",
    "_POLICY_FORBIDDEN",
    "_ACCOUNTABILITY_FORBIDDEN",
]
