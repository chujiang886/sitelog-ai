"""Phase 3.9.12 —— 供给层审计类别（Task 31）。

**设计决策（治理守约）**：本文件定义 3.9.12 的供给算子审计类别，但**不**修改企业级
``agents/enterprise/audit.py`` 的 ``AuditActionCategory`` 枚举——该枚举与
``.ai/baselines/audit_action_category_ledger.json`` 当前冻结于 **129**（last released
baseline 3.9.8），且有测试/基线契约硬性断言 129。

本仓库实践：已发布账本保持在「最后发布的基线」（3.9.8 → 129）；在途阶段（3.9.9/3.9.10/
3.9.11/3.9.12）在各自分支定义自身审计类别，待阶段边界收敛时再统一折叠进企业枚举与账本
（129 → 141，即本层 12 类）。因此本文件以**自包含常量集**形式记录 3.9.12 类别，
不污染冻结账本，且 human-record 端点以审计形态事件落盘（category 为字符串，不进企业枚举）。

全部 12 类均为**只读事实型**动作：仅如实记录「真实人工查看/登记外部预生产供给就绪」，
绝不承载批准/放行/自动供给/翻转 engineering_enabled/宣布 Production GO 语义（红线①~⑩）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 3.9.12 供给算子审计类别（12 类，只读事实型；fold-in 时并入企业枚举 129 → 141）。
PROVISIONING_AUDIT_CATEGORIES: frozenset[str] = frozenset(
    {
        "external_staging_provisioning_package_validated",
        "external_staging_provisioning_human_input_reviewed",
        "external_staging_provisioning_iac_dry_run",
        "external_staging_provisioning_operator_gate_evaluated",
        "external_staging_provisioning_bom_reviewed",
        "external_staging_provisioning_runbook_viewed",
        "external_staging_provisioning_cost_guard_checked",
        "external_staging_provisioning_capacity_reviewed",
        "external_staging_provisioning_cleanup_runbook_viewed",
        "external_staging_provisioning_authorization_registered",
        "external_staging_provisioning_readiness_reviewed",
        "external_staging_provisioning_evidence_built",
    }
)

# 红线标记（detail 强制携带）。
_RED_LINE_MARKER = "engineering_enabled=false;production_activation_prohibited=true"


@dataclass
class ProvisioningAuditEvent:
    """供给层审计事件（审计形态，category 为字符串，不进企业枚举）。"""

    record_id: str
    actor_kind: str  # "USER" | "AI"（human-record 强制 USER）
    actor_id: str
    category: str
    action: str
    target: str
    detail: str
    ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "actor_kind": self.actor_kind,
            "actor_id": self.actor_id,
            "category": self.category,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "ts": self.ts,
            "is_provisioning_audit": True,
            "red_line_marker": _RED_LINE_MARKER,
            "contains_real_secret": False,
        }


def build_provisioning_audit_event(
    *,
    record_id: str,
    actor_kind: str,
    actor_id: str,
    category: str,
    action: str = "view",
    target: str = "",
    detail: str = "",
    ts: str = "",
) -> ProvisioningAuditEvent:
    """构造一条供给层审计事件（fail-closed：category 必须在本层 12 类内）。"""

    if category not in PROVISIONING_AUDIT_CATEGORIES:
        raise ValueError(
            f"category={category!r} 不在 3.9.12 供给审计类别集（共 12 类）"
        )
    if actor_kind not in ("USER", "AI"):
        raise ValueError("actor_kind 必须为 USER 或 AI")
    full_detail = f"{detail}; {_RED_LINE_MARKER}" if detail else _RED_LINE_MARKER
    return ProvisioningAuditEvent(
        record_id=record_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        category=category,
        action=action,
        target=target,
        detail=full_detail,
        ts=ts,
    )


__all__ = [
    "PROVISIONING_AUDIT_CATEGORIES",
    "ProvisioningAuditEvent",
    "build_provisioning_audit_event",
]
