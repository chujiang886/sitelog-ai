# Phase 3.8.23 收口报告 — Enterprise Agent Governance Knowledge Retrieval & Learning Assistance Layer（企业智能体治理知识检索与辅助学习层）

> 报告日期：2026-08-09
> 身份：BOIP AI Chief Architect
> 状态：**🟢 BUILT_NO_GO** — 构建完成，等待主理人审核授权；不进入 Phase 3.8.24。

---

## 1. 概述：阶段目标与范围

本阶段在 3.8.0–3.8.22 全 ✅ 的治理基座之上（含 3.8.22 已由**真实人工审核**沉淀的治理知识、治理案例与事实模式），建立 **Agent 治理知识检索与辅助学习层**。把既有治理事实按治理事件语境做**只读相似检索**，产出**辅助分析上下文**与**事实型辅助报告**，最终只能由**真实人工**决定怎么用：

```
治理事件 → 历史案例检索 → 知识匹配 → 辅助分析 → 人工使用
```

- 输入：3.8.22 `GovernanceImprovementWorkflowService` 已沉淀的治理案例（`GovernanceCase`）、事实模式（`GovernancePattern`）、**已人工采纳**的知识候选（`status==ACCEPTED` 且 `reviewed_by` 为真实 USER）；3.8.21 `GovernanceWorkflowService` 中**已由真实人工闭环**（`completed` + 真实 `closed_by`）的治理任务。
- 产出：可溯源的检索请求（`GovernanceKnowledgeQuery`）、来源可追溯的检索结果（`GovernanceKnowledgeRetrieval`）、确定性相似匹配候选（`GovernanceMatchCandidate` / `GovernanceSimilarityMatcher`）、只辅助分析的上下文（`GovernanceLearningContext`）、禁止建议的辅助报告（`GovernanceAssistanceReport`），以及统一入口 `GovernanceKnowledgeRetrievalService`。
- 边界：**AI 在本层只能「检索事实 → 摆候选 → 摆来源」，绝不改知识、绝不应用经验、绝不生成治理策略、绝不代替治理责任人**；本层对 3.8.21 / 3.8.22 数据**纯只读**。

---

## 2. 交付物清单（代码 + 测试 + 文档）

| 类型 | 路径 | 规模 |
|---|---|---|
| 治理知识检索核心（新建） | `agents/enterprise/agent_governance_knowledge_retrieval.py` | 1972 行，9 个导出符号（+1 内部 `_RETRIEVAL_FORBIDDEN` 禁名表） |
| 审计增强 | `agents/enterprise/audit.py` | +3 枚举（59→62）+ 3 个 `record_*` 方法 |
| 权限接入 / 聚合装配 | `agents/enterprise/service.py` + `agents/enterprise/__init__.py` | 注入 `agent_governance_knowledge_retrieval`，传 `knowledge_service=self.agent_governance_knowledge`、`governance_workflow=self.agent_governance_workflow` |
| 测试（新建，八类） | `tests/agents/test_enterprise_agent_governance_knowledge_retrieval.py` | 50 用例，8 类 |
| 历史测试修正（审计计数 59→62） | `test_enterprise_agent_governance_center.py` / `_knowledge.py` / `_workflow.py` / `_quality_governance.py` / `_runtime_policy.py` / `_security_risk.py` / `_compliance.py` / `_cost_resource.py` / `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py` | 各 `len(AuditActionCategory)==59` → `==62`；`EXPECTED_CATEGORIES` 补 3 成员 |
| 收口报告 | `.ai/reviews/phase3.8.23_agent_governance_knowledge_retrieval_report.md` | 本报告 |
| 状态刷新 | `.ai/project_status.json` | `phase_3_8_23_status=ENTERPRISE_AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL_BUILT_NO_GO` + 明细块 |
| 路线图 | `.ai/roadmap_v8.md` | §26 |

**9 个导出符号**：`GovernanceKnowledgeQuery` / `GovernanceMatchKind` / `GovernanceMatchCandidate` / `GovernanceKnowledgeRetrieval` / `GovernanceSimilarityMatcher` / `GovernanceLearningContext` / `GovernanceAssistanceReport` / `GovernanceRetrievalStage` / `GovernanceKnowledgeRetrievalService`。

---

## 3. 六条最高红线落实情况（fail-closed）

| # | 红线 | 落实方式 | 验证 |
|---|---|---|---|
| ① | `engineering_enabled` 保持 false | 所有构造/写路径断言 `safety_invariants_ok()`；测试 autouse fixture monkeypatch 注入 `False`，不碰磁盘 | `enabled=False`、`inv_ok=True` ✅ |
| ② | 不输出 `engineering_approved` | 全模块零真实输出；`engineering_approved` 仅作为禁名出现在 `_RETRIEVAL_FORBIDDEN` 与 docstring 禁令（负向引用） | grep 命中均为负向 ✅ |
| ③ | 禁 AI 自动修改知识 | `_RETRIEVAL_FORBIDDEN` 含 `auto_update_knowledge`/`auto_merge_knowledge`/`update_knowledge`/`write_knowledge` 等 26 个 knowledge 家族；结构级 `__getattr__` 拦截；`query_text`/`rationale`/`factual_summary` 命中 `_KNOWLEDGE_MUTATION_MARKERS` 即拒；本层对 3.8.22 知识纯只读 | 红线测试命中即抛 `EnterpriseRedLineViolationError` ✅ |
| ④ | 禁 AI 自动应用治理经验 | 含 `auto_apply_knowledge`/`auto_execute_knowledge`/`apply_knowledge`/`adopt_knowledge` 等 23 个 experience 家族；候选 `requires_human_use` 恒 `True`、置 False 即拒；阶段机无"已应用/已生效"终态 | ✅ |
| ⑤ | 禁 AI 自动生成治理策略 | 含 `auto_generate_policy`/`generate_policy`/`create_policy`/`promote_knowledge_to_policy` 等 25 个 policy 家族；`GovernanceMatchKind` 无 policy 类；`GovernanceAssistanceReport` 结构上无 recommendation/action/policy 字段 | ✅ |
| ⑥ | 禁 AI 代替治理责任人 | `mark_human_used` 强制 `require_human_actor(AuditActorKind.USER)`；`actor_id` 命中非人类即拒；审计禁 `record_human_approval`；辅助报告禁建议/责任判定语义（`_ADVICE_MARKERS`） | ✅ |

`_RETRIEVAL_FORBIDDEN` 共 **105 项**，覆盖基座 7 项 + ③/④/⑤/⑥ 四族；三层拦截：类型级（dataclass `__post_init__` 校验）+ 结构级（`_RedLineForbiddenMixin.__getattr__` 命中禁名即抛错）+ 语义级（`_reject_markers` / `_reject_non_human` / `_reject_retrieval_markers` / `_reject_advice_markers` 对内容做 `auto_*` / 非人类主语 / 策略动作 / 建议责任标记扫描）。

---

## 4. 关键设计：链路 · 确定性匹配 · 只给候选 · 只辅助分析

### 4.1 链路与阶段机
`GovernanceRetrievalStage` 五态：`QUERY_SUBMITTED → RETRIEVED → CONTEXT_BUILT → REPORT_READY → HUMAN_USED`。
- 仅**前进不回退**（`_ALLOWED_RETRIEVAL_TRANSITIONS`）；**唯一终态是 `HUMAN_USED`（人工使用）**，绝不存在"已应用/已生效"终态（红线④）。
- `submit_query`（AI 可代提，但 `user_id` 必真实 USER 且过权限/组织隔离）→ `retrieve`（只读汇编四类候选）→ `build_learning_context`（只辅助分析）→ `build_assistance_report`（禁建议）→ `mark_human_used`（`require_human_actor(USER)` 强制）。

### 4.2 确定性相似度，绝不调用 LLM（红线⑥）
- 匹配为**确定性词元重合度**（`_tokenize` 英文按非字母数字切分 + 中文按字切分；`_similarity` 为 Jaccard，0.0~1.0），**不调模型、不做语义推断、不编造相关性**，可复现可解释可复核。
- `match_cases` **刻意不把 `human_resolution` 纳入相似度**——只按"问题长得像不像"检索，避免变相给处置建议（测试 `test_matcher_does_not_use_human_resolution_for_similarity` 显式验证：用人工处置结论原文查询不命中，用问题原文查询命中）。
- `match_knowledge` 只收录 `status==ACCEPTED` 且 `reviewed_by` 为真实人类的候选；`find_related_events` 只收录 `completed` 且 `closed_by` 为真实人类的治理任务——未闭环/未采纳的"半成品"绝不拿来当经验检索。

### 4.3 只给候选、只辅助分析
- `GovernanceMatchCandidate.requires_human_use` 恒 `True`，置 False 即拒；`is_advisory_only` 恒 `True`。
- `GovernanceLearningContext.is_advisory_only` 恒 `True`，置 False 即拒；无来源链即拒；桶内只接受候选。
- `GovernanceAssistanceReport.contains_recommendation` 是**计算属性恒返回 False，不可被赋值伪造**（测试对其赋值抛 `AttributeError`/`TypeError`）；报告结构上无 `recommendation`/`action`/`policy` 字段（测试 `not in __dataclass_fields__` 验证）；`factual_summary` / `fact_lines` 过 `_ADVICE_MARKERS` + `_RETRIEVAL_MARKERS` 扫描，命中"建议/应当整改/应立即/判定责任/recommend"即拒生成（宁可不出报告也不越界）。

### 4.4 权限隔离与审计可溯
- 读路径 `_ensure_access` 复用 `AgentPermissionPolicy.check_agent_access`（默认拒绝）+ `IdentityService`；跨组织访问（`_ensure_org_scope`）一律抛 `EnterpriseIsolationError`；`KnowledgeVisibilityPolicy.can_read` 存在时默认拒绝（`_ensure_knowledge_visible`）。
- `audit.py` 新增 `AGENT_GOVERNANCE_KNOWLEDGE_QUERY` / `AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL` / `AGENT_GOVERNANCE_ASSISTANCE` 三类（累计 59→62），对应 `record_agent_governance_knowledge_query_action` / `record_agent_governance_knowledge_retrieval_action` / `record_agent_governance_assistance_action`；actor 如实（AI 发起默认 AI，人工使用节点强制 USER），**禁 `record_human_approval`**。

---

## 5. 测试结果与验证

- **新增八类测试 `test_enterprise_agent_governance_knowledge_retrieval.py`：50 用例全绿**（query 构造/权限隔离/语义拦截 · candidate/retrieval 来源可追溯 · matcher 确定性相似度只给候选 · learning_context 只辅助分析 · assistance_report 禁建议 · service 只读入口+人工使用 · 审计三类别 · `_RETRIEVAL_FORBIDDEN` 结构性拦截）。
- **全 agents 套件：`1952 passed / 0 failed`**（剔除历史阈值债文件后亦零回归；本次清洁运行连 2 个历史阈值债文件同跑亦全绿）。
  - 历史测试修正：10 个既有审计计数测试把 `len(AuditActionCategory)==59` 修正为 `==62`，`EXPECTED_CATEGORIES` 集合补 3 成员，与 3.8.22 的「56→59」修正同构。
- **红线状态核验**：`engineering_enabled=false`（`agents/config.yaml:102`）未变更、`safety_invariants_ok()=True`、无 `engineering_approved` 真实输出、审计无 `record_human_approval` 调用、无 `auto_*` 知识/经验/策略方法可调用。
- 未修改 `verified.json` / 不改 `engineering_enabled`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。

---

## 6. 已知限制 / 历史技术债

- **`test_threshold_migration.py` + `test_threshold_real_drill.py`（共 18 用例，`tests/` 下 `_tmp_drill_*.json` 临时文件）**：历史阈值债，成组跑时偶发顺序污染致雪崩式失败，**与 3.8.23 新增代码无关**；本次清洁运行（先删 `_tmp_drill_*`）已全绿。属历史债，建议单独 hygiene 修复，不阻塞本阶段收口。
- 检索层不持有任何"知识修改 / 经验应用 / 策略生成 / 责任判定 / 风险整改"能力，这些均留待真实治理责任人（USER）线下执行。
- `verified.json` 仍待主理人 + 专家线下提交真实证据后，由人类终端显式置 `engineering_enabled=true`。

---

## 7. 状态结论与下一步

- **状态：🟢 BUILT_NO_GO（2026-08-09）**：企业智能体治理知识检索与辅助学习层已完成 `GovernanceKnowledgeQuery` / `GovernanceMatchCandidate` / `GovernanceKnowledgeRetrieval` / `GovernanceSimilarityMatcher` / `GovernanceLearningContext` / `GovernanceAssistanceReport`(+`SourceTrace`) + `GovernanceKnowledgeRetrievalService` 的完整 fail-closed 检索辅助主线构建；审计累计 62 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改知识 / 应用经验 / 生成策略 / 代替治理责任人。
- 全层只检索与陈列既有事实、只由真实治理责任人逐步研判并使用；本层不产出任何治理结论、不修订任何策略、不分配任何责任、不整改任何风险、不关闭任何任务。

---

> **STOP（3.8.23 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.24**，等待主理人审核授权。
>
> **未完成（人工动作，pending_verification）**：真实治理知识检索与人工研判 / 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人 + 专家线下执行。本报告与状态刷新完成后停止。
