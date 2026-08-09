# Phase 3.7.5 Solution Constraint & Optimization Layer（方案约束与优化层）收口报告

- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-03
- **前置就绪**：Phase 3.7.0 架构 ✅ / 3.7.1 基础层 ✅ / 3.7.2 推理层 ✅ / 3.7.3 案例层 ✅ / 3.7.4 方案生成层 ✅
- **本次交付**：Phase 3.7.5 方案约束与优化层（6 任务全交付，6 红线全守约）
- **激活态**：`engineering_enabled = false`（真实读取 `agents/config.yaml` line 102）；**NO-GO 维持**；未输出 `engineering_approved`

---

## 一、交付概览

Phase 3.7.5 在 3.7.4 方案生成层之上建立「方案约束与优化层」，目标为**提升候选方案质量**而非做出任何工程结论。本层纯粹承载**约束标注、明显冲突过滤、候选对比、来源链解释、人工审核三阶段**；所有真实约束数值、方案选终、报价均**不**在本层发生，须经专家双签 + 主理人核准（G6）的激活流程。

| 维度 | 真实状态 |
|---|---|
| 阶段 | 🟢 **3.7.5 方案约束与优化层 DONE（2026-08-03）** |
| 新增符号 | `SolutionConstraint` / `SolutionConstraintEngine` / `SolutionComparison` / `SolutionExplanation` + 3 报告载体 + `SolutionReviewQueue` 三阶段扩展 |
| 图谱白名单影响 | **零**：`SolutionConstraint` 为纯数据壳，不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系；`7 实体 / 17 关系` 保持不变 |
| 测试 | 全 agents 套件 **692 passed**（基线 670 → +22，零回归）；`verified.json` 未触碰 |
| 红线 | **6/6 守约**（3.7.5 新增第④条「禁止自动报价」） |

---

## 二、六任务交付明细

### 任务1：约束模型（`SolutionConstraint`）
**文件**：`agents/engineering/knowledge/graph/entities.py`

新增 `@dataclass class SolutionConstraint`，字段：
- `constraint_id: str`（必填，唯一标识）
- `type: str = PENDING_PLACEHOLDER`
- `source: str = PENDING_PLACEHOLDER`
- `severity: str = PENDING_PLACEHOLDER`
- `description: str = PENDING_PLACEHOLDER`
- `status: str = PENDING_VERIFICATION`（默认待人工核验转正）

**关键设计**：该模型是**独立纯数据占位壳**，**不**继承图谱实体契约、`to_node`/`from_node` 不参与、不进入 `KnowledgeGraphEntityType` 枚举、不进入 `_ENTITY_DISPATCH`、不新增关系白名单。因此基座测试 `test_knowledge_graph.py` 的 `EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 断言**无需改动**，图谱白名单零污染。已并入 `__all__` 导出。

### 任务2：约束引擎（`SolutionConstraintEngine`）
**文件**：`agents/engineering/knowledge/graph/solution_constraint.py`

四类检查（**仅过滤明显冲突，绝不自动选终/报价**）：
- `check_geometry()`：检测 `solution_id` 重复、方案实质未定（pending 仅标待核验，非冲突）
- `check_dependency()`：检测候选引用的 Case/Rule/Threshold 是否真实缺失于图谱
- `check_compatibility()`：结构性扫描（候选未转正 / 约束状态非 pending 仅记录），不做真实兼容判定
- `check_conflict()`：检测同名 id 的上下文互斥等明显冲突

所有方法返回 `SolutionConstraintReport`（`requires_human_review=True`、`has_conflicts` 仅反映明显冲突）。构造器与方法均断言 `UnifiedActivationGate.safety_invariants_ok()`（红线①/⑥）；无 `select`/`finalize`（由 `_RedLineForbiddenMixin` 拦截，红线③）。

### 任务3：候选对比（`SolutionComparison`）
**文件**：`solution_constraint.py`

`compare(A/B/C)` 输出 `SolutionComparisonReport`：
- `difference`：各候选占位壳字段差异
- `risk`：pending 标记的风险（不输出终裁）
- `knowledge_trace`：沿四关系只读遍历的知识溯源
- `winner`：**恒 None**（由 mixin 拦截 `select`/`finalize`/`quote`/`pricing`，红线③/④）

### 任务4：可解释层（`SolutionExplanation`）
**文件**：`solution_constraint.py`

`explain(candidate)` 沿图谱四关系（`solution_case`/`solution_rule`/`solution_threshold`/`solution_knowledge_item`）**只读** `traverse` 构建 **Case / Rule / Threshold / KnowledgeItem 完整来源链**（`SolutionExplanationReport.source_chain` + 按四类型归类的 `referenced_types`），使方案依据可被人工核验。只读不写（红线③/⑤/⑥），无写图/选终/报价路径。

### 任务5：审核队列增强（`SolutionReviewQueue` 三阶段）
**文件**：`agents/engineering/knowledge/graph/solution_generation.py`

- `SolutionSubmission` 新增三阶段字段：`review_stage`（默认 `"constraint"`）/ `constraint_review_done: bool` / `expert_review_done: bool`
- 新增三方法（均仅 `by_human=True` 可驱动，AI 调用抛 `SolutionRedLineViolationError`，红线②/③）：
  - `record_constraint_review(submission_id, *, by_human=False)` → 标记约束审查完成，进入 `expert` 阶段
  - `record_expert_review(submission_id, *, by_human=False)` → 须先完成约束审查，进入 `human_decision` 阶段
  - `human_decision(submission_id, *, by_human=False, approve=False)` → 须两审查均完成前置，终裁进入 `approved_by_human` / `rejected`
- 保留既有 `approve`/`reject`（仍仅 `by_human=True`）；AI 始终无法进入 `approved_by_human`

### 任务6：测试（`tests/agents/test_knowledge_graph_constraint.py`）
**文件**：`tests/agents/test_knowledge_graph_constraint.py`（新增，+22 用例）

五类覆盖（用户要求）：
1. **constraint 测试**：四检查（geometry/dependency/compatibility/conflict）仅过滤明显冲突
2. **comparison 测试**：A/B/C 对比，输出 difference/risk/knowledge_trace，winner 恒 None
3. **explain 测试**：构建 Case/Rule/Threshold/KnowledgeItem 完整来源链
4. **review 测试**：三阶段（constraint_review / expert_review / human_decision）AI 不能进入
5. **red line 测试**：6 条最高红线 fail-closed（含新增自动报价 `quote`/`pricing` 拦截 + `SolutionConstraint` 不污染图谱白名单）

**红线约束落实**：不修改 `verified.json`（全用例用内存图谱，绝不传 `store_path`）；不开启 `engineering_enabled`（构造/检查/解释全断言 `safety_invariants_ok`）；夹具用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-*），不写真实值。

---

## 三、六红线核验（6/6 守约）

| # | 红线 | 本层落地 | 核验 |
|---|---|---|---|
| ① | 禁止开启 `engineering_enabled` | Engine/Comparison/Explanation/ReviewQueue 构造即 `safety_invariants_ok()` 只读断言 | ✅ 真实 `config.yaml` 仍 `false`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | 三阶段审查与终裁均仅 `by_human=True` 可入 `approved_by_human` | ✅ AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| ③ | 禁止 AI 自动选择最终方案 | Engine/Comparison 无 `select`/`finalize`/`winner` | ✅ `_RedLineForbiddenMixin` 拦截 forbidden 方法名；测试显式断言方法不可达 |
| ④ | 禁止自动报价 | 本轮新增：forbidden 方法名补 `quote`/`pricing` | ✅ Engine/Comparison 访问 `quote`/`pricing` 抛 `SolutionRedLineViolationError`；本层无报价路径 |
| ⑤ | 禁止伪造工程参数 | `SolutionConstraint` 仅占位壳；Candidate `components`/`confidence` 恒 `PENDING`/`pending` | ✅ 约束/解释不填真实数值；`status` 默认 `PENDING_VERIFICATION` |
| ⑥ | 禁止绕过 `UnifiedActivationGate` | 构造/检查/解释/审核所有写/决策路径先断言 `safety_invariants_ok()` | ✅ 闸门复用 fail-closed，无绕过设计 |

> 注：3.7.4 计「5 红线」，3.7.5 将「自动报价」提升为最高红线④，故本层红线体系为 **6 条**，已在 `project_status.json` 与 `roadmap_v7.md` 同步刷新计数。

---

## 四、测试报告

```
backend/.venv/bin/python -m pytest tests/agents -q
→ 692 passed in 22.03s   （基线 670 → +22，零回归）
```

- 基座 `test_knowledge_graph.py`：`EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 全部仍成立（约束模型零污染白名单）
- 新增 `test_knowledge_graph_constraint.py`：22 用例，覆盖 constraint / comparison / explain / review / red line 五类
- `verified.json`：未被任何用例修改（仅内存图谱，未传 `store_path`）—— 已通过 `git status` 核实，三个 `verified.json` 均未进入修改列表

---

## 五、与 3.7.4 的兼容性

| 扩展点 | 影响 | 结论 |
|---|---|---|
| `SolutionConstraint` 是否进图谱枚举 | 不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系 | 白名单 7 实体 / 17 关系不变 |
| `SolutionReviewQueue` 扩展 | 新增三方法 + `SolutionSubmission` 三字段；既有 `approve`/`reject` 行为不变 | 向后兼容，既有 `test_knowledge_graph_solution.py` 全绿 |
| forbidden 方法名 | 3.7.4 的 `_FORBIDDEN_GENERATOR_METHODS` 未含 `quote`/`pricing`；本层 `_FORBIDDEN_CONSTRAINT_METHODS` 补入以覆盖红线④ | 自动报价拦截到位 |

---

## 六、激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认，未自动开启）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实约束数值 / 参数进入。
- **按指令停止**：方案约束与优化层（3.7.5）实现完成即止，不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动选终、不自动报价。
- **解锁路径（纯人工）**：主理人 + 专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 人类对方案 / 报价作 `Engineering_Approved`（经 `SolutionReviewQueue.by_human` 终裁）。

---

## 七、交付文件清单

**代码**
- `agents/engineering/knowledge/graph/entities.py`（新增 `SolutionConstraint` + `__all__` 导出）
- `agents/engineering/knowledge/graph/solution_constraint.py`（新建：`SolutionConstraintEngine` / `SolutionComparison` / `SolutionExplanation` + 3 报告载体 + `_FORBIDDEN_CONSTRAINT_METHODS` 含 `quote`/`pricing`）
- `agents/engineering/knowledge/graph/solution_generation.py`（`SolutionSubmission` 三阶段字段 + `SolutionReviewQueue` 三阶段方法）
- `agents/engineering/knowledge/graph/__init__.py`（追加约束层导出 + docstring 3.7.5）

**测试**
- `tests/agents/test_knowledge_graph_constraint.py`（新建，+22 用例）

**文档**
- `.ai/reviews/phase3.7.5_solution_constraint_optimization_report.md`（本报告）
- `.ai/roadmap_v7.md`（§1 进度链 / §2.7 3.7.5 / §3.5 红线 6/6）
- `.ai/project_status.json`（`task_status.phase_3_7.3.7.5` 块 + `current_stage.phase_3_7_status` + `phase_3_7._phase_status`，红线计数 → 6/6）

---

## 八、结论

Phase 3.7.5 方案约束与优化层已完整交付并收口：**6 任务全完成、6 红线全守约、692 测试全绿、图谱白名单零污染、verified.json 零触碰、engineering_enabled 维持 false、未输出 engineering_approved**。本层仅提升候选方案质量（约束标注 / 明显冲突过滤 / 对比 / 来源链解释 / 人工审核三阶段），真实约束数值、方案选终与报价仍严格保留在「主理人 + 专家经 ESW 窗口线下提交 → 人类终端显式激活」的激活流程之外。按指令**停止**，等待人工解锁。
