"""Engineering AI Read Boundary（Phase 3.4 Sprint 3.4.1, Task 3）。

明确 Engineering AI 可读取 / 不可读取的边界（声明性约束，运行期由消费层遵守）：
- AI 可以读取：KnowledgeItem 元数据 / quality_report / relationship / conflict。
- AI 不可读取 / 不可消费：
  - verified.json 的真实 value（红线③）；
  - ReleaseApproval 的创建权限（G6 由主理人线下产生，AI 不代建）；
  - engineering_enabled 的写权限（读 load_engineering_enabled 仅用于只读断言）。

不变量：AI 对知识的所有读取不改变任何 item 的 validation_status、不写审计事件、
不翻 engineering_enabled。
"""

from __future__ import annotations

# AI 允许读取的知识视图类别。
ALLOWED_KINDS: frozenset[str] = frozenset(
    {
        "metadata",        # KnowledgeItem 13 元数据字段
        "quality_report",  # KnowledgeQualityReport（仅辅助信号）
        "relationship",    # RelationshipCandidate（用于规避，不自动解决）
        "conflict",        # ConflictReport（用于规避，不自动解决）
    }
)


class KnowledgeReadBoundary:
    """Task 3：Engineering AI 读取边界（声明性，全为只读判定）。"""

    def can_read(self, kind: str) -> bool:
        """kind 是否属于 AI 允许读取的知识视图类别。"""
        return kind in ALLOWED_KINDS

    def allowed_kinds(self) -> frozenset[str]:
        return ALLOWED_KINDS

    def can_read_verified_value(self) -> bool:
        """AI 不得消费 verified.json 真实 value（红线③）。"""
        return False

    def can_create_release_approval(self) -> bool:
        """AI 不得创建 ReleaseApproval（G6 由主理人线下产生）。"""
        return False

    def can_write_engineering_enabled(self) -> bool:
        """AI 不得写 engineering_enabled（仅可读断言）。"""
        return False

    def can_self_produce_approved(self) -> bool:
        """AI 不得自助产生 Engineering_Approved（仅校验，不签发）。"""
        return False

    def read_invariants_ok(self) -> bool:
        """读取边界不变量：不读 verified value / 不建 ReleaseApproval / 不写 enabled。"""
        return not (
            self.can_read_verified_value()
            or self.can_create_release_approval()
            or self.can_write_engineering_enabled()
        )


__all__ = [
    "ALLOWED_KINDS",
    "KnowledgeReadBoundary",
]
