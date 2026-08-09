"""Enterprise Knowledge Agent Orchestration Layer —— 查询理解智能体（任务1，Phase 3.8.10）。

新增：``KnowledgeQueryAgent``（AI 智能体）。

职责（红线严格限定）：
- **只理解用户需求**：``parse_query`` / ``identify_intent`` / ``extract_filters`` 仅做自然语言
  理解的解析工作，**绝不生成任何工程判断 / 工程结论**（``generate_engineering_conclusion`` 等
  决策入口在结构上被拦截，红线④/⑤）。
- 不自动应用知识、不自动执行知识（``auto_apply_knowledge`` / ``auto_execute_knowledge`` 被拦截，
  红线③）。
- 不输出 ``engineering_approved``（红线②）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 智能体默认 AI，红线⑥：绝不伪造为人工审批）。

数据流：``raw_query``（用户原文） → ``KnowledgeQuery``（结构化解析结果：意图 + 过滤条件）。
后续由检索智能体 / 校验智能体 / 回答起草智能体接力，**本智能体不参与任何知识落地或结论生成**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


@dataclass
class KnowledgeQuery:
    """查询理解结果（任务1）。

    由 ``KnowledgeQueryAgent.parse_query`` 产出；仅承载「用户需求的结构化理解」：
    - ``intent``：识别出的意图类别（如 ``ask_regulation`` / ``ask_design_spec`` /
      ``ask_case`` / ``ask_manual`` / ``ask_governance`` / ``ask_feedback`` / ``unknown``）。
    - ``filters``：从查询中抽取的结构化过滤条件（``knowledge_type`` / ``source`` / ``tags`` 等），
      供后续检索智能体直接使用。

    本对象**不**包含任何工程判断 / 工程结论（由智能体在结构上保证，红线④/⑤）。
    """

    query_id: str
    raw_query: str
    intent: str = "unknown"
    filters: dict = field(default_factory=dict)
    parsed_at: str = ""
    org_id: str = ""

    def derive_knowledge_type(self) -> str:
        """从意图反推知识类型提示（供检索过滤使用；unknown 返回空串，由引擎回退到无类型过滤）。"""
        mapping = {
            "ask_regulation": "regulation",
            "ask_design_spec": "design_spec",
            "ask_case": "case",
            "ask_manual": "manual",
            "ask_governance": "governance",
            "ask_feedback": "feedback",
        }
        return mapping.get(self.intent, "")


# 意图关键词映射（确定性启发式，无外部 LLM 依赖）。
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "ask_regulation": ["规范", "法规", "标准", "regulation", "code", "standard"],
    "ask_design_spec": ["设计", "图纸", "型材", "design", "spec", "profile"],
    "ask_case": ["案例", "工程实例", "case", "example", "instance"],
    "ask_manual": ["手册", "操作", "工艺", "manual", "operation", "process"],
    "ask_governance": ["治理", "流程", "制度", "governance", "process", "policy"],
    "ask_feedback": ["反馈", "问题", "复盘", "feedback", "issue", "lesson"],
}


class KnowledgeQueryAgent(_RedLineForbiddenMixin):
    """查询理解智能体（任务1）。

    仅解析用户查询（意图识别 + 过滤条件抽取），**不参与任何知识落地 / 结论生成**。
    跨域访问抛 ``EnterpriseIsolationError``；构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。

    本智能体**不**持有 approve / engineering_approved / auto_apply_knowledge /
    auto_execute_knowledge / generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③：禁止 AI 自动落地/应用/执行知识（查询智能体只理解，不落地）
        "auto_apply_knowledge",
        "auto_execute_knowledge",
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_activate",
        "publish",
        "merge",
        "apply",
        "commit",
        "write",
        # 红线④/⑤：禁止自动生成工程结论 / 经营决策 / 审批 / 管理建议
        "generate_engineering_conclusion",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeQueryAgent（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def parse_query(
        self,
        *,
        query_id: str,
        raw_query: str,
        parsed_at: str = "",
        actor_id: str = "ai",
    ) -> KnowledgeQuery:
        """解析用户查询：识别意图 + 抽取过滤条件（仅理解，不生成工程判断，红线④/⑤）。

        如实记录 ``KNOWLEDGE_AGENT_QUERY`` 审计（AI 智能体默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下解析查询（红线①/⑤）"
            )
        intent = self.identify_intent(raw_query=raw_query)
        filters = self.extract_filters(raw_query=raw_query, intent=intent)
        query = KnowledgeQuery(
            query_id=query_id,
            raw_query=raw_query,
            intent=intent,
            filters=filters,
            parsed_at=parsed_at,
            org_id=self._org_id,
        )
        if self._audit is not None:
            self._audit.record_knowledge_agent_query_action(
                record_id=f"agent-query-{query_id}",
                actor_id=actor_id,
                action="understand_user_query",
                target=query_id,
                detail=(
                    f"intent={intent};filters={len(filters)};"
                    f"knowledge_type={query.derive_knowledge_type() or 'none'}"
                ),
                ts=parsed_at,
                actor_kind=AuditActorKind.AI,
            )
        return query

    def identify_intent(self, *, raw_query: str) -> str:
        """识别查询意图（确定性关键词匹配；无命中返回 ``unknown``）。

        仅做意图分类，**不**对查询结果做任何工程判断（红线④/⑤）。
        """
        lowered = (raw_query or "").lower()
        best: str = "unknown"
        best_hits = 0
        for intent, keywords in _INTENT_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in lowered)
            if hits > best_hits:
                best_hits = hits
                best = intent
        return best

    def extract_filters(self, *, raw_query: str, intent: str) -> dict:
        """从查询中抽取结构化过滤条件（知识类型提示 + 标签词元）。

        仅产出检索用的候选过滤条件，**不**承载任何工程含义（红线④/⑤）。
        """
        filters: dict = {}
        ktype = {
            "ask_regulation": "regulation",
            "ask_design_spec": "design_spec",
            "ask_case": "case",
            "ask_manual": "manual",
            "ask_governance": "governance",
            "ask_feedback": "feedback",
        }.get(intent)
        if ktype:
            filters["knowledge_type"] = ktype
        # 抽取 CJK 单字以外的连续拉丁词作为候选标签（避免噪声，仅启发式）。
        import re

        latin_tags = re.findall(r"[a-z0-9]{3,}", (raw_query or "").lower())
        if latin_tags:
            filters["tags"] = sorted(set(latin_tags))
        return filters


__all__ = ["KnowledgeQuery", "KnowledgeQueryAgent"]
