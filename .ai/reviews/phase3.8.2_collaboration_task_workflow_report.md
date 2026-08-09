# BOIP Phase 3.8.2 —— Enterprise Collaboration & Task Workflow Layer（企业协作与任务工作流层）收口报告

- **范围**：Phase 3.8.2（企业协作与任务工作流层）
- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-04
- **状态**：`ENTERPRISE_COLLAB_BUILT_NO_GO`
- **前置**：Phase 3.7 ✅ Engineering Intelligence Complete；Phase 3.8.0 ✅ Enterprise Operation Layer；Phase 3.8.1 ✅ Enterprise Access & Permission Intelligence

---

## 0. 红线总闸（6 条，fail-closed，全部保持）

| # | 红线 | 本层落地 |
|---|------|----------|
| ① | 禁止开启 `engineering_enabled` | 所有新服务构造/写路径首行断言 `safety_invariants_ok()`；启用态（伪造 `True`）构造即抛 `EnterpriseRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | 新服务不含 `approve` / `engineering_approved`；`TaskWorkflowService`/`NotificationService` 经 `_RedLineForbiddenMixin` 结构性拦截 |
| ③ | 禁止自动报价 | 新服务不含 `quote` / `pricing` |
| ④ | 禁止自动审批 | 新服务不含 `approve` / `sign` / `authorize`（`mixin` 拦截） |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | 以 `safety_invariants_ok()` 作为统一前置护栏（只读 `load_engineering_enabled()`） |
| ⑥ | 禁止 AI 代替人工决策 | `AuditService` 仍禁止 `record_human_approval`；`TaskWorkflow.record_review_result` 强制传入真实 `reviewer_id`（human），系统不提供 `approve`；`NotificationService` 结构性拦截 `notify_human_approval` / `forge_approval` 伪造人工审批通知 |

**结果**：全 agents 套件 **880 → 917 passed（+37）零回归**；未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`（config.yaml:102）；未输出 `engineering_approved`。

---

## 1. 任务1：任务模型（`agents/enterprise/task.py`，NEW）

- 新增 `TaskStatus`（CREATED/ASSIGNED/PROCESSING/WAITING_REVIEW/COMPLETED，与工作流状态机对齐）、`TaskPriority`（LOW/MEDIUM/HIGH/URGENT）。
- 新增 `Task` dataclass，字段严格对应指令：`task_id` / `project_id` / `assignee_id` / `creator_id` / `status` / `priority` / `due_date` / `created_at`，并强制 `org_id`（组织隔离）。
- 新增 `TaskService(org_id, audit=None)`：`create_task` / `assign` / `update_status` / `get` / `list_tasks`。
  - 构造与写路径首行 `safety_invariants_ok()` 断言（红线①/⑤）。
  - 跨域访问（org 不一致）抛 `EnterpriseIsolationError`（组织隔离，fail-closed）。
  - 可选联动 `AuditService.record_task_action`（actor 真实，默认 USER）。

## 2. 任务2：协作评论模型（`agents/enterprise/comment.py`，NEW）

- 新增 `CommentResourceKind`（PROJECT / TASK / REVIEW）三类挂载资源。
- 新增 `Comment` dataclass：`comment_id` / `org_id` / `author_id` / `resource_kind` / `resource_id` / `content` / `timestamp`（记录 author/timestamp/resource，要求组织隔离）。
- 新增 `CommentService(org_id, audit=None)`：`add_comment` / `get` / `list_comments`（可按资源类型、资源 id 过滤）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。
  - 可选联动 `AuditService.record_comment_action`（actor 真实，默认 USER）。

## 3. 任务3：通知中心（`agents/enterprise/notification.py`，NEW）

- 新增 `NotificationKind`（TASK_CHANGED / REVIEW_REMINDER / PERMISSION_CHANGED）。
- 新增 `Notification` dataclass：`notification_id` / `org_id` / `recipient_id` / `kind` / `title` / `body` / `ts` / `read`。
- 新增 `NotificationService(org_id, audit=None)`：`push` / `mark_read` / `get` / `list_for`（按接收人过滤）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。
  - **红线⑥加固**：继承 `_RedLineForbiddenMixin`，扩展 forbidden 名单，`notify_human_approval` / `forge_approval` 在结构上不可达（禁止伪造人工审批通知）。
  - 可选联动 `AuditService.record_notification_action`（actor 真实，默认 USER）。

## 4. 任务4：任务工作流（`agents/enterprise/task_workflow.py`，NEW）

- 新增 `TaskWorkflowStatus`（CREATED/ASSIGNED/PROCESSING/WAITING_REVIEW/COMPLETED）状态机。
- 新增 `TaskWorkflow` dataclass：`workflow_id` / `org_id` / `task_id` / `status` / `reviewer_id` / `review_result` / `review_note` / `created_at` / `updated_at`。
- 新增 `TaskWorkflowService(org_id, audit=None)`：驱动状态机 `create_workflow` → `assign` → `start_processing` → `submit_for_review` → `record_review_result`。
  - 状态机由 `_ALLOWED_TRANSITIONS` 强制（非法跃迁抛 `EnterpriseRedLineViolationError`）。
  - **人工审核节点必须 human 驱动**：`record_review_result(reviewer_id, approved)` 必须传入非空真实 `reviewer_id`，否则拒（红线⑥：禁止匿名/系统代审）；`approved=True → COMPLETED`，`approved=False → PROCESSING`（打回重做）。
  - **不提供 `approve` 方法**：继承 `_RedLineForbiddenMixin`，`approve` / `engineering_approved` / `sign` / `authorize` / `auto_approve` / `auto_sign_off` 结构性拦截（红线②/④/⑥）。
  - 审核结论如实登记，`actor_kind=USER`（actor 真实，红线⑥）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。

## 5. 任务5：审计增强（`agents/enterprise/audit.py`，MODIFIED）

- 新增 `AuditActionCategory.COLLABORATION`（协作动作大类）。
- 新增 `record_task_action` / `record_comment_action` / `record_notification_action`：
  - `category=COLLABORATION`；`actor_kind` 默认 `USER`，可显式指定 `AI` / `SYSTEM`（actor 真实，不伪造）。
  - 保持 `record_human_approval` 被 `_RedLineForbiddenMixin` 拦截（红线⑥）。
- 既有 `record_ai_action` / `record_user_action` / `record_workflow_event` / 权限审计方法全部不变，向前兼容。

## 6. 任务6：测试（`tests/agents/`，NEW，6 类 +37 用例）

| 测试文件 | 覆盖 | 用例数 |
|---|---|---|
| `test_enterprise_task.py` | 任务字段/org 隔离/assign+status 流转/列表/跨域隔离/审计联动/构造 fail-closed | 5 |
| `test_enterprise_comment.py` | 三类资源评论/列表过滤/跨域隔离/审计联动/构造 fail-closed | 5 |
| `test_enterprise_notification.py` | 三类通知/已读/列表/跨域隔离/审计联动/伪造审批方法被拦截/构造 fail-closed | 5 |
| `test_enterprise_task_workflow.py` | 状态机 happy path/打回/非法跃迁/审核需 human/approve 被禁/actor=USER/构造 fail-closed | 7 |
| `test_enterprise_audit_collab.py` | COLLABORATION 类别/三方法默认 USER/actor_kind 覆盖/query 过滤/record_human_approval 仍禁 | 6 |
| `test_enterprise_collab_red_line.py` | safety_invariants_ok / 新服务构造 fail-closed（参数化 5）/聚合装配/通知伪造/工作流 approve 被禁 | 9（含参数化展开） |

- **全 agents 套件：917 passed（880 基线 + 37）零回归**，耗时约 27s。
- **未修改 `verified.json` / `config.yaml` / `engineering_enabled`**：启用态仅通过 `monkeypatch agents.enterprise.red_line.load_engineering_enabled` 内存注入。

## 7. 聚合装配（`agents/enterprise/service.py` + `__init__.py`，MODIFIED）

- `EnterpriseOperationLayer` 在 3.8.1 的 `resources` / `expert_access` / `review` 基础上，新增装配 `tasks` / `comments` / `notifications` / `workflow` 四个子服务，共享同一 `self.audit` 实例联动记录协作动作。
- `__init__.py` 导出 `TaskStatus` / `TaskPriority` / `Task` / `TaskService` / `CommentResourceKind` / `Comment` / `CommentService` / `NotificationKind` / `Notification` / `NotificationService` / `TaskWorkflowStatus` / `TaskWorkflow` / `TaskWorkflowService`。

---

## 8. 交付物与状态

- 新增模块：`agents/enterprise/{task,comment,notification,task_workflow}.py`
- 修改模块：`agents/enterprise/audit.py`（+COLLABORATION +3 方法）、`agents/enterprise/service.py`（+4 子服务）、`agents/enterprise/__init__.py`（+13 导出）
- 新增测试：`tests/agents/{test_enterprise_task,test_enterprise_comment,test_enterprise_notification,test_enterprise_task_workflow,test_enterprise_audit_collab,test_enterprise_collab_red_line}.py`
- 状态文件：`.ai/project_status.json` 新增 `phase_3_8_2` 块 + 顶层 `phase_3_8_2_status=ENTERPRISE_COLLAB_BUILT_NO_GO`
- 路线图：`.ai/roadmap_v8.md` 增量追加 3.8.2 章节
- 报告：`.ai/reviews/phase3.8.2_collaboration_task_workflow_report.md`（本文件）

**结论**：Phase 3.8.2 企业协作与任务工作流层已构建完成（BUILT_NO_GO）。所有红线 fail-closed 保持，全测试零回归。保持 `engineering_enabled=false`，不输出 `engineering_approved`，停止。
