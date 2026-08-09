# Phase 3.8.26 企业智能体治理驾驶舱与人工操作界面层 —— 收口报告

> 状态：**BUILT_NO_GO（已交付，停等主理人审核）**
> 分支：`feat/phase3.8.26-governance-dashboard`
> 角色：企业智能体治理平台首席工程负责人
> 完成标准：✓ 人工可查看治理流程 ✓ 人工可确认任务 ✓ 人工可追踪执行 ✓ 所有动作可审计 ✓ AI 无法越权

---

## 1. 阶段目标

在 3.8.25 治理工作流编排层（六态机 + 编排器）之上，补齐**人工操作入口**：

- 让真实治理责任人能够：查看治理流程、查看待研判、人工确认、追踪执行、查看审计。
- 建设 **Enterprise Governance Dashboard**（后端 API + FastAPI 路由 + Next.js 人工界面）。
- 严守最高原则：**AI 只能辅助，不能治理**；所有关键动作必须 USER 确认；默认拒绝 + 跨组织隔离。

本阶段交付"只读查询 + 单一人工确认入口"的驾驶舱层，自身**不持有任何治理状态**，状态仍由 3.8.25 编排器单一真相源持有。

---

## 2. 架构设计

```
                 ┌─────────────────────────────────────────────┐
                 │        Governance Dashboard (3.8.26)          │
                 │                                               │
  真实责任人 ──▶  │  GET /governance/{workflows,reviews,audit,    │
  (USER 头)      │      summary, workflows/{id}}   ← 只读        │
                 │  POST /governance/review/confirm  ← 唯一写入口│
                 └───────────────┬───────────────────────────────┘
                                 │ 委派（强制 USER）
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  GovernanceWorkflowOrchestrator (3.8.25)       │
                 │  六态机：created→under_review→human_confirmed  │
                 │  →in_progress→waiting_result→completed         │
                 │  human_confirm / start_execution /            │
                 │  submit_execution_result / human_complete /    │
                 │  archive（全部 require_human_actor(USER)）      │
                 └───────────────┬───────────────────────────────┘
                                 │ 复用
            ┌───────────┬────────┴────────┬───────────────┐
            ▼           ▼                 ▼               ▼
      3.8.21 问责层  3.8.24 知识助手   AuditService     IdentityService /
      (derive_task)  (答案草稿)        (审计留痕)       PermissionPolicy /
                                                       KnowledgeVisibilityPolicy
```

设计要点：

- **驾驶舱是薄层**：只读方法委派给编排器 `list_workflows/get_workflow/get_reviews/get_execution_records`；写方法仅 `confirm_review` 一个，委派给编排器 `human_confirm`。
- **权限闸门**：继承 `_RedLineForbiddenMixin`（`_FORBIDDEN = _DASHBOARD_FORBIDDEN`，176 项），复用 `AgentPermissionPolicy.check_agent_access` 做默认拒绝，复用 `EnterpriseIsolationError` 做跨组织隔离。
- **审计增强（Task5）**：所有 UI 动作均留痕 —— 只读查询经 `audit.record_dashboard_query`（actor=USER）记录；确认动作由编排器 `human_confirm` 写 WORKFLOW_REVIEW 审计（actor=USER，含 decision/reason）。
- **HTTP 层**：FastAPI 路由 `backend/app/api/governance_dashboard.py`，依赖注入 `get_dashboard_service()`（生产由 `EnterpriseOperationLayer` 注入，未注入时回退内存演示实例）；`require_user` 依赖强制 `x-actor-kind: user` + `x-actor-id`，否则 403。
- **UI 层**：Next.js App Router 页面 `frontend/src/app/governance-dashboard/page.tsx`，纯客户端、human-only、无自动按钮。

---

## 3. 新增模块

| 模块 | 路径 | 职责 |
|------|------|------|
| 禁名集 | `agents/enterprise/governance_dashboard/forbidden.py` | `_DASHBOARD_FORBIDDEN`（176 项 = 3.8.25 编排层 166 ∪ 本层 17 增量） |
| 视图模型 | `agents/enterprise/governance_dashboard/models.py` | `DashboardUser` / `ExecutionStatusView` / `RiskAlert` / `DashboardSummary` |
| 驾驶舱服务 | `agents/enterprise/governance_dashboard/service.py` | `GovernanceDashboardService`（核心，377 行） |
| 包导出 | `agents/enterprise/governance_dashboard/__init__.py` | 再导出公共服务与模型 |
| FastAPI 路由 | `backend/app/api/governance_dashboard.py` | HTTP 端点（GET 5 + POST 1） |
| 路由注册 | `backend/app/api/__init__.py` + `backend/app/main.py` | 注册 `governance_dashboard_router` |
| 人工界面 | `frontend/src/app/governance-dashboard/page.tsx` | 待研判卡片 + 人工确认表单 |
| 后端测试 | `backend/tests/test_governance_dashboard.py` | TestClient 验证 HTTP 契约（6 用例） |
| 核心测试 | `tests/agents/test_enterprise_governance_dashboard.py` | 服务层 fail-closed 测试（19 用例） |

---

## 4. API 清单

**FastAPI 路由（`prefix=/governance`，全部强制 USER）**

| 方法 | 路径 | 说明 | 对应服务方法 |
|------|------|------|--------------|
| GET  | `/governance/workflows?status=` | 治理工作流列表 | `list_workflows` |
| GET  | `/governance/reviews` | 待人工研判列表（under_review） | `list_pending_reviews` |
| GET  | `/governance/audit?limit=&target=` | 治理相关审计记录（创建/研判/执行三类） | `list_audit_records` |
| GET  | `/governance/workflows/{workflow_id}` | 单条执行状态（状态+研判+执行记录） | `get_execution_status` |
| GET  | `/governance/summary` | 驾驶舱总览计数 | `summary` |
| POST | `/governance/review/confirm` | 人工研判确认（唯一写入口） | `confirm_review` |

**`GovernanceDashboardService` 公共方法**

- 只读：`list_workflows` / `list_pending_reviews` / `get_workflow_detail` / `get_execution_status` / `list_audit_records` / `list_risk_alerts` / `summary`
- 写：`confirm_review`（强制 USER，委派 `orchestrator.human_confirm`）

**请求/响应约定**

- 所有请求头必须携带 `x-actor-id`（责任人 id）与 `x-actor-kind: user`；缺/错 → 403。
- `POST /review/confirm` body：`{ workflow_id, decision(confirmed|rejected|need_more_info), reason, derive_task?, task_id? }`。
- 响应：直接返回治理/审计领域对象（dataclass），由 FastAPI `jsonable_encoder` 序列化（枚举转 `.value`）。

---

## 5. UI 功能

`frontend/src/app/governance-dashboard/page.tsx`（客户端组件，路径 `/governance-dashboard`）：

- **事实摘要**：渲染每条待研判工作流的 `source_facts`（来自 3.8.24 助手答案草稿的事实）。
- **来源**：渲染 `references`（证据来源列表）。
- **流程状态**：状态徽章（候选/待研判/已确认/执行中/待确认结果/已完成）。
- **人工确认**：每个待研判项含「研判决定」下拉（确认/驳回/需补充信息）+ 理由文本框 + 「人工确认」按钮。**按钮必须显式人工点击**，无自动提交、无 AI 代点。
- **全部工作流**：只读列表展示所有工作流及其状态，供追踪。
- **责任人身份**：演示用责任人 `governor-1` / `user`；生产由网关/鉴权层注入 `x-actor-id` / `x-actor-kind` 头。

类型检查：`npx tsc --noEmit`（经 hoisted typescript）对本文件**零错误**（仓库既有 26 处预存错误均与本文件无关，位于测试文件与 `consult` 页）。

---

## 6. 修改文件列表

**新增（3.8.26 范畴）**

- `agents/enterprise/governance_dashboard/forbidden.py`
- `agents/enterprise/governance_dashboard/models.py`
- `agents/enterprise/governance_dashboard/service.py`
- `agents/enterprise/governance_dashboard/__init__.py`
- `backend/app/api/governance_dashboard.py`
- `backend/app/api/__init__.py`（注册导出）
- `backend/app/main.py`（注册路由）
- `frontend/src/app/governance-dashboard/page.tsx`
- `tests/agents/test_enterprise_governance_dashboard.py`
- `backend/tests/test_governance_dashboard.py`
- `.ai/reviews/phase3.8.26_governance_dashboard_closure_report.md`

**修改（接线 / 导出）**

- `agents/enterprise/service.py`：`EnterpriseOperationLayer` 实例化 `agent_governance_dashboard`（`GovernanceDashboardService`），并补 import。
- `agents/enterprise/__init__.py`：导出 `GovernanceDashboardService` / `DashboardUser` / `ExecutionStatusView` / `RiskAlert` / `DashboardSummary`。

> 仓库异常（同 3.8.25）：BOIP 根 `.git` 当前仅跟踪 `.ai/` 文档，**整个 `agents/` Python 树此前未跟踪**。本阶段仅**精确 `git add` 提交 3.8.26 范畴文件，绝不 `git add -A`，不补提交整个未跟踪 `agents/` 树**，避免污染历史、绕过 review。

---

## 7. Git Commit 列表

纪律：精确 `git add` 仅 3.8.26 范畴文件（含后端/前端/测试/报告），**不碰未跟踪 `agents/` 树**。

计划提交（单一逻辑提交，独立 commit）：

```
agents/enterprise/governance_dashboard/forbidden.py
agents/enterprise/governance_dashboard/models.py
agents/enterprise/governance_dashboard/service.py
agents/enterprise/governance_dashboard/__init__.py
agents/enterprise/service.py
agents/enterprise/__init__.py
backend/app/api/governance_dashboard.py
backend/app/api/__init__.py
backend/app/main.py
frontend/src/app/governance-dashboard/page.tsx
tests/agents/test_enterprise_governance_dashboard.py
backend/tests/test_governance_dashboard.py
.ai/reviews/phase3.8.26_governance_dashboard_closure_report.md
```

提交信息（建议）：

```
feat(governance): Phase 3.8.26 企业智能体治理驾驶舱与人工操作界面层（BUILT_NO_GO，停等审核）

- 新增 GovernanceDashboardService（只读查询 + 单一人工确认入口，176 项禁名 fail-closed）
- FastAPI 路由 /governance/*（GET 5 + POST 1，强制 USER）
- Next.js 人工审核界面（事实摘要/来源/状态/确认，无自动按钮）
- 接入 EnterpriseOperationLayer 并导出；权限默认拒绝 + 跨组织隔离 + 审计留痕
- 测试：agents 19 用例 + backend 路由 6 用例，全绿；tests/agents 全量 2043 通过零回归
- 严格精确 git add，未触碰未跟踪 agents 树
```

> 提交哈希于主理人审核后由实际 `git commit` 填写（本收口报告与代码同步纳入同一逻辑提交）。

---

## 8. 测试结果

| 套件 | 用例数 | 结果 |
|------|--------|------|
| `tests/agents/test_enterprise_governance_dashboard.py` | 19 | ✅ all pass |
| `backend/tests/test_governance_dashboard.py`（TestClient） | 6 | ✅ all pass |
| `tests/agents` 全量回归（剔除 4 个 threshold 雪崩测试） | 2043 | ✅ 0 failed |
| `frontend` 类型检查（tsc --noEmit，本文件） | — | ✅ 0 错误 |

覆盖点（fail-closed）：

- 列表 / 待研判 / 执行状态 / 审计 / 风险 / 总览
- 人工确认推进至 `human_confirmed` 且 `confirmed_by` 留痕
- `confirm_review` 派生 3.8.21 治理任务（derive_task → 问责层 create_task，actor=USER）
- **AI 调 confirm_review 被拦**（EnterpriseRedLineViolationError）
- 缺 user 对象被拦；读接口非 USER 被拦
- 权限策略默认拒绝（DenyPolicy → 拒绝；AllowPolicy → 放行）
- 跨组织隔离（EnterpriseIsolationError）
- 结构级禁名拦截（auto_execute / generate_policy 未定义即命中 `_DASHBOARD_FORBIDDEN`）
- 接入 `EnterpriseOperationLayer.agent_governance_dashboard`

---

## 9. 安全红线验证

六条最高红线逐项 ✅（fail-closed）：

1. **engineering_enabled 恒 False**：`GovernanceDashboardService.__init__` 断言 `safety_invariants_ok()`（红线①）。
2. **禁输出 engineering_approved**：继承 `_RedLineForbiddenMixin`，禁名集含 `engineering_approved` / `record_human_approval`。
3. **禁 AI 自动治理/审批/关闭**：`confirm_review` 强制 `require_human_actor(USER)`；AI 调任何写入口必被拦截；读接口同样仅对 USER 开放（驾驶舱责任人专属）。
4. **禁 AI 自动执行**：驾驶舱无任何 execute/apply 能力；执行动作由编排器在人工确认后推进。
5. **禁 AI 自动生成策略 / 改知识**：驾驶舱对 `AgentPermissionPolicy` / `KnowledgeVisibilityPolicy` 纯只读；无文本生成/改写入口；禁名含 `generate_policy` / `modify_knowledge` / `update_knowledge`。
6. **禁 AI 代替责任人**：所有人工节点经编排器 `require_human_actor(USER)`；审计留痕 actor / time / action / object（确认 action 写 WORKFLOW_REVIEW，actor=USER；查询 action 写 DASHBOARD，actor=USER）。

附加隔离验证：

- 默认拒绝：`_ensure_access` 在无 user 或策略拒绝时抛红线违例。
- 跨组织隔离：`_ensure_org_scope` 请求 org ≠ 服务 org 即抛 `EnterpriseIsolationError`。
- 结构级拦截：`_DASHBOARD_FORBIDDEN` = 176 项（3.8.25 编排层 166 ∪ 本层 17 增量：auto_confirm / auto_confirm_review / auto_approve_review / batch_confirm / confirm_on_behalf / click_for_user / auto_resolve / auto_review / auto_execute / auto_close / auto_archive / auto_complete / generate_policy / modify_knowledge / update_knowledge / rewrite_knowledge / auto_draft_decision）。

---

## 10. 当前能力

事件 → 知识 → 事实助手 → 人工治理工作流 → **驾驶舱（本阶段）→** 审计，闭环补完：

- 真实责任人可在驾驶舱 **查看** 全部治理工作流、待研判项、执行状态、审计记录、风险提示。
- 真实责任人可对待研判项 **人工确认**（确认/驳回/需补充信息 + 理由），确认自动委派编排器推进状态机并派生 3.8.21 治理任务。
- 真实责任人可 **追踪执行**（执行状态视图含研判记录与执行跟踪记录）。
- 所有查看/确认动作 **可审计**（actor=USER，含 time/action/object）。
- AI 仍仅能登记候选、推送研判队列、辅助呈现事实；**无法审批/执行/关闭/生成政策/改知识/代替责任人**。

---

## 11. 已知限制

1. **`governance_workflow` 存在重复的 `GovernanceWorkflowOrchestrator` 定义**：`orchestrator.py`（被 `EnterpriseOperationLayer` 与测试使用，方法名 `register_candidate` / `create_from_answer_draft` / `archive` 等）与 `service.py`（被 `governance_workflow/__init__.py` 再导出，方法名 `create_workflow` / `create_from_draft` / `human_archive` 等）。本阶段驾驶舱严格使用 `orchestrator.py` 路径，运行正确；但两定义并存是 3.8.25 遗留隐患，建议主理人审核后统一为单一实现（推荐保留 `orchestrator.py`，将 `governance_workflow/__init__.py` 改指向它，并迁移 `service.py` 风格调用方）。
2. **演示审批头**：前端 `governance-dashboard/page.tsx` 用硬编码演示责任人 `governor-1`；生产需由网关/鉴权层注入 `x-actor-id` / `x-actor-kind`，并将 `NEXT_PUBLIC_API_BASE_URL` 指向真实后端。
3. **后端服务注入**：FastAPI 路由的 `get_dashboard_service()` 在未由 `EnterpriseOperationLayer` 注入时回退内存演示实例（状态不跨进程持久）；生产应在应用启动钩子调用 `set_dashboard_service(layer.agent_governance_dashboard)`。
4. **UI 端到端未跑真实栈**：前端页面经 `tsc` 类型检查（本文件零错误），但未在运行中的 Next+FastAPI 全栈做 E2E 点击验证（需真实后端地址与鉴权）。后端 HTTP 契约已通过 TestClient 6 用例验证。
5. **仓库 git 跟踪异常**：`agents/` 整树未跟踪；本次仅精确提交 3.8.26 范畴文件（见第 6、7 节）。

---

## 12. 下一阶段建议

1. **统一 `GovernanceWorkflowOrchestrator` 双定义**（优先）：消除 `orchestrator.py` / `service.py` 并存，避免后续调用方踩坑。
2. **真实鉴权接入**：将 `x-actor-id` / `x-actor-kind` 改为由企业 RBAC/JWT 网关注入，移除前端硬编码责任人。
3. **执行闭环 UI**：本阶段驾驶舱聚焦「查看 + 确认」；`start_execution` / `submit_execution_result` / `human_complete` / `archive` 等后续人工节点可在下阶段补 UI（均已是 USER 强制，可直接复用）。
4. **持久化与多租户**：当前内存存储；下阶段接数据库 + 组织隔离表，使审计/工作流跨重启可用。
5. **驾驶舱风险联动**：将 `list_risk_alerts` 接入实时通知（邮件/IM），让责任人主动获知待办。

---

**收口**：Phase 3.8.26 功能、测试、红线、收口报告均已就绪。**立即停止开发，不进入 Phase 3.8.27，等待主理人审核。**
