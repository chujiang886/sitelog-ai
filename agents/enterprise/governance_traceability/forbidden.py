"""Phase 3.8.30 治理全链路追踪与统一审计智能层 —— 结构级禁名（红线③/④/⑤/⑥）。

本层是**纯只读的事实串联与重建层**：把散落在各治理层的事实（事件 / 工作流 / 任务 /
审计 / 知识）用 ``GovernanceTrace`` 串成链路，并以时间线 / 重放 / 来源链三种只读视图
呈现给真实审计责任人。它**绝不**具备下列任何能力：

- 修改或删除治理记录（红线③）；
- 生成治理结论（红线④）；
- 关闭治理事件（红线⑤）；
- 代替审计责任人签署/确认（红线⑥）。

本模块把 3.8.26 驾驶舱层已验证的禁名集（``_DASHBOARD_FORBIDDEN``）叠加本层专属增量，
形成追踪层禁名集。所有禁名以**精确方法名**形式被 ``_RedLineForbiddenMixin.__getattr__``
拦截：一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。

注意：禁名是**结构级**拦截（第一道）。本层另有类型级（模型不存在任何可写结论/关闭
字段）与语义级（文本标记扫描）两道，共同构成三重 fail-closed。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import (
    _DASHBOARD_FORBIDDEN,
    _dedupe,
)

# 追踪层专属禁名增量：聚焦「改审计 / 出结论 / 关事件 / 重放即执行 / 代替审计责任人」。
_TRACEABILITY_EXTRA_FORBIDDEN = (
    # —— 红线③：禁止 AI 自动修改治理记录 ——
    "auto_modify_audit",
    "modify_audit",
    "edit_audit",
    "update_audit",
    "rewrite_audit",
    "alter_audit",
    "patch_audit",
    "auto_delete_record",
    "delete_record",
    "delete_audit",
    "remove_audit",
    "purge_audit",
    "truncate_audit",
    "tamper_audit",
    "backdate_audit",
    "modify_trace",
    "edit_trace",
    "delete_trace",
    "rewrite_trace",
    "modify_timeline",
    "rewrite_timeline",
    "delete_timeline",
    # —— 红线④：禁止 AI 自动生成治理结论 ——
    "auto_generate_conclusion",
    "generate_conclusion",
    "auto_conclude",
    "conclude",
    "conclude_trace",
    "draw_conclusion",
    "infer_conclusion",
    "auto_verdict",
    "verdict",
    "auto_judge",
    "judge_trace",
    "auto_assess",
    "auto_determine_cause",
    "determine_root_cause",
    "auto_root_cause",
    "auto_summarize_conclusion",
    # —— 红线⑤：禁止 AI 自动关闭事件 ——
    "auto_close_incident",
    "close_incident",
    "auto_resolve_incident",
    "resolve_incident",
    "dismiss_incident",
    "auto_dismiss",
    "close_trace",
    "auto_close_trace",
    "auto_terminate",
    "auto_settle",
    # —— 红线④/⑤：禁止「重放」退化为「重新执行」——
    "replay_execute",
    "execute_replay",
    "apply_replay",
    "re_execute",
    "reexecute",
    "rerun",
    "replay_and_execute",
    "replay_apply",
    "rollback",
    "restore_state",
    "undo_action",
    "redo_action",
    # —— 红线⑥：禁止代替审计责任人 ——
    "auto_sign_audit",
    "sign_off_audit",
    "approve_audit",
    "act_as_auditor",
    "audit_on_behalf",
    "auto_attest",
    "attest_on_behalf",
    "auto_certify",
    "certify_trace",
)

# 追踪层禁名集 = 3.8.26 驾驶舱禁名（含 3.8.25 编排层 ∪ 3.8.21 问责层 98 项）∪ 本层增量。
_TRACEABILITY_FORBIDDEN = _dedupe(_DASHBOARD_FORBIDDEN, _TRACEABILITY_EXTRA_FORBIDDEN)

# 供测试 / 文档引用。
TRACEABILITY_FORBIDDEN_COUNT = len(_TRACEABILITY_FORBIDDEN)

__all__ = [
    "_TRACEABILITY_FORBIDDEN",
    "_TRACEABILITY_EXTRA_FORBIDDEN",
    "TRACEABILITY_FORBIDDEN_COUNT",
]
