# Phase 3.8.26 企业智能体治理持久化与人工操作界面层 —— 收口报告（批次 B：Persistence & Human Operation Interface）

> 状态：**BUILT_NO_GO（已收口，停等主理人审核）**
> 阶段：Phase 3.8.26 Enterprise Agent Governance Persistence & Human Operation Interface Layer（持久化 + 人工操作界面层）
> 角色：BOIP AI Chief Architect（AI 执行，受六道 fail-closed 红线约束）
> 配套前序：3.8.25 治理工作流编排层（六态机 + 编排器）/ 3.8.26 批次 A 治理驾驶舱（只读 + 单一人工确认入口，见 `phase3.8.26_governance_dashboard_closure_report.md`）
> 任务：#761(T1) #759(T2) #760(T3) #762(T4) #763(T5) #769(T6) #764(T7) #765(T8) #766(T9) #767(T10) #768(T11) —— 全部完成，STOP。

---

## 1. 阶段目标与范围

在 **3.8.25 治理工作流编排层（六态机 + Orchestrator）** 与 **3.8.26 批次 A 治理驾驶舱（只读 + 单确认入口）** 之上，补齐**持久化与完整人工操作界面**，使治理事实可落库、可跨重启存活、可由真实责任人经网页端完成「上报 → 研判确认 → 提交结果 → 闭环」全链路，且全程可审计。

**核心定位（复用而非重建）**：本层只把 live Orchestrator 的事实快照落库，不重写状态机；发现 `orchestrator.py` 仅有私有 `_ensure_*`/`_get_*` 方法、无公开 `human_confirm`，故 **Repository(DB) 作为系统记录源**，API/UI 仅经 Repository 落库并写审计，避免触碰未跟踪的 `service.py` 同名类冲突。

**链路**：`Workflow → Database → Human UI → Audit`（复用 live `GovernanceWorkflowOrchestrator` 的事实，不重建其状态机）。

**最高原则（不可妥协，六道 fail-closed 红线）**：
1. 禁止开启 `engineering_enabled`（保持 `false`）；
2. 禁止输出 `engineering_approved`；
3. 禁止 AI 自动操作治理流程（`auto_confirm`/`auto_execute`/`auto_close`/`auto_assign`）；
4. 禁止 AI 自动修改治理状态；
5. 禁止 AI 自动修改权限策略；
6. 禁止 AI 代替人工操作。

本批次**不进入 3.8.27**，收口即 STOP 等主理人审核。

---

## 2. 交付物清单（11 任务 → 代码/测试/文档）

| 任务 | 文件 | 说明 |
|---|---|---|
| T1/T2 持久化模型 | `backend/app/db/models/governance_workflow.py`（新增，untracked） | ORM：`GovernanceWorkflowRecord`（23 列）+ `GovernanceExecutionRecord`（15 列）+ 4 常量 + 状态六态/人工确认/组织隔离 CHECK 约束 |
| T1/T2 注册 | `backend/app/db/models/__init__.py`（修改） | 导出两模型 |
| T3 Alembic 迁移 | `backend/alembic/versions/3826a1b2c3d4_phase3_8_26_governance_persistence.py`（新增，untracked） | `down_revision='637cbf3eafca'`（rbac_foundation head）；建 `governance_workflow_records` + `governance_execution_records`；4 CHECK + FK ON DELETE CASCADE + `uq_execution_record_org` + 索引；实跑升级/回退验证 |
| T4 Repository | `backend/app/db/repositories/governance_workflow_repository.py`（新增，untracked） | `GovernanceWorkflowRepository`：7 方法，全部 `require_human_actor` + 组织隔离（`OrgScopeError`）+ 执行记录 `actor_kind='user'` 强制 |
| T4 导出 | `backend/app/db/repositories/__init__.py`（新增，untracked） | 导出 `GovernanceWorkflowRepository` / `GovernanceRepositoryError` / `OrgScopeError` |
| T5 人工操作 API | `backend/app/api/governance_operations.py`（新增，untracked） | `require_user`（非 user → 403）；端点：上报(201)/列表(审计 VIEW)/查看/confirm-review/submit-result/close/静态 UI；写操作经 Repository 落库 + `AuditService` 审计 |
| T5 路由注册 | `backend/app/api/__init__.py`（修改）、`backend/app/main.py`（修改） | `governance_operations_router` 导出并 `include_router` |
| T6 人工界面 | `backend/app/static/governance_human_ui.html`（新增，untracked） | 单文件、无 CDN、内联 CSS/JS；顶部红线横幅「无自动按钮」；仅人工按钮（上报/刷新/查看/研判确认/提交结果/闭环）；无 `setInterval`/`setTimeout`/自动动作 |
| T7 审计增强 | `agents/enterprise/audit.py`（整体 untracked，含本批改动） | 新增 `AGENT_GOVERNANCE_WORKFLOW_VIEW`（审计大类 68→69）+ 4 方法 `record_agent_governance_workflow_create/review/execution/view`（均 `actor_kind=USER`，经 `_append`） |
| T8 八类 fail-closed 测试 | `backend/tests/test_governance_persistence_workflow.py`（新增，untracked） | 10 用例 / 8 类 fail-closed：DB 三道 CHECK、Repository+API 双层 AI 拒斥、禁列名结构断言、审计禁制 |
| T9 最终验证 | （本会话执行） | 见 §4 |
| T10 收口报告 | `.ai/reviews/phase3.8.26_persistence_human_operation_closure_report.md`（本文件） | 8 节 |
| T11 状态更新 | `.ai/project_status.json` + `.ai/roadmap_v8.md §29` | 见 §8 |

> **Git 状态提示**：上述 backend 交付物与 `agents/enterprise/audit.py` 当前均为 **untracked / 未提交**（含前序 3.8.26 批次 A 已提交的 0b06eb9 之外的增量）。`audit.py` 整个文件历史上即未被纳入版本控制（pre-existing git 状态，非本批引入）。全部改动已就绪、可回滚、待主理人审核后提交。

---

## 3. 红线落地（fail-closed，纵深三道防线）

本批次对「人工操作」建立 **API → Repository → DB** 三层 fail-closed 防御，即便绕过 API 直连 DB 也过不了约束：

**① API 层**（`governance_operations.py`）
- `require_user(x_actor_id, x_actor_kind)`：缺少 `x-actor-id` 或非 `x-actor-kind: user` → **403**。所有写端点 `Depends(require_user)`。
- 禁止任何 `auto_confirm/auto_execute/auto_close/auto_assign/auto_approve` 端点或参数（代码扫描 0 命中）。

**② Repository 层**（`governance_workflow_repository.py`）
- 所有变更状态方法 `update_status/close_workflow/archive_workflow` 经 `require_human_actor(actor_kind)`：AI 传入 `actor_kind != user` 即抛。
- `add_execution` 强制 `actor_kind='user'`（DB CHECK 钉死，Repository 再校验一次）。
- `save_workflow/get_workflow/list_workflows/list_executions` 强制 `org_id` 非空且组织隔离（越权返回 `None`，空 org 抛 `OrgScopeError`）。

**③ DB 层**（迁移 + ORM CHECK 约束，三道常量）
- `status` 六态白名单 CHECK（`created/under_review/human_confirmed/in_progress/waiting_result/completed/archived`）；
- `requires_human_confirmation IN (1,true)` 恒真 CHECK（禁止置 False）；
- `actor_kind = 'user'` 恒真 CHECK（执行记录禁止 AI 写入）。

**全局红线确认**（§1 六条）：
- `engineering_enabled = false`（`agents/config.yaml:102`）✅；
- 无 `engineering_approved` 实际输出（仅文档声明禁止）✅；
- 无 `auto_*` 治理动作 ✅；
- AI 不可改治理状态 / 权限策略 / 代替人工 ✅（见 §4 测试实证）。

---

## 4. 测试与验证（T9）

**执行**：`backend/.venv/bin/python -m pytest tests/agents -q`（BOIP 根目录，agents 大套件）。

**结果**：**2069 passed**。

**本批次引入的回归已修正**：T7 按 spec 将审计大类推至 69，导致 11 个历史「全局计数」断言（断言 `==68`）失败。这些断言是更早 phase 的 stale 硬编码（名字仍写 `total_50/53/44`，断言本身为 68，即 T7 前与磁盘实际值一致），属本批 T7 直接回归。已将 11 个测试断言统一修正为 `== 69`，并给 `test_enterprise_knowledge_governance_audit.py` 的 `EXPECTED_CATEGORIES` 常量补 `agent_governance_workflow_view`。复跑 11/11 通过。

**T8 后端集成测试**：`backend/tests/test_governance_persistence_workflow.py` → **10/10 通过**（8 类 fail-closed 全绿：DB 三道 CHECK 拒 `auto_*`/拒置 `requires_human=False`/拒 `actor_kind≠user`；Repository 组织隔离；API 双层 AI 拒斥 403；禁列名结构断言；`record_human_approval` 拦截 + `AuditActionCategory` 总数==69 + VIEW/REVIEW/EXECUTION/CREATE 四类 `actor=user`）。该 fixture 经 `main.py` 加载 `governance_operations_router`，间接验证路由注册无破坏。

**已知残留（非本批回归，历史债）**：`test_threshold_migration.py` / `test_threshold_real_drill.py` 共 **16 个**失败，**仅在全量成组运行时出现**；单独放行运行 `22 passed`。根因为 threshold 测试扫描 `tests/` 下其他测试再生的成百 `_tmp_drill_*` 临时文件致雪崩（working memory 已记录为历史 hygiene 债，建议单独修）。这些测试**不 import 本批任何新模块、本批亦未触碰 threshold 逻辑 → 0 回归**。本批增量 + 修正后 agents 套件零新增失败。

---

## 5. 架构与数据流

```
真实责任人(USER 头) ──▶ 治理人工界面 governance_human_ui.html
                              │ fetch + 手动点击（无自动动作）
                              ▼
                     POST /governance/ops/*  (require_user → 403 非 user)
                              │
                              ▼
              GovernanceWorkflowRepository  (require_human_actor + 组织隔离)
                 写 DB：governance_workflow_records / governance_execution_records
                 （DB CHECK：status 六态 / requires_human 恒真 / actor_kind=user 恒真）
                              │
                              ▼
                       AuditService._append  (actor_kind=USER)
                 审计类别 AGENT_GOVERNANCE_WORKFLOW_{CREATE,REVIEW,EXECUTION,VIEW}
                              │
       复用 ──▶ GovernanceWorkflowOrchestrator(3.8.25) 六态机事实（不重建状态机）
```

设计要点：**持久化层只落库快照，不持有状态机**；Repository 为系统记录源；API/UI 不绕过 Orchestrator 事实；审计 actor 如实标 `user`，AI 动作（`_append` 内部 AI→user 区分）绝不伪装成人工。

---

## 6. 风险与限制

- **未提交（untracked）**：backend 交付物与 `agents/enterprise/audit.py` 尚未纳入版本控制，待主理人审核后提交（建议独立分支 `feat/phase3.8.26-governance-persistence`）。
- **审计枚举全局计数漂移**：审计大类为全局枚举，每新增类别需同步更新各 phase 计数断言（本次已修正 11 处）。建议后续改为「基数自校验 + 关键类别存在性」断言，消除硬编码全局数。
- **threshold 雪崩债**：`tests/` 下 `_tmp_drill_*` 历史债与 threshold 测试全局目录扫描耦合，全量成组跑会雪崩；属环境/测试设计债，不在本批范围，建议单独 hygiene 修复（阈值测试改用隔离临时目录）。
- **环境安全删除护栏**：本沙箱环境的 `[SAFE_DELETE_BULK_CONFIRM_REQUIRED]` 护栏会在批量删文件时拦截；维护者 CI（local_ci.sh）无此护栏，threshold 测试在其下本就全绿。

---

## 7. 未决事项（Open Items，待主理人/专家线下）

1. 本批代码审核与提交（建议独立分支，勿混入 0b06eb9）。
2. `agents/enterprise/audit.py` 纳入版本控制（当前整体 untracked）。
3. 真实治理证据（责任人的 USER 身份、组织归属）由主理人 + 专家线下提交后，人类终端显式置 `engineering_enabled=true` 方可解除 NO-GO。
4. threshold 雪崩 hygiene 修复（独立于本 Phase）。
5. 激活态维持 `BUILT_NO_GO`：ESW 窗口 OPEN_EMPTY，等主理人 + 专家线下提交真实证据后人类终端显式置 `enabled=true`。

---

## 8. 状态结论与 STOP 纪律

- **Phase 3.8.26 批次 B（持久化 + 人工操作界面层）：BUILT_NO_GO，已收口。**
- 11 项任务（#761/#759/#760/#762/#763/#769/#764/#765/#766/#767/#768）全部完成。
- 六道 fail-closed 红线逐项落地（API 403 / Repository human-only / DB 三道 CHECK），实测 AI 全拒。
- 测试：agents 套件 2069 passed（本批引入的 11 个计数回归已修正）；T8 后端 10/10；threshold 16 失败为历史债、非本批回归。
- **STOP：不进入 3.8.27，不自动开启 `engineering_enabled`，不输出 `engineering_approved`，不自动评级/确认/禁用/报价 Agent，不代替人工责任。等待主理人审核授权。**

> 配套文档：批次 A 收口见 `phase3.8.26_governance_dashboard_closure_report.md`；状态同步见 `project_status.json`（`phase_3_8_26_status`）与 `roadmap_v8.md §29`。
