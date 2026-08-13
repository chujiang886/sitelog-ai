"""Phase 3.9.7 企业生产变更管控平面 —— 权限边界（Permission Boundary）。

把"谁可以对生产变更管控层做什么"收敛为单一事实源（SSOT）。后端 API 与测试都复用本模块，
避免权限判断散落各处、出现"某端点漏掉 human-gating"的治理黑洞。

权限字符串复用 ``backend/app/identity/permissions.py::GovernancePermission`` 的
``governance:release:read`` / ``governance:release:signoff``（reuse-not-duplicate）：
变更管控与发布闸门共用同一组"真实责任人 + 治理管理员"权限模型（四角色一致、管理员独享签署），
故本模块复用之，不另起一套权限枚举。

设计要点（fail-closed）
----------------------
* 每个操作都强制 ``actor_kind == 'user'``（真实自然人），AI / SYSTEM 一律拒绝
  （红线③/⑥/⑧/⑨）；
* 每个操作映射到一个**最小**治理权限字符串，与
  ``backend/app/identity/permissions.py::GovernancePermission`` 的字符串一一对齐，
  复用而非复制权限枚举（reuse-not-duplicate）；
* 任何**未在本表登记**的操作，默认**拒绝**（白名单，fail-closed）；
* 本模块不持有任何生产状态、不翻转 ``engineering_enabled``、不宣布 GO、不执行变更。

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

#: 与 ``backend/app/identity/permissions.py::GovernancePermission`` 字符串对齐（复用）。
PERM_RELEASE_READ = "governance:release:read"
PERM_RELEASE_SIGNOFF = "governance:release:signoff"


class ChangePermissionBoundaryError(EnterpriseRedLineViolationError):
    """权限边界被违反（fail-closed，继承红线异常）。"""


class ChangeOperation(str, Enum):
    """Phase 3.9.7 生产变更管控平面暴露的全部操作（白名单）。

    任何不在本枚举内的动作都**不允许**直达本治理层；新增操作必须先在此登记并
    明确其所需最小权限，杜绝"暗门"。
    """

    VIEW_CHANGE_READINESS = "view_change_readiness"                  # 只读：变更就绪档案
    SUBMIT_CHANGE_EVIDENCE = "submit_change_evidence"                # 真实 USER 提交证据
    VALIDATE_CHANGE_EVIDENCE = "validate_change_evidence"           # 结构/哈希/溯源校验
    RECORD_CHANGE_PLAN = "record_change_plan"                       # 真实 USER 登记变更计划
    RESERVE_CHANGE_WINDOW = "reserve_change_window"                 # 真实 USER 预约变更窗口
    RECORD_CHANGE_PREFLIGHT = "record_change_preflight"             # 真实 USER 记录预检
    RECORD_CHANGE_CHECKPOINT = "record_change_checkpoint"           # 真实 USER 记录检查点
    REGISTER_CHANGE_ABORT_POLICY = "register_change_abort_policy"   # 真实 USER 登记中止策略
    REGISTER_CHANGE_ROLLBACK_REF = "register_change_rollback_ref"   # 真实 USER 登记回滚引用
    RECORD_POST_CHANGE_VERIFICATION = "record_post_change_verification"  # 真实 USER 登记变更后验证
    PERFORM_CHANGE_SIMULATION = "perform_change_simulation"         # 真实 USER 触发受控仿真
    EVALUATE_FAILURE_SCENARIO = "evaluate_failure_scenario"         # 真实 USER 评估失败场景
    BUILD_CHANGE_PACKAGE = "build_change_package"                   # 生成供人裁决材料包
    REGISTER_CHANGE_SIGNOFF = "register_change_signoff"             # 真实 USER 四角色签署
    RECORD_CHANGE_DECISION = "record_change_decision"               # 真实 USER 最终裁决登记


#: 操作 → 最小治理权限（白名单映射；缺省即拒绝）。
OPERATION_PERMISSION: dict = {
    ChangeOperation.VIEW_CHANGE_READINESS: PERM_RELEASE_READ,
    ChangeOperation.SUBMIT_CHANGE_EVIDENCE: PERM_RELEASE_READ,
    ChangeOperation.VALIDATE_CHANGE_EVIDENCE: PERM_RELEASE_READ,
    ChangeOperation.RECORD_CHANGE_PLAN: PERM_RELEASE_READ,
    ChangeOperation.RESERVE_CHANGE_WINDOW: PERM_RELEASE_READ,
    ChangeOperation.RECORD_CHANGE_PREFLIGHT: PERM_RELEASE_READ,
    ChangeOperation.RECORD_CHANGE_CHECKPOINT: PERM_RELEASE_READ,
    ChangeOperation.REGISTER_CHANGE_ABORT_POLICY: PERM_RELEASE_READ,
    ChangeOperation.REGISTER_CHANGE_ROLLBACK_REF: PERM_RELEASE_READ,
    ChangeOperation.RECORD_POST_CHANGE_VERIFICATION: PERM_RELEASE_READ,
    ChangeOperation.PERFORM_CHANGE_SIMULATION: PERM_RELEASE_READ,
    ChangeOperation.EVALUATE_FAILURE_SCENARIO: PERM_RELEASE_READ,
    ChangeOperation.BUILD_CHANGE_PACKAGE: PERM_RELEASE_READ,
    ChangeOperation.REGISTER_CHANGE_SIGNOFF: PERM_RELEASE_SIGNOFF,
    ChangeOperation.RECORD_CHANGE_DECISION: PERM_RELEASE_SIGNOFF,
}

#: 仅"写入 / 裁决"类操作需要 RELEASE_SIGNOFF；其余为只读（RELEASE_READ）。
_WRITE_OPERATIONS: Tuple[ChangeOperation, ...] = (
    ChangeOperation.SUBMIT_CHANGE_EVIDENCE,
    ChangeOperation.VALIDATE_CHANGE_EVIDENCE,
    ChangeOperation.RECORD_CHANGE_PLAN,
    ChangeOperation.RESERVE_CHANGE_WINDOW,
    ChangeOperation.RECORD_CHANGE_PREFLIGHT,
    ChangeOperation.RECORD_CHANGE_CHECKPOINT,
    ChangeOperation.REGISTER_CHANGE_ABORT_POLICY,
    ChangeOperation.REGISTER_CHANGE_ROLLBACK_REF,
    ChangeOperation.RECORD_POST_CHANGE_VERIFICATION,
    ChangeOperation.PERFORM_CHANGE_SIMULATION,
    ChangeOperation.EVALUATE_FAILURE_SCENARIO,
    ChangeOperation.BUILD_CHANGE_PACKAGE,
    ChangeOperation.REGISTER_CHANGE_SIGNOFF,
    ChangeOperation.RECORD_CHANGE_DECISION,
)


def is_write_operation(operation: ChangeOperation) -> bool:
    """该操作是否属于"写入 / 裁决"类（用于审计语义区分）。"""

    return operation in _WRITE_OPERATIONS


def require_change_operation(
    *,
    operation: ChangeOperation,
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
        raise ChangePermissionBoundaryError(
            "safety_invariants_ok() 失败：禁止在启用态下执行任何变更管控操作（红线①）"
        )

    # 1) 真实自然人闸门（最高优先级，任何非 user 主体直接拒绝）。
    if (actor_kind or "").strip().lower() != REQUIRED_ACTOR_KIND:
        raise ChangePermissionBoundaryError(
            f"operation {operation.value!r} requires a real human user "
            f"(actor_kind='user'), got {actor_kind!r}（红线③/⑥/⑧/⑨）"
        )

    # 2) 白名单登记（未登记 = 默认拒绝）。
    required = OPERATION_PERMISSION.get(operation)
    if required is None:
        raise ChangePermissionBoundaryError(
            f"operation {operation.value!r} is not registered in the change-control "
            "permission boundary (deny-by-default, fail-closed)"
        )

    # 3) 最小权限校验。
    held = {str(p).strip() for p in granted_permissions}
    if required not in held:
        raise ChangePermissionBoundaryError(
            f"operation {operation.value!r} requires permission {required!r}, "
            f"principal holds {sorted(held) or '[]'}（职责分离：越权被拒）"
        )


@dataclass(frozen=True)
class ChangePermissionBoundary:
    """某个变更的管控权限边界（只读描述 + 复用校验）。

    实例本身只承载 ``change_id``；真正的校验委托给模块级
    ``require_change_operation``。``describe()`` 用于 SSOT / 文档生成。
    """

    change_id: str

    def require(
        self,
        *,
        operation: ChangeOperation,
        actor_kind: str,
        granted_permissions: Iterable[str],
    ) -> None:
        """以本变更上下文执行 fail-closed 权限校验。"""

        require_change_operation(
            operation=operation,
            actor_kind=actor_kind,
            granted_permissions=granted_permissions,
        )

    def describe(self) -> dict:
        """返回权限边界全表（机器可读，供治理文档 / API 自省）。"""

        rows = []
        for op in ChangeOperation:
            rows.append(
                {
                    "operation": op.value,
                    "required_permission": OPERATION_PERMISSION.get(op),
                    "required_actor_kind": REQUIRED_ACTOR_KIND,
                    "is_write": is_write_operation(op),
                }
            )
        return {
            "change_id": self.change_id,
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
    "ChangePermissionBoundaryError",
    "ChangeOperation",
    "OPERATION_PERMISSION",
    "is_write_operation",
    "require_change_operation",
    "ChangePermissionBoundary",
]
