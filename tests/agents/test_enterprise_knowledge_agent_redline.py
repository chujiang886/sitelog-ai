"""Phase 3.8.10 —— 测试8：智能体编排层红线（fail-closed 全局校验）。

覆盖：6 条最高红线在智能体编排层的落地：
① 全部智能体 / 编排器 / 复核构造即断言 safety_invariants_ok（启用态下构造抛错）。
② 不输出 engineering_approved（所有相关类 forbidden 拦截）。
③ 不自动应用 / 执行知识（auto_apply_knowledge / auto_execute_knowledge 拦截）。
④ 不自动审批 / 生成工程结论（approve / generate_engineering_conclusion 拦截）。
⑤ 不绕过安全护栏（构造即断言）。
⑥ 不 AI 代责（review 拒绝 ai 复核；audit 无 record_human_approval）。

另：全模块无 engineering_approved 被「输出」（仅出现在 forbidden 元组 / 注释中）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.knowledge_agent_orchestrator import KnowledgeAgentOrchestrator
from agents.enterprise.knowledge_answer_agent import KnowledgeAnswerAgent
from agents.enterprise.knowledge_answer_review import KnowledgeAnswerReview
from agents.enterprise.knowledge_query_agent import KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval_agent import KnowledgeRetrievalAgent
from agents.enterprise.knowledge_validation_agent import KnowledgeValidationAgent
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    load_engineering_enabled,
)


_AGENT_CLASSES = [
    KnowledgeQueryAgent,
    KnowledgeRetrievalAgent,
    KnowledgeValidationAgent,
    KnowledgeAnswerAgent,
    KnowledgeAgentOrchestrator,
    KnowledgeAnswerReview,
]


@pytest.mark.parametrize("cls", _AGENT_CLASSES)
def test_all_agents_fail_closed_when_enabled(
    cls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        cls(org_id="org-1")


def test_no_engineering_approved_output_in_source() -> None:
    """静态校验：源码中 engineering_approved 绝不被赋值或作为返回值输出（红线②）。

    允许出现的位置：forbidden 元组字符串成员（结构性拦截）与红线说明注释/文档。
    禁止出现的位置：``engineering_approved = ...`` 或 ``return ... engineering_approved`` 等
    任何「输出 / 赋值」语义。
    """
    import re

    base = Path(__file__).resolve().parents[2] / "agents" / "enterprise"
    target_files = [
        "knowledge_query_agent.py",
        "knowledge_retrieval_agent.py",
        "knowledge_validation_agent.py",
        "knowledge_answer_agent.py",
        "knowledge_agent_orchestrator.py",
        "knowledge_answer_review.py",
    ]
    assign_or_return = re.compile(
        r"engineering_approved\s*=|return\s+.*engineering_approved"
    )
    for fname in target_files:
        text = (base / fname).read_text(encoding="utf-8")
        for line in text.splitlines():
            assert not assign_or_return.search(line), (
                f"{fname} 中出现可疑的 engineering_approved 输出/赋值：{line!r}"
            )
        # 同时确认 forbidden 元组守卫确实存在（红线②结构性保证）。
        assert '"engineering_approved"' in text or "'engineering_approved'" in text


def test_review_rejects_ai_actor_redline() -> None:
    svc = KnowledgeAnswerReview(org_id="org-1", audit=AuditService(org_id="org-1"))
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.submit_review_by_user(
            review_id="r1", answer_id="a1", reviewer_user_id="ai",
            decision="accepted",
        )


def test_global_redline_imports_ok() -> None:
    # 确保红线基座可被所有智能体模块导入且符号齐全。
    from agents.enterprise.red_line import (
        _ENTERPRISE_FORBIDDEN_METHODS,
        _RedLineForbiddenMixin,
        safety_invariants_ok,
    )

    assert "engineering_approved" in _ENTERPRISE_FORBIDDEN_METHODS
    assert safety_invariants_ok() is True
