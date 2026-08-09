# Phase 3.8.24 收口报告 — Enterprise Agent Governance Knowledge Assistant Layer（企业智能体治理知识助手层）

> 报告日期：2026-08-09
> 身份：BOIP AI Chief Architect
> 状态：**🟢 BUILT_NO_GO** — 构建完成，等待主理人审核授权；不进入 Phase 3.8.25。

---

## 1. 概述：阶段目标与范围

本阶段在 3.8.0–3.8.23 全 ✅ 的治理基座之上（含 3.8.22 已由**真实人工审核**沉淀的治理知识、治理案例与事实模式，3.8.23 已建立的只读相似检索与辅助学习层），建立 **Agent 治理知识助手层**。把"用户提问"这一入口自然延伸为**问答型辅助**：在 3.8.23 检索引擎之上，把问题结构化、检索、攒上下文、产出**纯事实答案草稿**，最终只能由**真实人工**研判与采用：

```
用户问题 → 治理知识检索（复用 3.8.23）→ 案例/模式/知识/事件匹配 → 上下文构建 → 事实摘要 → 人工使用
```

- 输入：复用 3.8.23 `GovernanceSimilarityMatcher`（只读消费 3.8.22 已沉淀案例 / 模式 / **已人工采纳**知识候选 + 3.8.21 **已人工闭环**治理事件）。
- 产出：治理知识问题（`GovernanceAssistantQuery`）、只辅助分析的上下文（`GovernanceAssistantContext`）、纯事实答案草稿（`GovernanceAnswerDraft`，强制引用来源、禁建议）、真实人工确认节点（`GovernanceAssistantReview`），以及统一编排入口 `GovernanceAssistantAgent`。
- 边界：**AI 在本层只能「理解问题 → 检索事实 → 摆候选 → 摆来源 → 写事实摘要」，绝不改知识、绝不应用经验、绝不生成治理策略、绝不代替治理责任人、绝不自动确认答案**；本层对 3.8.21 / 3.8.22 / 3.8.23 数据**纯只读**。

---

## 2. 交付物清单（代码 + 测试 + 文档）

| 类型 | 路径 | 规模 |
|---|---|---|
| 治理知识助手核心（新建） | `agents/enterprise/agent_governance_knowledge_assistant.py` | ~910 行，8 个导出符号（+1 内部 `_ASSISTANT_FORBIDDEN` 禁名表，117 项） |
| 审计增强 | `agents/enterprise/audit.py` | +3 枚举（62→65）+ 3 个 `record_*` 方法 |
| 权限接入（注入） | `agents/enterprise/service.py` + `agents/enterprise/__init__.py`（沿用 3.8.23 装配，本层经 `agent_governance_knowledge_assistant` 暴露） | 注入 `GovernanceAssistantAgent` 入口 |
| 测试（新建，八类） | `tests/agents/test_enterprise_agent_governance_knowledge_assistant.py` | 43 用例，8 类 |
| 历史测试修正（审计计数 62→65） | `test_enterprise_agent_governance_center.py` / `_knowledge.py` / `_workflow.py` / `_quality_governance.py` / `_runtime_policy.py` / `_security_risk.py` / `_compliance.py` / `_cost_resource.py` / `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py` | 各 `len(AuditActionCategory)==62` → `==65`；`EXPECTED_CATEGORIES` 补 3 成员 |
| 收口报告 | `.ai/reviews/phase3.8.24_agent_governance_knowledge_assistant_report.md` | 本报告 |
| 状态刷新 | `.ai/project_status.json` | `phase_3_8_24_status=ENTERPRISE_AGENT_GOVERNANCE_ASSISTANT_BUILT_NO_GO` + 明细块 |
| 路线图 | `.ai/roadmap_v8.md` | §27 |

**8 个导出符号**：`GovernanceAssistantQuery` / `GovernanceAssistantContext` / `GovernanceAnswerDraft` / `AssistantReviewDecision` / `GovernanceAssistantReview` / `GovernanceAssistantStage` / `GovernanceAssistantAgent` / `_ASSISTANT_FORBIDDEN`。

---

## 3. 六条最高红线落实情况（fail-closed）

| # | 红线 | 落实方式 | 验证 |
|---|---|---|---|
| ① | `engineering_enabled` 保持 false | 所有写路径断言 `safety_invariants_ok()`；测试 autouse fixture monkeypatch 注入 `False`，不碰磁盘 | `enabled=False`、`inv_ok=True` ✅ |
| ② | 不输出 `engineering_approved` | 全模块零真实输出；`engineering_approved` 仅作为禁名出现在 `_ASSISTANT_FORBIDDEN` 与 docstring 禁令（负向引用）；类命名空间 `hasattr(GovernanceAssistantAgent, "engineering_approved")==False` | grep 命中均为负向 ✅ |
| ③ | 禁 AI 自动修改知识 | 复用 3.8.23 `_RETRIEVAL_FORBIDDEN` 的 knowledge 家族（`auto_update_knowledge`/`auto_merge_knowledge`/`update_knowledge`/`write_knowledge` 等）；结构级 `__getattr__` 拦截；`question`/`summary`/`facts` 命中 `_KNOWLEDGE_MUTATION_MARKERS` 即拒；本层对 3.8.22 知识纯只读 | 红线测试命中即抛 `EnterpriseRedLineViolationError` ✅ |
| ④ | 禁 AI 自动应用治理经验 | 复用 experience 家族（`auto_apply_knowledge`/`auto_execute_knowledge`/`apply_knowledge` 等）；候选 `requires_human_use` 恒 `True`；阶段机无"已应用/已生效"终态；答案草稿结构无应用动作字段 | ✅ |
| ⑤ | 禁 AI 自动生成治理策略 | 复用 policy 家族（`auto_generate_policy`/`generate_policy`/`recommend_policy`/`auto_recommend`/`promote_knowledge_to_policy` 等）；`GovernanceAnswerDraft` 结构上无 recommendation/action/policy 字段；`contains_recommendation` 计算属性恒 False 不可伪造 | ✅ |
| ⑥ | 禁 AI 代替治理责任人 | `confirm_answer` 强制 `require_human_actor(AuditActorKind.USER)`；`GovernanceAssistantReview` 构造即强制 `reviewer_kind==USER.value`；`actor_id` 命中非人类即拒；审计禁 `record_human_approval`；答案草稿禁建议/责任判定语义（`_ADVICE_MARKERS`） | ✅ |

`_ASSISTANT_FORBIDDEN` 共 **117 项** = 3.8.23 `_RETRIEVAL_FORBIDDEN`（105 项）+ 助手层专属 12 项（`auto_confirm`/`auto_answer`/`auto_generate_answer`/`auto_review_answer`/`auto_approve_answer`/`confirm_answer_automatically`/`answer_automatically`/`auto_conclude_answer`/`auto_decide_answer`/`assistant_approve` + 红线⑤补强 `recommend_policy`/`auto_recommend`）。三层拦截：类型级（dataclass `__post_init__` 校验）+ 结构级（`_RedLineForbiddenMixin.__getattr__` 命中禁名即抛错）+ 语义级（`_reject_markers` / `_reject_non_human` / `_reject_retrieval_markers` / `_reject_advice_markers`）。

---

## 4. 关键设计：问答链路 · 确定性匹配 · 只给候选 · 只辅助分析 · 人工确认

### 4.1 链路与阶段机
`GovernanceAssistantStage` 五态：`QUERY_UNDERSTOOD → CONTEXT_RETRIEVED → SUMMARY_BUILT → REVIEWED → HUMAN_USED`。
- 仅**前进不回退**（`_ALLOWED_ASSISTANT_TRANSITIONS`）；**唯一终态是 `HUMAN_USED`（人工使用）**，绝不存在"已应用/已生效"终态（红线④）。
- `submit_query`（AI 可代提，但 `user_id` 必真实 USER 且过权限/组织隔离）→ `understand_query`（只读结构化为 3.8.23 检索请求，复用其强校验）→ `retrieve_context`（复用 `GovernanceSimilarityMatcher` 攒上下文）→ `build_summary`（纯事实答案草稿，禁建议）→ `confirm_answer`（`require_human_actor(USER)` 强制真实人工确认）。
- 设计亮点：`retrieve_context` 在 `understand_query` 校验通过后对未 `submit_query` 登记的问题**惰性置 `QUERY_UNDERSTOOD`**，确保"必先 understood 才可 retrieved"（红线⑥），同时兼容直接调用检索的测试与编排场景。

### 4.2 确定性相似度，绝不调用 LLM（红线⑥）
- 匹配**复用 3.8.23 `GovernanceSimilarityMatcher`**：确定性词元重合度（`_tokenize` 英文按非字母数字切分 + 中文按字切分；`_similarity` 为 Jaccard，0.0~1.0），**不调模型、不做语义推断、不编造**，可复现可解释可复核。
- `match_cases` 刻意不把 `human_resolution` 纳入相似度；`match_knowledge` 只收录 `status==ACCEPTED` 且 `reviewed_by` 为真实人类的候选；`find_related_events` 只收录 `completed` 且 `closed_by` 为真实人类的治理任务。
- `GovernanceAssistantAgent._compute_confidence` 为**确定性**置信度（候选相似度均值 × 来源覆盖度），非模型判断、可复现。

### 4.3 只给候选、只辅助分析、只写事实摘要
- `GovernanceAssistantContext.is_advisory_only` 恒 `True`；无来源链即拒；桶内只接受 `GovernanceMatchCandidate`。
- `GovernanceAnswerDraft.requires_human_review` 恒 `True`；`contains_recommendation` 是**计算属性恒返回 False，不可被赋值伪造**；结构上无 `recommendation`/`action`/`policy` 字段；`facts`/`summary` 过 `_reject_retrieval_markers` + `_reject_advice_markers` 扫描，命中即拒生成（宁可不出草稿也不越界）；`references` 强制引用来源（案例 / 模式 / 知识 / 事件 + 来源链）。

### 4.4 权限隔离、人工确认节点与审计可溯
- 读路径 `_ensure_access` 复用 `AgentPermissionPolicy.check_agent_access`（默认拒绝）+ `IdentityService`；跨组织访问（`_ensure_org_scope`）一律抛 `EnterpriseIsolationError`；`KnowledgeVisibilityPolicy.can_read` 存在时默认拒绝（`_ensure_knowledge_visible`）。
- `GovernanceAssistantReview` 构造即强制 `reviewer_kind==AuditActorKind.USER.value`（红线⑥），无 approve/auto_approve/record_human_approval 方法；`confirm_answer` 调 `record_agent_governance_assistant_draft_action(action="human_confirm_assistant_answer", actor_kind=USER)`，强制 `require_human_actor(USER)`。
- `audit.py` 新增 `AGENT_GOVERNANCE_ASSISTANT_QUERY` / `AGENT_GOVERNANCE_ASSISTANT_CONTEXT` / `AGENT_GOVERNANCE_ASSISTANT_DRAFT` 三类（累计 62→65），对应 `record_agent_governance_assistant_query_action` / `record_agent_governance_assistant_context_action` / `record_agent_governance_assistant_draft_action`；actor 如实（AI 发起默认 AI，人工确认节点强制 USER），**禁 `record_human_approval`**。

---

## 5. 测试结果与验证

- **新增八类测试 `test_enterprise_agent_governance_knowledge_assistant.py`：43 用例全绿**（Query 构造/权限隔离/语义拦截 · Context 只辅助分析 · Agent 编排/事实摘要 · AnswerDraft 引用来源/禁建议 · Review 人工确认（红线②/⑥）· 权限接入默认拒绝/跨组织/可见性 · 审计增强 3 类+3 方法 · 六大红线整体 fail-closed）。
- **全 agents 套件：`1995 passed / 0 failed`**（清洁运行：先删 `_tmp_drill_*` 临时文件，零回归）。
  - 历史测试修正：10 个既有审计计数测试把 `len(AuditActionCategory)==62` 修正为 `==65`，`EXPECTED_CATEGORIES` 集合补 3 成员（3.8.24 新增），与历次相位「+3 计数」修正同构。
- **红线状态核验**：`engineering_enabled=false`（`agents/config.yaml:102`）未变更、`safety_invariants_ok()=True`、无 `engineering_approved` 真实输出、审计无 `record_human_approval` 调用、无 `auto_*` 知识/经验/策略/确认方法可调用（12 个代表性禁名全部被结构拦截）。
- 未修改 `verified.json` / 不改 `engineering_enabled`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。

---

## 6. 已知限制 / 历史技术债

- **`test_threshold_migration.py` + `test_threshold_real_drill.py`（共 18 用例，`tests/` 下 `_tmp_drill_*.json` 临时文件）**：历史阈值债，成组跑时偶发顺序污染致雪崩式失败，**与 3.8.24 新增代码无关**；本次清洁运行（先删 `_tmp_drill_*`）已全绿。属历史债，建议单独 hygiene 修复，不阻塞本阶段收口。
- 助手层不持有任何"知识修改 / 经验应用 / 策略生成 / 责任判定 / 风险整改 / 自动确认答案"能力，这些均留待真实治理责任人（USER）线下执行。
- `verified.json` 仍待主理人 + 专家线下提交真实证据后，由人类终端显式置 `engineering_enabled=true`。

---

## 7. 状态结论与下一步

- **状态：🟢 BUILT_NO_GO（2026-08-09）**：企业智能体治理知识助手层已完成 `GovernanceAssistantQuery` / `GovernanceAssistantContext` / `GovernanceAnswerDraft` / `GovernanceAssistantReview`(+`AssistantReviewDecision`) + `GovernanceAssistantAgent`（复用 3.8.23 `GovernanceSimilarityMatcher`）的完整 fail-closed 问答辅助主线构建；审计累计 65 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改知识 / 应用经验 / 生成策略 / 代替治理责任人 / 自动确认答案。
- 全层只理解问题、检索与陈列既有事实、只由真实治理责任人逐步研判并采用；本层不产出任何治理结论、不修订任何策略、不分配任何责任、不整改任何风险、不关闭任何任务、不确认任何答案。

---

> **STOP（3.8.24 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.25**，等待主理人审核授权。
>
> **未完成（人工动作，pending_verification）**：真实治理知识问答与人工研判 / 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人 + 专家线下执行。本报告与状态刷新完成后停止。
