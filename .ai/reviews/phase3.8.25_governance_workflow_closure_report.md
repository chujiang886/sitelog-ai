# Phase 3.8.25 企业智能体治理工作流编排层 —— 收口报告

> 状态：**BUILT_NO_GO（已收口，停等主理人审核）**
> 阶段：Phase 3.8.25 Enterprise Agent Governance Workflow Orchestration Layer
> 角色：企业智能体治理架构负责人（AI 执行，受六道 fail-closed 红线约束）
> 分支：`feat/phase3.8.25-governance-workflow`
> 配套前序：3.8.21 治理问责层（GovernanceWorkflowService）/ 3.8.24 治理知识助手层（GovernanceAssistantAgent）

---

## 1. 阶段目标

在 **3.8.24 治理知识助手**之上建立**编排层**，把治理链路

```
问题发现 → 事实辅助分析 → 人工研判 → 治理任务创建 → 执行跟踪 → 结果归档 → 审计闭环
```

串成一条**可追踪、可审计、AI 不可越权**的工作流流水线。

**最高原则（不可妥协）**：
- 禁止 AI 自动治理 / 审批 / 关闭问题 / 生成政策 / 修改知识；
- AI 只能理解、整理、关联、提醒、生成草稿；
- **所有治理动作必须真实人工确认**，并留痕审计。

本阶段**不进入 3.8.26**，收口即 STOP 等主理人审核。

---

## 2. 架构设计

```
                        ┌─────────────────────────────────────────────┐
                        │   EnterpriseOperationLayer（既有门面）        │
                        │   · 构造期断言 safety_invariants_ok()          │
                        │   · engineering_enabled 恒 False（红线①）      │
                        └───────────────┬─────────────────────────────┘
                                        │ 注入 审计/身份/可见性/权限策略
                  ┌─────────────────────┼─────────────────────────────┐
                  ▼                     ▼                             ▼
       3.8.24 治理知识助手      3.8.21 治理问责层            3.8.25 治理工作流编排层（本阶段新增）
   GovernanceAssistantAgent  GovernanceWorkflowService     GovernanceWorkflowOrchestrator
   （事实草稿 / 来源引用）      （五态：created→assigned→    （六态：created→under_review→
   requires_human_review=True） processing→waiting_review→   human_confirmed→in_progress→
                                completed）                   waiting_result→completed）
                                  ▲ 人工治理任务真实落点        │ derive_task 派生（人工 actor）
                                  └────────────────────────────┘
```

**核心组件**：`GovernanceWorkflowOrchestrator(_RedLineForbiddenMixin)`，位于
`agents/enterprise/governance_workflow/orchestrator.py`。

**复用关系（不重建，只串联）**：
- **3.8.21 `GovernanceWorkflowService`**：人工治理任务的真实落点。`human_confirm` 在 `decision=CONFIRMED` 时可 `derive_task` 派生一条 3.8.21 治理任务，其 `actor` 仍是真实人工（reviewer_id），**不越权**（红线④）。
- **3.8.24 `GovernanceAssistantAgent`**：事实草稿来源。`create_from_answer_draft` 校验 `requires_human_review is True`。
- **既有治理基础设施**：`AuditService` / `IdentityService` / `KnowledgeVisibilityPolicy` / `AgentPermissionPolicy`，与 3.8.21 共用同一审计实例与隔离策略（默认拒绝）。

**命名决策（用户 D1）**：编排器命名为 `GovernanceWorkflowOrchestrator`，与 3.8.21 的 `GovernanceWorkflowService` 语义明确区分，避免混淆。两者**并存、互不覆盖**。

**接线范围（用户 D2）**：本次一并把 3.8.24 治理知识助手接入 `EnterpriseOperationLayer`（`service.py:591`），与 3.8.25 编排器（`service.py:602`）一同完成门面装配。

---

## 3. 状态机设计

**六态（仅前进，无回退）**：

```
CREATED ──submit_for_review──▶ UNDER_REVIEW
   │                               │
   │ (AI 可登记候选/推送队列)        │ human_confirm(CONFIRMED, USER)
   │                               ▼
   │                         HUMAN_CONFIRMED
   │                               │ start_execution(USER)
   │                               ▼
   │                         IN_PROGRESS
   │                               │ submit_execution_result(USER)
   │                               ▼
   │                         WAITING_RESULT
   │                               │ human_complete(USER)
   │                               ▼
   │                         COMPLETED ──archive(USER)──▶ archived=True
```

**红线约束**：
- **无 `AUTO_APPROVED` / `AUTO_EXECUTED` / `AUTO_CLOSED` 态**（红线③/④/⑥ 落到类型级 + 结构级 + 语义级三重）。
- `_ALLOWED_WORKFLOW_TRANSITIONS` 仅定义**前进**迁移；非法迁移（`CREATED→HUMAN_CONFIRMED` 等）直接拒绝。
- 终态 `COMPLETED` 不可再转；`REJECTED` / `NEED_MORE_INFO` 不前进（仅 `CONFIRMED` 推进）。
- `human_confirm` 状态推进**强制 `require_human_actor(USER)`**；`reviewer_kind` 非 USER 即抛 `EnterpriseRedLineViolationError`。

---

## 4. 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `agents/enterprise/governance_workflow/orchestrator.py` | 570 | **核心新增**。编排器 `GovernanceWorkflowOrchestrator(_RedLineForbiddenMixin)`，含 18 个方法：注册候选、从草稿创建、推送研判、人工确认、开始执行、提交结果、人工完成、追加备注、归档、派生任务、四类查询，及 `_ensure_org_scope` / `_ensure_access` 隔离闸门、`_record_execution_audit` 审计封装。 |
| `tests/agents/test_enterprise_agent_governance_workflow_orchestrator.py` | 20 用例 | **核心新增**。覆盖创建 / 状态转换（合法链→COMPLETED+archived / 非法迁移拒绝 / 终态不可转 / rejected 不前进）/ 跨组织隔离 / AI 调 human_confirm·start_execution·submit_execution_result 均被拦 / derive_task / 审计（3 类类别 + actor_kind=USER）/ 禁名结构拦截（auto_approve·auto_execute·auto_close_workflow·generate_policy·decide_workflow）/ 无 AUTO 态。 |

**关联脚手架（前序已就位，本次仅读取契约、未改动）**：
- `agents/enterprise/governance_workflow/forbidden.py`（增量合并 3.8.21 禁名）
- `agents/enterprise/governance_workflow/models.py`（6 类模型 + 六态枚举 + 迁移表）
- `agents/enterprise/audit.py`（3 个包装方法：`record_agent_governance_workflow_create/review/execution_action`）
- `agents/enterprise/agent_governance_workflow.py`（3.8.21 问责层，作为 `derive_task` 落点）

---

## 5. 修改文件

| 文件 | 修改点 |
|------|--------|
| `agents/enterprise/service.py` | 在 3.8.23 实例化之后、`is_activation_safe` 之前新增：(a) 3.8.24 `self.agent_governance_knowledge_assistant = GovernanceAssistantAgent(...)`（用户 D2，一并补接）；(b) 3.8.25 `self.agent_governance_workflow_orchestrator = GovernanceWorkflowOrchestrator(..., assistant=self.agent_governance_knowledge_assistant)`。导入块同步新增 3.8.24 + 3.8.25 符号。 |
| `agents/enterprise/__init__.py` | 导入并导出 3.8.24（`GovernanceAssistantAgent` / `GovernanceAnswerDraft` / `GovernanceAssistantQuery` / `GovernanceAssistantContext` / `GovernanceAssistantReview` / `GovernanceAssistantStage`）+ 3.8.25（`GovernanceWorkflowSourceType` / `GovernanceWorkflowStatus` / `GovernanceWorkflow` / `WorkflowReviewDecision` / `GovernanceWorkflowReview` / `GovernanceExecutionRecord` / `GovernanceWorkflowOrchestrator`）。 |
| `tests/agents/test_enterprise_*.py`（10 个） | 审计枚举真实数量已确认为 **68**，将陈旧 `== 65` 断言同步为 `== 68`。涉及：quality_governance / governance_center / knowledge_intelligence_audit / compliance / governance_workflow / cost_resource / knowledge_governance_audit / security_risk / runtime_policy / governance_knowledge。 |
| `tests/agents/test_enterprise_knowledge_governance_audit.py` | `EXPECTED_CATEGORIES` 增量 +3 条 3.8.25 类别（`agent_governance_workflow_create` / `_review` / `_execution`），与 `len(members) == 68` 对齐。 |

> 审计枚举真实成员数：**68**（3.8.25 贡献 3 个：`AGENT_GOVERNANCE_WORKFLOW_CREATE` / `REVIEW` / `EXECUTION` + 3 个包装方法）。

---

## 6. Git Commit 列表（待主理人审核后执行）

> 仓库异常：BOIP 根 `.git` 当前仅跟踪 `.ai/` 文档（约 282 文件），**整个 `agents/` Python 树未跟踪**。
> **纪律**：精确 `git add` 仅提交 3.8.25 范畴文件，**绝不 `git add -A`**，不补提交整个未跟踪 `agents/` 树（避免污染历史、绕过 review）。

计划提交（单一逻辑提交，独立 commit）：
```
agents/enterprise/governance_workflow/orchestrator.py
agents/enterprise/service.py
agents/enterprise/__init__.py
tests/agents/test_enterprise_agent_governance_workflow_orchestrator.py
tests/agents/test_enterprise_agent_quality_governance.py
tests/agents/test_enterprise_agent_governance_center.py
tests/agents/test_enterprise_knowledge_intelligence_audit.py
tests/agents/test_enterprise_agent_compliance.py
tests/agents/test_enterprise_agent_governance_workflow.py
tests/agents/test_enterprise_agent_cost_resource.py
tests/agents/test_enterprise_knowledge_governance_audit.py
tests/agents/test_enterprise_agent_security_risk.py
tests/agents/test_enterprise_agent_runtime_policy.py
tests/agents/test_enterprise_agent_governance_knowledge.py
.ai/reviews/phase3.8.25_governance_workflow_closure_report.md
```

提交信息（建议）：
```
feat(governance): Phase 3.8.25 企业智能体治理工作流编排层（BUILT_NO_GO，停等审核）

- 新增 GovernanceWorkflowOrchestrator（六态机 + 六道 fail-closed 红线）
- 串联 3.8.21 问责层 / 3.8.24 知识助手，形成治理闭环流水线
- 一并补接 3.8.24 GovernanceAssistantAgent 至 EnterpriseOperationLayer
- 同步审计枚举计数 65→68（10 测试 + 1 set 测试）
- 严格精确 git add，未触碰未跟踪 agents 树
```

---

## 7. 测试结果

| 范围 | 命令 | 结果 |
|------|------|------|
| 3.8.25 新套件 | `pytest tests/agents/test_enterprise_agent_governance_workflow_orchestrator.py` | **20 passed** |
| 全量回归（排除 threshold 雪崩 4 文件） | `pytest tests/agents`（忽略 `test_*threshold*` 4 文件） | **1973 passed, 0 failed** |
| 枚举计数同步校验 | 10 个 `== 65 → == 68` + `EXPECTED_CATEGORIES` +3 | 全绿 |

> 说明：`tests/agents` 下 4 个 `test_*threshold*` 文件为历史技术债（扫描 `tests/` 读取 `_tmp_drill_*.json` 引发雪崩式失败），与本次变更无关，已排除。清理命令：`find tests -name '_tmp_drill_*' -delete; rm -rf tests/intake_snapshots`。

---

## 8. 安全红线验证（fail-closed）

| # | 红线 | 验证方式 | 结果 |
|---|------|----------|------|
| ① | `engineering_enabled` 恒 False | `autouse` fixture 锁 `load_engineering_enabled→False`（不碰磁盘）；门面构造经 `safety_invariants_ok()` | ✅ 拦截 |
| ② | 不输出 `engineering_approved` | 结构级禁名拦截（`_FORBIDDEN` 含相关禁名） | ✅ 拦截 |
| ③ | 禁 AI 自动治理/审批/关闭 | 前进转移全部 `require_human_actor`；非法迁移（`CREATED→HUMAN_CONFIRMED` 等）拒绝；终态不可转；无 AUTO 态 | ✅ 拒绝 |
| ④ | 禁 AI 自动执行 | `start_execution` / `submit_execution_result` 强制 `require_human_actor(USER)`；`GovernanceExecutionRecord.actor_kind` 固化字面 `"user"`（枚举会被 `str()` 转坏，已规避） | ✅ 拦截 |
| ⑤ | 禁 AI 自动生成政策/改知识 | 六组语义扫描（`_reject_all_markers`）落入 `forbidden.py` + `models.py` | ✅ 拦截 |
| ⑥ | 禁 AI 代替责任人 | `human_confirm` / `start_execution` / `submit_execution_result` / `human_complete` / `archive` 全部 `require_human_actor(USER)` + 审计 `actor_kind=USER` | ✅ 拦截 |

**禁名规模**：`_WORKFLOW_FORBIDDEN = 166`（增量 `_ORCHESTRATION_FORBIDDEN = 68`，合并自 `_GOVERNANCE_FORBIDDEN = 98`）。

**测试显式覆盖**：AI 调用 `human_confirm`·`start_execution`·`submit_execution_result` 均被拦；禁名结构拦截（`auto_approve` / `auto_execute` / `auto_close_workflow` / `generate_policy` / `decide_workflow`）；状态机无 `AUTO` 态；跨组织 `EnterpriseIsolationError`。

---

## 9. 当前能力

编排器已具备以下端到端能力（全部 fail-closed）：

1. **登记候选**：`register_candidate`（AI 发起，落 `CREATED`，如实记 `actor_id=ai`，不伪装人工）。
2. **从助手草稿创建**：`create_from_answer_draft`，校验 `requires_human_review is True` 且可溯源 `answer_id`。
3. **推送研判**：`submit_for_review`（`CREATED→UNDER_REVIEW`，AI 可推送，不构成决定，审计 `actor_kind=AI`）。
4. **人工研判确认**：`human_confirm`（`UNDER_REVIEW→HUMAN_CONFIRMED`，强制 USER + 审计；可选 `derive_task` 派生 3.8.21 任务，actor 仍为人工）。
5. **执行跟踪**：`start_execution` / `submit_execution_result`（强制 USER + 执行记录 + 审计）。
6. **完成与归档**：`human_complete` / `archive`（仅 `COMPLETED` 态可归档，全程 USER + 审计）。
7. **查询与隔离**：`get_workflow` / `list_workflows`（按 org 过滤）/ `get_reviews` / `get_execution_records`；`_ensure_org_scope` 跨 org 抛 `EnterpriseIsolationError`；`_ensure_access` 默认拒绝。

---

## 10. 已知限制

- **编排而非新增能力**：本层纯串联，不新增治理知识/政策能力；知识沉淀仍走 3.8.22/3.8.23/3.8.24。
- **内存态**：编排器工作流存于 `_workflows` dict，**未接持久化/DB**（与既有 agents 内存实现一致），进程重启丢失。
- **derive_task 触发条件**：仅 `human_confirm(decision=CONFIRMED, derive_task=True)` 时派生 3.8.21 任务；落点任务 `actor` 为真实人工 `reviewer_id`。
- **审计默认 actor**：`audit.py` 包装方法默认 `actor_kind=AI`；编排器对人工动作显式传 `USER`（已验证 `actor_kind=USER`）。
- **仓库跟踪异常**：`agents/` 整树未被 git 跟踪（仅 `.ai/` 文档 282 文件被跟踪）。本次精确提交仅 3.8.25 范畴文件，**不补提交整个未跟踪 `agents/` 树**（避免污染历史 / 绕过 review）。
- **threshold 雪崩债**：4 个 `test_*threshold*` 为历史技术债，与本次无关，已排除在回归外。

---

## 11. 下一阶段建议（待主理人审核通过后）

1. **Phase 3.8.26（建议，未启动）**：将编排层接入前端治理驾驶舱，与 3.8.20 治理中枢仪表盘联动，提供人工确认 / 执行 UI 入口。
2. **持久化**：编排器工作流态接入 SQLAlchemy / Alembic（与既有 agents 持久化方案对齐），消除重启丢失。
3. **跨层审计溯源**：统一 3.8.21 问责层与 3.8.25 编排层的 id 空间与审计串联，支持端到端溯源。
4. **3.8.24 接线收尾**：本阶段已一并补接 3.8.24 至门面，建议单独为 3.8.24 补一份收口说明（如尚未有）。
5. **当前纪律**：收口即 **STOP**，不进入 3.8.26，等待主理人 + 专家线下提交真实证据后，由人类终端显式置 `engineering_enabled=true`。

---

**收口结论**：Phase 3.8.25 企业智能体治理工作流编排层已交付（BUILT_NO_GO），18 方法编排器 + 20 用例测试全绿，六道 fail-closed 红线逐项验证通过，审计枚举计数与脚手架同步。**停等主理人审核，不进 3.8.26。**
