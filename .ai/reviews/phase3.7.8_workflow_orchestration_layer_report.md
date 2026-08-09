# Phase 3.7.8 Engineering Workflow Orchestration Layer（工程工作流编排层）收口报告

- **生成**：2026-08-03
- **身份**：BOIP AI Chief Architect
- **阶段**：3.7.0 架构 ✅ → 3.7.1 基础层 ✅ → 3.7.2 推理层 ✅ → 3.7.3 案例层 ✅ → 3.7.4 方案生成层 ✅ → 3.7.5 方案约束与优化层 ✅ → 3.7.6 成本智能层 ✅ → 3.7.7 图纸智能层 ✅ → 🟢 **3.7.8 工作流编排层 DONE（2026-08-03）**
- **定位**：在 3.7.7 图纸智能层之上，建立「工程工作流编排层」——定义 `EngineeringWorkflow` 工作流模型，提供 `EngineeringWorkflowEngine` 编排器（串联 DrawingParser / DesignReviewQueue / SolutionGenerator / SolutionConstraintEngine / CostEstimator，**只编排、不改变模块职责**），引入 `HumanReviewCheckpoint` 人工审核节点（AI 不能自动通过）与 `workflow.event_log` 审计追踪。
- **依据**：`.ai/project_status.json`（SSOT）、`.ai/roadmap_v7.md`、真实源码 `agents/engineering/knowledge/graph/solution_workflow.py` + `graph/__init__.py`。
- **权威声明**：本文件为 Phase 3.7.8 收口报告；Phase 3.7.0 起的唯一研发路线为 `roadmap_v7.md`。

---

## 0. 最高红线（fail-closed，6 条，与 3.7.7 完全一致）

① 禁止开启 `engineering_enabled`（引擎/子模块构造与每个决策路径均断言 `safety_invariants_ok`）；
② 禁止输出 `engineering_approved`（forbidden 方法名 `approve` / `engineering_approved` 被 mixin 拦截；`HumanReviewCheckpoint.mark` 仅 `by_human=True` 可放行，AI 调用抛 `SolutionRedLineViolationError`）；
③ 禁止自动确认图纸尺寸（forbidden 方法名 `confirm_dimension` / `select` / `finalize` / `activate`）；
④ 禁止自动生成真实工程参数（forbidden 方法名 `generate_engineering_param`）；
⑤ 禁止自动报价（forbidden 方法名 `quote` / `pricing`）；
⑥ 禁止绕过 `UnifiedActivationGate`（构造/启动/执行/暂停/恢复所有决策路径先断言 `safety_invariants_ok`）。

本层仅编排既有占位壳模块（解析/视觉/生成/约束/估算均不产出真实尺寸/参数/报价），并在人工审核节点处挂起等待人类终裁；真实尺寸/工程参数/报价须经专家双签 + 主理人核准（G6）写入来源系统，属激活阶段，绝不在本层发生。

---

## 1. 任务落地（Tasks 1-6）

### 任务1：EngineeringWorkflow 工作流模型（定义契约）

- ✅ `EngineeringWorkflow` dataclass（`agents/engineering/knowledge/graph/solution_workflow.py`）：
  - 契约字段（`workflow_id` / `input_source` / `stages` / `status` / `created_at` / `requires_human_review`）全部落地；任务5 额外携带 `event_log` 审计追踪，不影响上述契约。
  - 方法 `stage_by_name(name)` / `next_pending_stage()` 支撑阶段可追踪与顺序推进。
- ✅ **非图谱节点**（与 `DesignCandidate` 同性质）：不进 `KnowledgeGraphEntityType` / `_ENTITY_DISPATCH` / 17 关系白名单，扩展零回归（`len(RELATIONSHIP_SPECS) == 17` 不受影响，测试已断言）。

### 任务2：EngineeringWorkflowEngine 流程编排器（核心 API）

- ✅ `EngineeringWorkflowEngine(_RedLineForbiddenMixin)`：
  - `start_workflow(*, workflow_id, input_source, design_id=None, file_path=None, parse_format="pdf", cases=None)` → 建立 6 阶段（`STAGE_ORDER`）+ 人工审核节点，状态 `running`，记录 `started` 审计事件。
  - `execute_stage(workflow_id, *, stage_name=None)` → 默认执行下一个 pending 阶段；每阶段 `running`→`done`（或 `human_review`→`awaiting_human` 并挂起），异常还原 `pending` 并记录 `error` 事件（不吞异常）。
  - `pause_for_review(workflow_id)` → 显式挂起为 `paused_for_review`，记录审计。
  - `resume_workflow(workflow_id)` → **仅当** `HumanReviewCheckpoint.all_passed()`（三节点全部 `by_human=True` 通过）才收尾 `human_review` 阶段并标记 `completed`；否则维持 `running` 等待人工，绝不 AI 代审/代通过。
  - 阶段可追踪：每个 `WorkflowStage` 带 `actor` / `started_at` / `finished_at` / `result_ref` / `note`。

### 任务3：接入既有模块（只编排，不改职责）

- ✅ `EngineeringWorkflowEngine.__init__` 仅构造 5 个子模块句柄并调用其既有方法（`_dispatch` 按阶段分派）：
  - `parse_drawing` → `DrawingParser.parse_{pdf,cad,image}`；
  - `review_drawing` → `DesignReviewQueue.submit` + `begin_review`；
  - `generate_solution` → `SolutionGenerator.generate`；
  - `check_constraint` → `SolutionConstraintEngine.check_geometry`；
  - `estimate_cost` → `CostEstimator.total_estimate`；
  - `human_review` → 挂接已建 `HumanReviewCheckpoint`，不自动通过。
- ✅ 不修改任何被编排模块的内部逻辑、签名、契约或职责边界；编排层为纯调度壳（fail-closed 断言 + 审计日志）。

### 任务4：HumanReviewCheckpoint 人工审核节点（AI 不可自动通过）

- ✅ `HumanReviewCheckpoint`：三门 `CHECKPOINTS = ("drawing_verified", "solution_reviewed", "cost_reviewed")`。
- ✅ 构造即断言 `safety_invariants_ok()`（红线①/⑥）。
- ✅ `mark(checkpoint, *, by_human=False)`：非 `by_human` 调用一律抛 `SolutionRedLineViolationError`（红线②：AI 不得自动通过人工审核节点）；仅 `by_human=True` 可放行并记录 `human_reviewer` 决策人与时间戳。
- ✅ `is_passed` / `all_passed` / `status()` 提供审核态查询；引擎经 `human_checkpoint(workflow_id)` 暴露节点供真实人类调用 `mark(by_human=True)`。

### 任务5：审计追踪 workflow_event_log

- ✅ `WorkflowEvent` dataclass（`stage` / `actor` / `timestamp` / `status` / `detail`）。
- ✅ 引擎内部 `_log(wf, *, stage, actor, status, detail="")` 在每次关键转移追加 `WorkflowEvent` 至 `wf.event_log`：
  - `start_workflow` → `workflow/started`；
  - `execute_stage` 每阶段 → `running` +（`done` 或 `awaiting_human` 或 `error`）；
  - `pause_for_review` → `paused_for_review`；
  - `resume_workflow` → `human_review/done` + `workflow/completed`（人工通过）或 `workflow/resumed`（等待人工）。
- ✅ 测试断言审计事件齐备（started / 5×done / awaiting_human / completed / human_review done）。

### 任务6：测试（workflow / stage / review checkpoint / audit / red line）

- ✅ 新建 `tests/agents/test_knowledge_graph_workflow.py`，覆盖 6 类：**22 用例全绿**。
- ✅ 复用 `test_knowledge_graph_cost.py` 夹具模式（`_make_item` / `_populated_repo` / `CaseEntity.from_node` / `KnowledgeItem`），纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / D-1 / WF-*），不写真实值。
- ✅ **不修改 `verified.json` / `engineering_enabled`**（全内存图谱，构造/启动/执行/暂停/恢复全断言 `safety_invariants_ok`）。
- ✅ 全 agents 套件回归：`740 → 762 passed`（**+22**），零回归。

---

## 2. 红线核验（6/6 fail-closed）

| # | 红线 | 遵守 | 落实点 |
|---|---|---|---|
| ① | 禁止开启 `engineering_enabled` | ✅ | 引擎/子模块/HRC 构造 + `start_workflow`/`execute_stage`/`pause_for_review`/`resume_workflow` 全断言 `safety_invariants_ok()`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | ✅ | `_FORBIDDEN_WORKFLOW_METHODS` 含 `approve`/`engineering_approved`，mixin 拦截；`HumanReviewCheckpoint.mark` 仅 `by_human=True` 可放行，AI 调用抛 `SolutionRedLineViolationError`；全文未输出 approved |
| ③ | 禁止自动确认图纸尺寸 | ✅ | forbidden 方法名含 `confirm_dimension`/`select`/`finalize`/`activate`；编排层不触碰尺寸确认，尺寸仍走 `DesignReviewQueue`（仅人工 `verify`） |
| ④ | 禁止自动生成真实工程参数 | ✅ | forbidden 方法名含 `generate_engineering_param`；被编排的 `DrawingParser`/`SolutionGenerator` 仍恒产出占位壳 |
| ⑤ | 禁止自动报价 | ✅ | forbidden 方法名含 `quote`/`pricing`；编排层无报价路径，成本估算仍仅占位（需人工审核） |
| ⑥ | 禁止绕过 `UnifiedActivationGate` | ✅ | 构造/启动/执行/暂停/恢复所有决策路径先断言 `safety_invariants_ok()`；测试 `test_safety_invariants_block_construction` 验证翻转即 fail-closed |

附加零回归：`EngineeringWorkflow` / `WorkflowStage` 等纯数据壳不进 `KnowledgeGraphEntityType` 枚举、`len(RELATIONSHIP_SPECS) == 17` 不变（测试断言）。

---

## 3. 交付物清单

- ✅ `agents/engineering/knowledge/graph/solution_workflow.py`（新建：Tasks 1-5 实现，含 docstring 6 红线说明、`_FORBIDDEN_WORKFLOW_METHODS`、`STAGE_ORDER`、`_utc_now`、`__all__`）
- ✅ `agents/engineering/knowledge/graph/__init__.py`（更新：docstring 补 3.7.8 段 + 导入 6 新符号 + `__all__` 追加）
- ✅ `tests/agents/test_knowledge_graph_workflow.py`（新建：Task 6，22 用例）
- ✅ `.ai/reviews/phase3.7.8_workflow_orchestration_layer_report.md`（本报告）
- ✅ `.ai/project_status.json`（更新：`phase_3_7.3.7.8` 块 + 刷新 `phase_3_7` 状态）
- ✅ `.ai/roadmap_v7.md`（更新：§1 状态链补 3.7.8、§2.10 新增、§3.8 红线 6/6）

## 4. 激活态结论

- `engineering_enabled=false`（真实读取 `agents/config.yaml`，未动）
- 无任何 `engineering_approved` 输出
- 工作流执行到 `human_review` 阶段挂起（`paused_for_review`），`resume_workflow` 仅依赖三节点 `by_human=True` 通过才收尾
- ESW 窗口维持 `OPEN_EMPTY`；真实尺寸/工程参数/报价仍须经专家双签 + 主理人核准写入来源系统（属激活阶段，不在本层发生）

**阶段收口声明**：Phase 3.7.8 全部任务（Tasks 1-6）已落地、测试全绿（762 passed）、6 红线 6/6 fail-closed 守约。本轮完成后停止，保持 `engineering_enabled=false`，不输出 `engineering_approved`。
