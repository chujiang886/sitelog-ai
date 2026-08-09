# Phase 3.7.9 Engineering AI Assistant Interface Layer（工程 AI 助手交互层）收口报告

- **日期**：2026-08-03
- **身份**：BOIP AI Chief Architect
- **基线**：Phase 3.7.0~3.7.8 ✅（工作流编排层 DONE，2026-08-03）
- **状态**：🟢 **ASSISTANT_INTERFACE_LAYER_BUILT_NO_GO**（已构建，未激活）
- **激活态**：`engineering_enabled=false`；**NO-GO 维持**

---

## 0. 最高红线（fail-closed，6 条，与 3.7.8 实质一致）

| # | 红线 | 本层落点 |
|---|---|---|
| 1 | 禁止开启 `engineering_enabled` | 桥/会话/门户构造与每个决策路径均断言 `safety_invariants_ok` |
| 2 | 禁止输出 `engineering_approved` | forbidden 方法名 `approve`/`engineering_approved` 被 mixin 拦截；审核节点仅 `by_human=True` 可放行 |
| 3 | 禁止自动确认工程结果 | forbidden 方法名 `confirm_dimension`/`select`/`finalize`/`activate`/`generate_engineering_param`；`results_confirmed`/`direct_judgment` **恒 False** |
| 4 | 禁止自动生成真实工程参数 | forbidden 方法名 `generate_engineering_param` |
| 5 | 禁止自动报价 | forbidden 方法名 `quote`/`pricing` |
| 6 | 禁止绕过 `UnifiedActivationGate` | 构造/建流/查状态/提交人工决策所有路径先断言 `safety_invariants_ok` |

> 本层**仅**承载会话壳、请求/响应载体与桥接/门户，不写 `verified.json`、不开启 `engineering_enabled`、不输出 `engineering_approved`、绝不编造真实工程参数；所有真实工程结论须经专家双签 + 主理人核准（G6）写入来源系统，属激活阶段，绝不在本层发生。

---

## 1. 任务交付清单

### 任务1：AssistantSession（会话模型）
- **位置**：`agents/engineering/knowledge/graph/solution_assistant.py`
- **契约**：`session_id` / `user_input` / `files` / `workflow_id` / `status` / `created_at`
- **非图谱节点**：与 `EngineeringWorkflow` 同性质，不进 `KnowledgeGraphEntityType` / `_ENTITY_DISPATCH` / 17 关系白名单，**扩展零回归**（`len(RELATIONSHIP_SPECS)==17` 不受影响）。

### 任务2：用户输入处理（WorkflowRequest）
- **产物**：`WorkflowRequest`（`session_id` / `text` / `files` / `parse_format` / `design_id` / `direct_judgment`）
- **`_infer_parse_format(files, text)`**：按扩展名推断 `cad` / `image` / `pdf`，缺省 `pdf`。
- **`_build_input_source(...)`**：构造 `EngineeringWorkflowEngine.start_workflow` 所需的 `input_source`（含 `file_path` / `parse_format` / `design_id` / `text`）。
- **红线③**：`direct_judgment` **恒 False**——交互层只把用户输入转成「待处理请求」，绝不替用户做工程判定（不得以 AI 身份确认尺寸/参数/选终/批准）。

### 任务3：AssistantWorkflowBridge（桥接层）
- **API**：`create_workflow` / `attach_files` / `query_status`（`get_session` / `session_workflow_id` 便捷查询）
- **`_FORBIDDEN = _FORBIDDEN_ASSISTANT_METHODS`**：复用 `_RedLineForbiddenMixin`，拦截 `approve`/`engineering_approved`/`select`/`finalize`/`activate`/`quote`/`pricing`/`confirm_dimension`/`generate_engineering_param`
- **只桥接、不改职责**：持 `EngineeringWorkflowEngine` 句柄（`self.engine`），调用既有 `start_workflow`；`workflow_id=f"WF-{session_id}"`；建流时 `direct_judgment=False` 不做任何工程决策；每个方法先断言 `safety_invariants_ok()`。

### 任务4：AssistantResponse（响应载体）
- **契约**：`session_id` / `workflow_status` / `candidate_results` / `review_required` / `source_trace` / `results_confirmed`
- **红线③**：`results_confirmed` **恒 False**、`review_required` **恒 True**——AI 不替用户确认任何工程结果，始终要求人工复核。

### 任务5：HumanReviewPortal（人工审核入口）
- **只读查看三节点**：`view_drawing_review` / `view_solution_review` / `view_cost_review`（均断言 `safety_invariants_ok`）
- **`submit_human_decision(*, session_id, checkpoint, by_human=False)`**：
  - `by_human=False`（AI 调用）一律抛 `SolutionRedLineViolationError`（红线⑤）
  - 仅 `by_human=True` 桥接到底层 `HumanReviewCheckpoint.mark(by_human=True)`
- **只桥接**：经 `bridge.engine.human_checkpoint(wf_id)` 读取/标记已存储的审核节点，不新增任何审核判定逻辑。

### 任务6：测试（五类）
- **文件**：`tests/agents/test_knowledge_graph_assistant.py`（**+29 用例**）
- **分类**：Assistant 模型（4）/ Session 生命周期（4）/ Workflow Bridge（8）/ Response 载体（3）/ RedLine（10）
- **红线覆盖**：构造 fail-closed（monkeypatch 翻转 `load_engineering_enabled`）、forbidden 方法名拦截、`by_human=False` 自动提交拦截、`results_confirmed`/`direct_judgment` 恒 False、非图谱节点零回归
- **不修改 `verified.json` 与 `engineering_enabled`**：全部用例使用内存图谱（`KnowledgeGraphRepository()` 不传 `store_path`）

---

## 2. 测试与回归结果

| 项 | 结果 |
|---|---|
| 新增测试 | `tests/agents/test_knowledge_graph_assistant.py` → **29 passed** |
| 全 agents 套件（基线 762） | **791 passed**（762 + 29）零回归 |
| `len(RELATIONSHIP_SPECS)` | **17**（非图谱节点扩展零回归） |
| `verified.json` | 未触碰（mtime 仍为 2026-07-28） |
| `agents/config.yaml` 的 `engineering_enabled` | 仍为 `false`（line 102） |

零回归验证命令：
```bash
backend/.venv/bin/python -m pytest tests/agents -q
# 791 passed in 21.32s
```

---

## 3. 伪造扫描（Fabrication Scan）

**0 命中**：交互层零真实工程数值、零真实图纸尺寸、零工程参数、零报价；仅承载会话壳 / 请求响应载体 / 桥接门户。
- `direct_judgment` 恒 False、`results_confirmed` 恒 False；
- `HumanReviewPortal` 仅**只读**查看三审核节点，且 `submit` 强制 `by_human=True`，AI 不替用户通过任何人工审核；
- `workflow_event_log` 来源链仅透传底层工作流阶段事件，未编造任何尺寸/参数/报价结论。

---

## 4. 交付物清单

| 文件 | 说明 |
|---|---|
| `agents/engineering/knowledge/graph/solution_assistant.py` | AssistantSession / WorkflowRequest / `_infer_parse_format` / `_build_input_source` / AssistantWorkflowBridge / AssistantResponse / HumanReviewPortal + `_FORBIDDEN_ASSISTANT_METHODS` |
| `agents/engineering/knowledge/graph/__init__.py` | 追加 3.7.9 五符号导出（`AssistantSession` / `WorkflowRequest` / `AssistantWorkflowBridge` / `AssistantResponse` / `HumanReviewPortal`）+ docstring 段 |
| `tests/agents/test_knowledge_graph_assistant.py` | 五类测试（+29 用例） |
| `.ai/reviews/phase3.7.9_engineering_assistant_interface_report.md` | 本报告 |
| `.ai/roadmap_v7.md` | §1 状态链补 3.7.9、§2.11、§3.9、§4 停止声明更新 |
| `.ai/project_status.json` | 新增 `task_status.phase_3_7.3.7.9` 块 + 刷新 `phase_3_7._phase_status` 为 `ASSISTANT_INTERFACE_LAYER_BUILT_NO_GO` |

---

## 5. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认，`agents/config.yaml` line 102）。
- **未输出 `engineering_approved`**（全文无 approved 字段；forbidden 方法名被 mixin 拦截）。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实证据/参数进入。
- **按指令停止**：工程 AI 助手交互层（3.7.9）实现完成即止，保持 `engineering_enabled=false`、不输出 `engineering_approved`；真实方案数值转正须经 `HumanReviewPortal.submit_human_decision(by_human=True)` 终裁。
- **解锁路径（纯人工）**：主理人+专家经 ESW 窗口提交真实双签阈值（`E/D-TH-*` `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 人类对方案/报价作 `Engineering_Approved`。
