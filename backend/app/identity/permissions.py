"""治理权限目录（Phase 3.8.28 T2）—— 前后端唯一词表。

## 为什么权限词表必须只有一份

Phase 3.8.27 T3 在前端建立了 ``GovernancePermission`` 联合类型；如果后端
另起一套命名（哪怕只差一个冒号），会立刻退化成两个后果：

- 前端按 A 词表算出"能点"，后端按 B 词表判定"不能做" —— 用户看到按钮亮着
  却永远失败，运维只能靠猜；
- 更危险的反向：前端算出"不能点"把按钮灰掉，团队据此以为该动作被管住了，
  而后端因为词表对不上根本没挂上校验 —— **权限在视觉上存在，在执行上缺席**。

因此本模块的枚举值与 ``frontend/src/lib/identity/types.ts`` 的
``GovernancePermission`` **逐字相同**，角色映射与 ``guards.ts`` 的
``ROLE_PERMISSIONS`` **逐项相同**，并由测试钉死（见 T5 词表对齐用例）。

## 默认拒绝

``permissions_for_roles`` 对未知角色贡献空集：多一个不认识的角色不会带来
任何权限，权限只能由显式登记的映射产生。空角色列表 ⇒ 空权限集 ⇒ 拒绝一切
治理动作（读也不行）。

## 结构性红线（②/③/④/⑤）

治理权限里**不存在**任何"自动"语义的权限点。``governance:review:confirm``
的含义是"有资格提交一次人工研判"，**不是**"研判可以自动通过"——它授予的是
按钮的可见性，不是判断本身；判断仍然必须由持有该权限的自然人做出。

``FORBIDDEN_PERMISSION_PATTERNS`` 在运行时扫描任何进入系统的权限名，命中即
判定整份凭据不可信（而非过滤掉该项后继续）。理由见
``assert_no_forbidden_permission`` 的文档串。
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping

from app.identity.errors import IdentityRedLineViolationError


class GovernancePermission(str, Enum):
    """治理权限点。取值与前端 ``GovernancePermission`` 逐字一致。

    读写分列。写权限刻意拆成四个而不是合并成一个 ``governance:write``：
    "登记一条治理线索"、"下一次研判结论"、"提交处置结果"、"宣布闭环"是四种
    性质不同的责任，合并之后就无法表达"这个人能记录情况但不能替组织下结论"
    这类真实存在的岗位边界。
    """

    WORKFLOW_READ = "governance:workflow:read"
    REVIEW_READ = "governance:review:read"
    # 有权"提交"人工研判，不等于研判可以自动通过。
    REVIEW_CONFIRM = "governance:review:confirm"
    EXECUTION_READ = "governance:execution:read"
    AUDIT_READ = "governance:audit:read"
    SUMMARY_READ = "governance:summary:read"
    WORKFLOW_REPORT = "governance:workflow:report"
    EXECUTION_SUBMIT = "governance:execution:submit"
    WORKFLOW_CLOSE = "governance:workflow:close"


ALL_GOVERNANCE_PERMISSIONS: tuple[GovernancePermission, ...] = tuple(
    GovernancePermission
)

#: 治理角色名。与业务角色（admin/designer/viewer）**不共用命名空间**：
#: 一个"业务管理员"不因此自动获得治理审批资格，治理角色必须单独授予。
GOVERNANCE_ROLE_ADMIN = "governance-admin"
GOVERNANCE_ROLE_REVIEWER = "governance-reviewer"
GOVERNANCE_ROLE_AUDITOR = "governance-auditor"
GOVERNANCE_ROLE_VIEWER = "governance-viewer"

GOVERNANCE_ROLES: tuple[str, ...] = (
    GOVERNANCE_ROLE_ADMIN,
    GOVERNANCE_ROLE_REVIEWER,
    GOVERNANCE_ROLE_AUDITOR,
    GOVERNANCE_ROLE_VIEWER,
)

#: 角色 → 权限。与前端 ``guards.ts`` 的 ``ROLE_PERMISSIONS`` 逐项一致。
#:
#: 注意 admin 与 reviewer 的差别只在 ``audit:read``，而 auditor 明确
#: **没有** ``review:confirm``：审计者能看全部留痕但不能下判断，判断者
#: 能下判断但看不到全量审计 —— 这是刻意的职责分离，防止同一个人既做
#: 判断又改写对自己判断的审计视角。
GOVERNANCE_ROLE_PERMISSIONS: Mapping[str, frozenset[GovernancePermission]] = {
    GOVERNANCE_ROLE_ADMIN: frozenset(
        {
            GovernancePermission.WORKFLOW_READ,
            GovernancePermission.REVIEW_READ,
            GovernancePermission.REVIEW_CONFIRM,
            GovernancePermission.EXECUTION_READ,
            GovernancePermission.AUDIT_READ,
            GovernancePermission.SUMMARY_READ,
            GovernancePermission.WORKFLOW_REPORT,
            GovernancePermission.EXECUTION_SUBMIT,
            GovernancePermission.WORKFLOW_CLOSE,
        }
    ),
    GOVERNANCE_ROLE_REVIEWER: frozenset(
        {
            GovernancePermission.WORKFLOW_READ,
            GovernancePermission.REVIEW_READ,
            GovernancePermission.REVIEW_CONFIRM,
            GovernancePermission.EXECUTION_READ,
            GovernancePermission.SUMMARY_READ,
            GovernancePermission.WORKFLOW_REPORT,
            GovernancePermission.EXECUTION_SUBMIT,
            GovernancePermission.WORKFLOW_CLOSE,
        }
    ),
    # 审计员能看见一切，但一个写权限都没有：看得见与说了算是两回事。
    GOVERNANCE_ROLE_AUDITOR: frozenset(
        {
            GovernancePermission.WORKFLOW_READ,
            GovernancePermission.REVIEW_READ,
            GovernancePermission.EXECUTION_READ,
            GovernancePermission.AUDIT_READ,
            GovernancePermission.SUMMARY_READ,
        }
    ),
    GOVERNANCE_ROLE_VIEWER: frozenset(
        {
            GovernancePermission.WORKFLOW_READ,
            GovernancePermission.REVIEW_READ,
            GovernancePermission.SUMMARY_READ,
        }
    ),
}

#: 会改变治理事实的权限点。用于测试断言"只读角色一个写权限都不能有"。
GOVERNANCE_WRITE_PERMISSIONS: frozenset[GovernancePermission] = frozenset(
    {
        GovernancePermission.REVIEW_CONFIRM,
        GovernancePermission.WORKFLOW_REPORT,
        GovernancePermission.EXECUTION_SUBMIT,
        GovernancePermission.WORKFLOW_CLOSE,
    }
)

#: 任何角色都不得持有、任何凭据都不得声明的权限名片段（小写比较）。
#: 与前端 ``FORBIDDEN_PERMISSION_PATTERNS`` 同源，后端为最终裁决方；
#: 两侧词表由 ``tests/test_governance_identity_security.py`` 的"词表对齐"用例
#: 钉死为逐字相等，任意一侧新增/删除禁语都必须同步另一侧，否则后端测试失败。
FORBIDDEN_PERMISSION_PATTERNS: tuple[str, ...] = (
    "auto_approve",
    "auto-approve",
    "autoapprove",
    "auto_confirm",
    "auto-confirm",
    "auto_execute",
    "auto-execute",
    "auto_close",
    "auto-close",
    "auto_review",
    "auto-review",
    "ai_approve",
    "ai-approve",
    "agent_approve",
    "self_approve",
    "bypass_human",
    "bypass-human",
    "skip_human",
    "skip-human",
    "skip_review",
    "skip-review",
    "without_human",
    "no_human",
    "engineering_approved",
    "engineering_enabled",
)


def assert_no_forbidden_permission(names: Iterable[str]) -> None:
    """命中禁语即整份拒绝（红线②/③/④/⑤）。

    **为什么是"整份拒绝"而不是"过滤掉再用"**：一份声称自己拥有
    ``auto_approve`` 的凭据，说明签发它的那一侧对治理边界的理解已经错了。
    悄悄摘掉这一项、留下其余权限继续放行，等于承认了这份凭据的其余部分
    可信 —— 而我们并没有任何依据这样认为。宁可让持有者拿不到任何权限、
    被迫去查为什么，也不要产生一个"被静默削权后看起来正常工作"的会话。
    """

    for raw in names:
        low = str(raw).strip().lower()
        if not low:
            continue
        for pattern in FORBIDDEN_PERMISSION_PATTERNS:
            if pattern in low:
                raise IdentityRedLineViolationError(
                    f"凭据声明了禁止的权限 {raw!r}（命中禁语 {pattern!r}）："
                    "治理系统不存在任何自动审批/自动执行权限，整份凭据判定不可信。"
                )


def permissions_for_roles(
    roles: Iterable[str],
) -> frozenset[GovernancePermission]:
    """角色 → 权限并集。未知角色贡献空集（默认拒绝）。

    这里刻意**不**抛异常：一个用户同时持有业务角色（designer）和治理角色
    （governance-reviewer）是正常状态，业务角色在治理维度上就该什么都不给。
    "不认识 ⇒ 不给"比"不认识 ⇒ 报错"更符合最小权限，也避免业务侧加一个
    新角色就把治理登录整体打挂。
    """

    out: set[GovernancePermission] = set()
    for role in roles:
        key = str(role).strip()
        granted = GOVERNANCE_ROLE_PERMISSIONS.get(key)
        if granted:
            out |= granted
    return frozenset(out)


def is_governance_role(role: str) -> bool:
    """该角色名是否属于治理角色命名空间。"""

    return str(role).strip() in GOVERNANCE_ROLE_PERMISSIONS


def parse_permission(value: str) -> GovernancePermission | None:
    """把字符串解析为权限枚举；不认识的返回 ``None``（默认拒绝）。"""

    try:
        return GovernancePermission(str(value).strip())
    except ValueError:
        return None


__all__ = [
    "ALL_GOVERNANCE_PERMISSIONS",
    "FORBIDDEN_PERMISSION_PATTERNS",
    "GOVERNANCE_ROLES",
    "GOVERNANCE_ROLE_ADMIN",
    "GOVERNANCE_ROLE_AUDITOR",
    "GOVERNANCE_ROLE_PERMISSIONS",
    "GOVERNANCE_ROLE_REVIEWER",
    "GOVERNANCE_ROLE_VIEWER",
    "GOVERNANCE_WRITE_PERMISSIONS",
    "GovernancePermission",
    "assert_no_forbidden_permission",
    "is_governance_role",
    "parse_permission",
    "permissions_for_roles",
]
