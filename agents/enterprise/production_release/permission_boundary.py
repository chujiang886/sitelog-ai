"""Phase 3.9.6 T12 权限边界（Permission Boundary）。

把"谁可以对生产激活证据层做什么"收敛为单一事实源（SSOT）。后端 API（T14）与
测试（T16）都复用本模块，避免权限判断散落各处、出现"某端点漏掉 human-gating"的
治理黑洞。

设计要点（fail-closed）
----------------------
* 每个操作都强制 ``actor_kind == 'user'``（真实自然人），AI / SYSTEM 一律拒绝
  （红线③/⑥/⑧/⑨）；
* 每个操作映射到一个**最小**治理权限字符串，与
  ``backend/app/identity/permissions.py::GovernancePermission`` 的字符串一一对齐，
  复用而非复制权限枚举（reuse-not-duplicate）；
* 任何**未在本表登记**的操作，默认**拒绝**（白名单，fail-closed）；
* 本模块不持有任何生产状态、不翻转 ``engineering_enabled``、不宣布 GO、不激活。

本模块刻意不依赖 FastAPI / 前端框架，保持纯领域层，便于单元测试与多端复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Tuple

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


#: 真实责任人种类（审计层同口径 ``AuditActorKind.USER``）。
REQUIRED_ACTOR_KIND = "user"

#: 与 ``backend/app/identity/permissions.py::GovernancePermission`` 字符串对齐。
PERM_RELEASE_READ = "governance:release:read"
PERM_RELEASE_SIGNOFF = "governance:release:signoff"


class ActivationPermissionBoundaryError(EnterpriseRedLineViolationError):
    """权限边界被违反（fail-closed，继承红线异常）。"""


class ActivationOperation(str, Enum):
    """Phase 3.9.6 生产激活证据层暴露的全部操作（白名单）。

    任何不在本枚举内的动作都**不允许**直达本治理层；新增操作必须先在此登记并
    明确其所需最小权限，杜绝"暗门"。
    """

    VIEW_READINESS = "view_readiness"                      # 只读：就绪档案
    SUBMIT_EVIDENCE = "submit_evidence"                    # 真实 USER 提交证据
    VALIDATE_EVIDENCE = "validate_evidence"                # 结构/哈希/溯源校验
    RECORD_EVIDENCE_DECISION = "record_evidence_decision"  # 真实 USER 对单条证据裁决
    REGISTER_SIGNOFF = "register_signoff"                  # 真实 USER 四角色签署
    BUILD_REVIEW_PACKAGE = "build_review_package"          # 生成供人裁决材料包
    RECORD_FINAL_DECISION = "record_final_decision"        # 真实 USER 最终裁决登记


#: 操作 → 最小治理权限（白名单映射；缺省即拒绝）。
OPERATION_PERMISSION: dict = {
    ActivationOperation.VIEW_READINESS: PERM_RELEASE_READ,
    ActivationOperation.SUBMIT_EVIDENCE: PERM_RELEASE_READ,
    ActivationOperation.VALIDATE_EVIDENCE: PERM_RELEASE_READ,
    ActivationOperation.RECORD_EVIDENCE_DECISION: PERM_RELEASE_SIGNOFF,
    ActivationOperation.REGISTER_SIGNOFF: PERM_RELEASE_SIGNOFF,
    ActivationOperation.BUILD_REVIEW_PACKAGE: PERM_RELEASE_READ,
    ActivationOperation.RECORD_FINAL_DECISION: PERM_RELEASE_SIGNOFF,
}

#: 仅"写入 / 裁决"类操作需要 RELEASE_SIGNOFF；其余为只读（RELEASE_READ）。
_WRITE_OPERATIONS: Tuple[ActivationOperation, ...] = (
    ActivationOperation.SUBMIT_EVIDENCE,
    ActivationOperation.VALIDATE_EVIDENCE,
    ActivationOperation.RECORD_EVIDENCE_DECISION,
    ActivationOperation.REGISTER_SIGNOFF,
    ActivationOperation.BUILD_REVIEW_PACKAGE,
    ActivationOperation.RECORD_FINAL_DECISION,
)


def is_write_operation(operation: ActivationOperation) -> bool:
    """该操作是否属于"写入 / 裁决"类（用于审计语义区分）。"""

    return operation in _WRITE_OPERATIONS


def require_activation_operation(
    *,
    operation: ActivationOperation,
    actor_kind: str,
    granted_permissions: Iterable[str],
) -> None:
    """fail-closed 校验某主体能否执行某操作。

    条件（全部满足才放行）：
    1. ``actor_kind == 'user'`` —— AI / SYSTEM 主体一律 403 级拒绝；
    2. 操作已在白名单登记（否则默认拒绝）；
    3. 主体持有的权限集合包含该操作所需最小权限。

    本函数**只**回答"能不能做这一动作"，不回答"能不能放行生产"——
    放行仍是主理人在人类终端、四角色签署后的现实动作（红线②⑤⑩）。
    """

    if not safety_invariants_ok():
        raise ActivationPermissionBoundaryError(
            "safety_invariants_ok() 失败：禁止在启用态下执行任何激活证据操作（红线①）"
        )

    # 1) 真实自然人闸门（最高优先级，任何非 user 主体直接拒绝）。
    if (actor_kind or "").strip().lower() != REQUIRED_ACTOR_KIND:
        raise ActivationPermissionBoundaryError(
            f"operation {operation.value!r} requires a real human user "
            f"(actor_kind='user'), got {actor_kind!r}（红线③/⑥/⑧/⑨）"
        )

    # 2) 白名单登记（未登记 = 默认拒绝）。
    required = OPERATION_PERMISSION.get(operation)
    if required is None:
        raise ActivationPermissionBoundaryError(
            f"operation {operation.value!r} is not registered in the activation "
            "permission boundary (deny-by-default, fail-closed)"
        )

    # 3) 最小权限校验。
    held = {str(p).strip() for p in granted_permissions}
    if required not in held:
        raise ActivationPermissionBoundaryError(
            f"operation {operation.value!r} requires permission {required!r}, "
            f"principal holds {sorted(held) or '[]'}（职责分离：越权被拒）"
        )


@dataclass(frozen=True)
class ActivationPermissionBoundary:
    """某个 RC 的激活证据权限边界（只读描述 + 复用校验）。

    实例本身只承载 ``rc_id``；真正的校验委托给模块级
    ``require_activation_operation``。``describe()`` 用于 SSOT / 文档生成。
    """

    rc_id: str

    def require(
        self,
        *,
        operation: ActivationOperation,
        actor_kind: str,
        granted_permissions: Iterable[str],
    ) -> None:
        """以本 RC 上下文执行 fail-closed 权限校验。"""

        require_activation_operation(
            operation=operation,
            actor_kind=actor_kind,
            granted_permissions=granted_permissions,
        )

    def describe(self) -> dict:
        """返回权限边界全表（机器可读，供治理文档 / API 自省）。"""

        rows = []
        for op in ActivationOperation:
            rows.append(
                {
                    "operation": op.value,
                    "required_permission": OPERATION_PERMISSION.get(op),
                    "required_actor_kind": REQUIRED_ACTOR_KIND,
                    "is_write": is_write_operation(op),
                }
            )
        return {
            "rc_id": self.rc_id,
            "required_actor_kind": REQUIRED_ACTOR_KIND,
            "permission_reference": "reuse GovernancePermission "
            "(governance:release:read / governance:release:signoff)",
            "policy": "deny-by-default whitelist; AI/SYSTEM always denied",
            "operations": rows,
            "note": "本边界只回答'谁能执行哪个治理动作'；"
            "不回答'能否放行生产'（红线②⑤⑩）",
        }


__all__ = [
    "REQUIRED_ACTOR_KIND",
    "PERM_RELEASE_READ",
    "PERM_RELEASE_SIGNOFF",
    "ActivationPermissionBoundaryError",
    "ActivationOperation",
    "OPERATION_PERMISSION",
    "is_write_operation",
    "require_activation_operation",
    "ActivationPermissionBoundary",
]
