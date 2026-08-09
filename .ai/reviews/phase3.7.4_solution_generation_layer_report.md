# BOIP Phase 3.7.4 — Engineering Solution Generation Layer（工程方案生成层）收口报告

- **生成日期**：2026-08-03
- **身份**：BOIP AI Chief Architect
- **阶段**：Phase 3.7.0 ✅ 架构 → 3.7.1 ✅ 基础层 → 3.7.2 ✅ 推理层 → 3.7.3 ✅ 案例层 → 🟢 **3.7.4 方案生成层 DONE**
- **性质**：工程方案生成层**实现**（SolutionCandidate / DesignCandidate / SolutionGenerator / SolutionEvaluator / SolutionReviewQueue + 4 关系 + 测试），基于真实代码，无真实证据载荷、无数值实现、无批准、不开启 `engineering_enabled`、不输出 `engineering_approved`
- **依据**：`.ai/project_status.json`（SSOT，phase_3_7.3.7.4 块）、`.ai/roadmap_v7.md`、真实源码 `agents/engineering/knowledge/graph/*.py` + `tests/agents/test_knowledge_graph_solution.py`

---

## 0. 最高红线（5 条，fail-closed）

| # | 红线 | 本层守约 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | ✅ Generator/Evaluator/ReviewQueue 构造即 `UnifiedActivationGate.safety_invariants_ok()` 断言；`DesignCandidate` 构造断言 `load_engineering_enabled() is False` |
| ② | 禁止输出 `engineering_approved` | ✅ `SolutionReviewQueue.approve` 仅 `by_human=True` 可进入 `approved_by_human`；AI 调用一律抛 `SolutionRedLineViolationError` |
| ③ | 禁止自动选择最终工程方案 | ✅ Generator/Evaluator **无** `select`/`finalize`/`approve`（由 `_RedLineForbiddenMixin` 拦截 forbidden 方法名）；仅产出多候选 |
| ④ | 禁止伪造工程参数 | ✅ `SolutionCandidate.components` 恒 `PENDING_VERIFICATION`、`confidence` 恒 `pending`，不填任何真实方案数值 |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | ✅ 生成/评价/审核所有写/决策路径先断言 `safety_invariants_ok()`；fail-closed |

---

## 1. 任务1：定义 SolutionCandidate 模型 ✅

- 新增枚举值 `KnowledgeGraphEntityType.SOLUTION_CANDIDATE = "SolutionCandidate"`（实体 6→7）。
- 新增常量 `PENDING_VERIFICATION = "pending_verification"`（复用 `PENDING_PLACEHOLDER` 同值，语义独立命名）。
- 新增 `@dataclass SolutionCandidateEntity`，字段：
  `solution_id / input_context / related_cases / related_rules / related_thresholds / components / confidence / verification_status / status`
  - `to_node()` 标 `pending_build=True`（禁止在 enabled 前当就绪实体）；
  - `from_node()` 兼容旧键（`related_case_ids` / `related_rule_ids` / `related_threshold_ids`），平滑迁移；
  - `verification_status` 默认 `PENDING_VERIFICATION`；`from_empty()` 壳构造（仅 `solution_id` 占位）。
- 新增 `@dataclass DesignCandidate`（方案生成器入参契约）：
  - 字段 `design_id / components / metadata / constraints`；
  - `__post_init__` 断言 `load_engineering_enabled() is False`（红线①，fail-closed）。

**交付**：`agents/engineering/knowledge/graph/entities.py`

---

## 2. 任务2：方案生成器 ✅

- 新增 `SolutionGenerator(_RedLineForbiddenMixin)`：
  - 输入 `DesignCandidate` + `KnowledgeGraphRepository` + 可选 `Case` 列表；
  - `generate(design, *, cases=None, persist=True)` 产出 `list[SolutionCandidateEntity]` **多个候选**；
  - 生成前断言 `safety_invariants_ok()`（红线⑤）；
  - `persist=True` 时落 candidate 节点 + 四关系（任务3 关联图谱），纯结构关联、不填真实值；
  - **无 `select` / `finalize`**（由 mixin 拦截，`getattr(gen, "select")` 抛 `SolutionRedLineViolationError`）。

**交付**：`agents/engineering/knowledge/graph/solution_generation.py`

---

## 3. 任务3：方案关联图谱 ✅

- 扩展 `KnowledgeGraphRelationType` 枚举新增 4 值：
  `SOLUTION_CASE="solution_case"` / `SOLUTION_RULE="solution_rule"` / `SOLUTION_THRESHOLD="solution_threshold"` / `SOLUTION_KNOWLEDGE_ITEM="solution_knowledge_item"`
- `RELATIONSHIP_SPECS` 新增 `SolutionCandidate → Case / Rule / Threshold / KnowledgeItem` 四关系（`validate_edge` fail-closed 校验不变）；
- 关系白名单 **13 → 17**；`validate_edge` 报错文案同步为「17 关系白名单」；
- 模块 docstring 同步 13→17 关系列举；
- 基座测试 `test_knowledge_graph.py` 同步 `EXPECTED_ENTITY_TYPES`(6→7) / `EXPECTED_RELATIONS`(13→17) / `EXPECTED_FROM_TO`(+4) / `len(RELATIONSHIP_SPECS)==17`。

**交付**：`agents/engineering/knowledge/graph/relationships.py` + `tests/agents/test_knowledge_graph.py`

---

## 4. 任务4：候选方案评价 ✅

- 新增 `SolutionEvaluator(_RedLineForbiddenMixin)`：
  - `compatibility_check(candidate)`：检查候选引用的 Case/Rule/Threshold 是否都在图谱中存在（只读）；
  - `risk_check(candidate)`：`risk_level="pending_review"`，标记 `components`/`confidence`/`verification_status` 未定（不输出终裁）；
  - `knowledge_trace(candidate)`：从候选节点 BFS 构建知识溯源解释链（候选→Case→Rule/Threshold→KnowledgeItem）；
  - `requires_human_review` 属性恒 `True`；**无 `select`/`finalize`**（mixin 拦截）。
- 报告载体：`SolutionCompatibilityReport` / `SolutionRiskReport` / `SolutionTraceReport`（纯数据 + 解释链，不含决策位）。

**交付**：`agents/engineering/knowledge/graph/solution_generation.py`

---

## 5. 任务5：人工审核接口 ✅

- 新增 `SolutionReviewQueue` 状态机：`candidate → reviewing → approved_by_human / rejected`
- `submit(candidate)` → `begin_review(sid)` → `approve(sid, by_human=True)` / `reject(sid, by_human=True)`
- **AI 不能进入 approved**：`approve` / `reject` 仅 `by_human=True` 可转移，否则抛 `SolutionRedLineViolationError`（红线②/③）；
- 非法状态转移（如 `approve` 在 `candidate` 态、或 `rejected` 后再 `approve`）抛 `SolutionReviewError`；
- 构造即断言 `safety_invariants_ok()`（红线⑤）。

**交付**：`agents/engineering/knowledge/graph/solution_generation.py`

---

## 6. 任务6：测试 ✅

- 新增 `tests/agents/test_knowledge_graph_solution.py`（五类）：
  1. **solution entity 测试**：`SolutionCandidateEntity` 默认值（components=`pending_verification`、confidence=`pending`、pending_build=True）/ roundtrip / `from_empty` / `DesignCandidate` 在禁用态可构造；
  2. **generator 测试**：产出多候选、不自动选终、persist 落 candidate 节点 + 四关系、`cases=[]` 时不伪造候选、`getattr(gen, "approve"/"select"/...)` 抛 `SolutionRedLineViolationError`；
  3. **trace 测试**：`compatibility_check` / `risk_check` / `knowledge_trace` 输出报告且 `requires_human_review=True`、评价器无 `select`/`finalize`；
  4. **review queue 测试**：人工 `approve` 成功（state=`approved_by_human`）、AI `approve`/`reject` 被拦截、非法转移抛 `SolutionReviewError`；
  5. **red line 测试**：4 新关系 `validate_edge` 正常/反置失败/未注册命中「17 关系白名单」、`safety_invariants_ok()` 翻转时 Generator/Evaluator/ReviewQueue/DesignCandidate 构造全部 fail-closed。
- 基座 `test_knowledge_graph.py` 同步 7 实体 / 17 关系断言。
- **不修改 `verified.json` 与 `engineering_enabled`**（全部用例用内存图谱，绝不触碰磁盘 `verified.json`）。

**测试结果**：
- `tests/agents/test_knowledge_graph_solution.py` + `tests/agents/test_knowledge_graph.py`：**56 passed**
- 全 agents 套件：`backend/.venv/bin/python -m pytest tests/agents -q` → **670 passed**，零回归
- 反编造扫描：0 命中（方案层零真实工程数值、零行业常数硬编码；`components`/`confidence` 恒 `PENDING`/`pending`，未编造任何方案实质）

---

## 7. 交付物清单

| 类型 | 路径 |
|---|---|
| 实体扩展 | `agents/engineering/knowledge/graph/entities.py`（SolutionCandidateEntity + DesignCandidate + PENDING_VERIFICATION + 枚举 SOLUTION_CANDIDATE） |
| 关系扩展 | `agents/engineering/knowledge/graph/relationships.py`（4 关系 + 白名单 13→17 + validate_edge 报错 17） |
| 方案生成层 | `agents/engineering/knowledge/graph/solution_generation.py`（SolutionGenerator / SolutionEvaluator / SolutionReviewQueue + 报告载体 + SolutionRedLineViolationError / SolutionReviewError） |
| 包导出 | `agents/engineering/knowledge/graph/__init__.py`（追加方案层导出 + docstring 17 关系） |
| 测试 | `tests/agents/test_knowledge_graph_solution.py`（五类） |
| 基座测试 | `tests/agents/test_knowledge_graph.py`（同步 7 实体/17 关系） |
| 收口报告 | `.ai/reviews/phase3.7.4_solution_generation_layer_report.md` |
| 状态 | `.ai/project_status.json`（phase_3_7.3.7.4 块 + phase_3_7_status 刷新） |
| 路线 | `.ai/roadmap_v7.md`（§2.5 3.7.3 补记 + §2.6 3.7.4 + §3.3/§3.4 红线计数） |

---

## 8. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认，构造期断言守住）。
- **未输出 `engineering_approved`**（ReviewQueue 仅 `by_human=True` 可入 `approved_by_human`）。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实证据/参数进入；方案候选仅 `pending_verification` 骨架。
- **按指令停止**：方案生成层实现完成即止，不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动选终、不伪造工程参数。
- **解锁路径（纯人工）**：主理人+专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 真实方案数值经 `SolutionReviewQueue.by_human` 批准后方可转正。
