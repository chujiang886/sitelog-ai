# Phase 3.8.12 收口报告 —— Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer（企业知识任务规划与多智能体工作流层）

- **状态**：`ENTERPRISE_KNOWLEDGE_TASK_PLANNING_BUILT_NO_GO`（已构建，未进入启用态）
- **工程开关**：`engineering_enabled = false`（fail-closed，红线①）
- **收口结论**：✅ 全部 11 项任务交付；✅ 全量 agents 测试 **1374 passed**（基线 1335 + 39 新增），零回归；✅ 六条最高红线守约。
- **下一步**：**STOP，不进入 Phase 3.8.13；等待主理人审核。**

---

## 1. 阶段目标

Phase 3.8.12 在 3.8.0~3.8.11 企业知识层基座之上，新增「企业知识任务规划与多智能体工作流层」，建立复杂企业知识任务的可规划、可编排、可人工兜底能力。

设计主线（用户问题 → 任务拆解 → Agent 规划 → 知识调用 → 结果汇总 → 人工审核）：

1. 用户发起一次知识任务（`KnowledgeTask`），携带目标 `goal` 与归属会话/用户。
2. 任务规划器（`KnowledgeTaskPlanner`）**只拆任务、不执行决策**：`analyze_goal` 理解复杂度 → `create_plan` 生成步骤与子任务规格 → `split_subtasks` 拆出 `retrieval / validation / analysis / draft` 四类 Agent 子任务。
3. 子任务（`KnowledgeSubTask`）承载各 Agent 的中间执行态（输入/输出/状态），**绝不自动落地知识**。
4. 多智能体编排器（`KnowledgeTaskOrchestrator`）复用 3.8.10 的 Query/Retrieve/Validate/Answer 四个 AI 智能体，串起完整闭环，**只协调不审批**。
5. 人工复核检查点（`TaskReviewCheckpoint`）强制复杂任务最终输出 `requires_human_review=True`，**禁止 AI 自动完成最终任务**（红线⑥）。
6. 所有 Task/SubTask/AgentEvent 如实接入 `AuditService`（新增 `KNOWLEDGE_TASK` / `KNOWLEDGE_SUBTASK` / `KNOWLEDGE_AGENT_WORKFLOW` 三类）。
7. 任务接入 `IdentityService` + `KnowledgeVisibilityPolicy`，只能访问授权知识（任务7）。

---

## 2. 架构设计

```
用户(USER)
   │  create(task_id, conversation_id, user_id, goal)        [USER 审计]
   ▼
KnowledgeTaskService  ── org_id 绑定 / 访问隔离(本人|ADMIN)
   │  update_plan(steps)  [只拆解不决策]
   ▼
KnowledgeTaskPlanner (AI 规划器)
   │  analyze_goal() → create_plan() → split_subtasks()
   │  • 复杂任务 requires_human_review=True
   │  • retrieval 子任务携带 allowed_knowledge_types（按角色可见性约束传播）
   ▼
KnowledgeTaskOrchestrator (只协调不审批)
   │  plan → query(KnowledgeQueryAgent)
   │       → retrieve(KnowledgeRetrievalAgent, 按角色过滤)
   │       → validate(KnowledgeValidationAgent, 四维校验)
   │       → [analyze 内部结构化分析]
   │       → draft(KnowledgeAnswerAgent, 须引用来源)
   │  • 每个子任务记入 KnowledgeSubTask（retrieval/validation/analysis/draft）
   │  • 全程写入 task_workflow_event_log
   ▼
TaskReviewCheckpoint (任务5/红线⑥)
   │  • 复杂任务 requires_human_review 必须 True（否则拒绝 AI 自动收口）
   │  • 任务进入 waiting_review（绝不自动 completed）
   │  • finalize_by_human() 必须真实 USER（require_human_actor 守卫）
   ▼
AuditService: KNOWLEDGE_TASK / KNOWLEDGE_SUBTASK / KNOWLEDGE_AGENT_WORKFLOW
   │  • actor 真实（任务由 USER 发起→USER；子任务/工作流由 AI 编排→AI）
   │  • 无 record_human_approval（绝不伪造人工审批）
   ▼
人工审核（最终采用须经真实 USER；红线⑥）
```

`EnterpriseOperationLayer` 聚合 `knowledge_task_planner` / `knowledge_tasks` / `knowledge_subtasks` / `knowledge_task_orchestrator` / `task_review_checkpoint`，与既有企业层服务共享同一 `audit` / `identity` / `knowledge_visibility` 实例，并保证编排器、检查点复用同一 `task_service` / `subtask_service` / `planner` 实例以维持状态一致。

---

## 3. 任务完成情况（11 项）

| # | 任务 | 交付 | 状态 |
| --- | --- | --- | --- |
| 1 | KnowledgeTask 模型 | `knowledge_task.py`：`KnowledgeTaskStatus`(created/planning/executing/waiting_review/completed) / `KnowledgeTask` / `KnowledgeTaskService` | ✅ |
| 2 | TaskPlanner Agent | `knowledge_task_planner.py`：`analyze_goal` / `create_plan` / `split_subtasks`（只拆不决策） | ✅ |
| 3 | SubAgent 任务模型 | `knowledge_subtask.py`：`KnowledgeSubTaskType`(retrieval/validation/analysis/draft) / `KnowledgeSubTask` / `KnowledgeSubTaskService` | ✅ |
| 4 | Multi-Agent Workflow | `knowledge_task_orchestrator.py`：`KnowledgeTaskOrchestrator` 复用 3.8.10 四智能体，只协调不审批 | ✅ |
| 5 | Human Review Checkpoint | `task_review_checkpoint.py`：`checkpoint`（复杂任务强制待复核）/ `finalize_by_human`（仅真实 USER） | ✅ |
| 6 | 来源和审计 | `audit.py` +3 类别（累计 29）+ 3 个 `record_*` 方法；所有 Task/SubTask/AgentEvent 如实记录 source/actor/timestamp | ✅ |
| 7 | 权限接入 | 任务接入 `IdentityService` + `KnowledgeVisibilityPolicy`；访问隔离（本人\|ADMIN）；检索按角色过滤；规划器传播 `allowed_knowledge_types` | ✅ |
| 8 | 测试 | `test_enterprise_knowledge_task_planning.py` 八类（task/planner/subtask/orchestrator/checkpoint/audit/permission/red line），不修改 `verified.json` / `engineering_enabled` | ✅ |
| 9 | 最终验证 | 全 agents 套件 `pytest tests/agents -q` 全通过；`engineering_enabled=false`；无 `engineering_approved` | ✅ |
| 10 | 收口报告 | 本报告（7 节） | ✅ |
| 11 | 状态更新 | `project_status.json` + `phase_3_8_12_status` + `roadmap_v8.md` §15；完成后 STOP | ✅ |

---

## 4. 代码文件清单

### 4.1 新建文件

| 文件 | 内容 |
| --- | --- |
| `agents/enterprise/knowledge_task.py` | 任务1：`KnowledgeTaskStatus` / `KnowledgeTask` / `KnowledgeTaskService`（创建 / 读取 / 列举本人 / 规划写入 / 状态推进；组织隔离；访问隔离；`advance_status(COMPLETED)` 必经 `require_human_actor`） |
| `agents/enterprise/knowledge_task_planner.py` | 任务2：`GoalAnalysis` / `SubTaskSpec` / `TaskPlan` / `KnowledgeTaskPlanner`（`analyze_goal` / `create_plan` / `split_subtasks`；只拆任务不决策；复杂任务 `requires_human_review=True`；按角色约束可见知识类型） |
| `agents/enterprise/knowledge_subtask.py` | 任务3：`KnowledgeSubTaskType` / `KnowledgeSubTaskStatus` / `KnowledgeSubTask` / `KnowledgeSubTaskService`（拆解创建 / 完成 / 列举 / 读取；组织隔离；产出仅候选） |
| `agents/enterprise/knowledge_task_orchestrator.py` | 任务4：`KnowledgeTaskWorkflowEvent` / `KnowledgeTaskOrchestrator`（复用 3.8.10 四智能体；plan→query→retrieve→validate→[analyze]→draft；只协调不审批；任务进入 `waiting_review`） |
| `agents/enterprise/task_review_checkpoint.py` | 任务5：`TaskReviewCheckpoint`（复杂任务 `requires_human_review` 强制；`finalize_by_human` 必经 `require_human_actor(USER)`） |

### 4.2 修改文件

| 文件 | 变更 |
| --- | --- |
| `agents/enterprise/audit.py` | 任务6：新增 3 个审计类别 `KNOWLEDGE_TASK` / `KNOWLEDGE_SUBTASK` / `KNOWLEDGE_AGENT_WORKFLOW`（累计 **29**）；新增 `record_knowledge_task_action` / `record_knowledge_subtask_action` / `record_knowledge_agent_workflow_action`（actor 真实，无 `record_human_approval`） |
| `agents/enterprise/service.py` | 任务7/6：在 `EnterpriseOperationLayer.__init__` 装配 5 个新服务，共享 `self.audit` / `self.identity` / `self.knowledge_visibility`；编排器/检查点复用同一 `task_service` / `subtask_service` / `planner` 实例 |
| `agents/enterprise/__init__.py` | 任务6：新增 3.8.12 import 段与 `__all__` 导出 |
| `tests/agents/test_enterprise_knowledge_task_planning.py` | 任务8：八类共 **18** 个用例（task 2 / planner 4 / subtask 1 / orchestrator 2 / checkpoint 2 / audit 1 / permission 2 / red line 4） |
| `tests/agents/test_enterprise_knowledge_governance_audit.py` | 任务6/8：`EXPECTED_CATEGORIES` 同步至 29 + `assert len(members)==29` + 3 个 record 测试（hasattr 循环改为程序化 `AuditActionCategory.__members__` 迭代，规避 3.8.11 形近污染） |
| `tests/agents/test_enterprise_knowledge_intelligence_audit.py` | 任务6/8：同步总数断言 26 → 29 |

---

## 5. 测试结果

- **全量 agents 套件**：`1374 passed`（基线 1335 + 39 新增），0 失败，约 34s。
- **本层新增用例分布（八类）**：
  - task 模型：`test_task_create_get_list_update_plan`、`test_task_org_isolation`
  - planner：`test_planner_analyze_goal_complex`、`test_planner_analyze_goal_simple`、`test_planner_create_plan_subtask_order_and_review_flag`、`test_planner_simple_plan_no_review_required`
  - subtask 模型：`test_subtask_create_complete_list`
  - orchestrator：`test_orchestrator_run_task_complex`、`test_orchestrator_run_task_simple`
  - checkpoint：`test_checkpoint_complex_requires_review`、`test_checkpoint_finalize_requires_human`
  - 审计（任务6）：`test_audit_records_for_task_workflow`
  - 权限接入（任务7）：`test_task_access_isolation`、`test_planner_role_visibility_constraint`
  - 红线（任务8 验证）：`test_red_line_forbidden_methods_intercepted`、`test_red_line_safety_invariants_ok`、`test_red_line_ai_cannot_auto_complete_task`、`test_no_engineering_approved_attribute`
- **审计计数测试修正**：治理审计 `assert len(members)==29` + `EXPECTED_CATEGORIES` 同步（程序化生成，无手抄长枚举名）；智能审计 `assert len(list(AuditActionCategory))==29`。
- **未修改** `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；无 `engineering_approved`。

---

## 6. 六大红线验证（fail-closed）

| # | 红线 | 本层落实 | 核验结果 |
| --- | --- | --- | --- |
| ① | 保持 `engineering_enabled=false` | 所有服务构造/写路径断言 `safety_invariants_ok()`；配置保持 `false` | ✅ `load_engineering_enabled()=False` |
| ② | 不输出 `engineering_approved` | 5 个新服务 `_FORBIDDEN` 含 `engineering_approved`；访问该属性抛 `EnterpriseRedLineViolationError` | ✅ 无输出路径（`"engineering_approved" not in Service.__dict__`） |
| ③ | 禁止 AI 自动修改/合并/发布/应用知识 | 各服务 `_FORBIDDEN` 含 `auto_update_knowledge` / `auto_merge_knowledge` / `auto_publish_knowledge` / `auto_apply_knowledge` / `commit` / `write` 等 | ✅ 无自动写知识路径 |
| ④ | 禁止 AI 自动生成工程结论 | 各服务 `_FORBIDDEN` 含 `generate_engineering_conclusion` / `decide` / `auto_decision` 等；编排器只协调不审批 | ✅ 无自动结论路径 |
| ⑤ | 无自动审批 | `AuditService` 无 `record_human_approval`；`advance_status(COMPLETED)` / `finalize_by_human` 必经 `require_human_actor(USER)` | ✅ |
| ⑥ | AI 不代替人工责任 | 任务最终 `completed` 必经真实 USER；复杂任务 `requires_human_review=True` 强制；编排器绝不自动 completed；审计 actor 真实、无 `record_human_approval` | ✅ |

- **审计枚举数量**：`len(AuditActionCategory) == 29`（3.8.11 为 26，本层 +3）。
- **无 `record_human_approval` 方法**：`"record_human_approval" not in AuditService.__dict__` ✅。
- **组织隔离**：跨域访问抛 `EnterpriseIsolationError`；越权访问抛 `EnterpriseRedLineViolationError`。
- **AI 不得自动完成最终任务**：`KnowledgeTaskService.advance_status(COMPLETED, actor_kind=AI)` 抛 `EnterpriseRedLineViolationError`（已由 `test_red_line_ai_cannot_auto_complete_task` 验证）。

---

## 7. 激活状态声明

- **`engineering_enabled = false`**（未变更，fail-closed 红线①）：所有真实工程参数 / 尺寸确认 / 报价 / 代签路径保持 fail-closed；激活须经主理人 + 专家线下提交真实证据后由人类终端显式置 `enabled=true`。
- **本层只承载「任务规划与多智能体工作流编排」**：编排器/检查点/规划器**绝不**自动写知识库、绝不自动生成工程结论、绝不自动审批、绝不 AI 代责（红线③/④/⑤/⑥）；最终采用须经真实 USER。
- **`AuditActionCategory`**：累计 29（3.8.12 +3）。
- **`project_status.json`**：新增 `phase_3_8_12_status = ENTERPRISE_KNOWLEDGE_TASK_PLANNING_BUILT_NO_GO`；`phase` 推进至 `3.8.12`（更新见 `roadmap_v8.md` §15）。
- **下一步**：**STOP。不进入 Phase 3.8.13。等待主理人审核。**

---

*报告生成：BOIP AI Chief Architect · 2026-08-06*
