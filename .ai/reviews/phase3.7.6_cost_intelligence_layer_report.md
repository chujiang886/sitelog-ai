# Phase 3.7.6 Cost Intelligence Layer（成本智能层）收口报告

- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-02
- **前置就绪**：Phase 3.7.0 架构 ✅ / 3.7.1 基础层 ✅ / 3.7.2 推理层 ✅ / 3.7.3 案例层 ✅ / 3.7.4 方案生成层 ✅ / 3.7.5 方案约束与优化层 ✅
- **本次交付**：Phase 3.7.6 成本智能层（6 任务全交付，6 红线全守约）
- **激活态**：`engineering_enabled = false`（真实读取 `agents/config.yaml` line 102）；**NO-GO 维持**；未输出 `engineering_approved`

---

## 一、交付概览

Phase 3.7.6 在 3.7.5 方案约束与优化层之上建立「成本智能层」，目标为**建立成本占位估算与来源解释能力**而非做出任何报价/成交/取价结论。本层纯粹承载**BOM 数据壳、成本规则数据壳（禁硬编码价）、占位成本估算、成本来源解释链、成本人工审核队列**；所有真实价格、报价、成交均**不**在本层发生，须经专家双签 + 主理人核准（G6）的来源系统，并在激活后由人类经 `CostReviewQueue.by_human` 终裁。

| 维度 | 真实状态 |
|---|---|
| 阶段 | 🟢 **3.7.6 成本智能层 DONE（2026-08-02）** |
| 新增符号 | `BOMEntity` / `CostRule`（独立数据壳）+ `CostEstimator` / `CostEstimateDraft` / `CostExplanation` / `CostExplanationReport` / `CostReviewQueue` / `CostReviewItem` |
| 图谱白名单影响 | **零**：`BOMEntity`/`CostRule` 为纯数据壳，不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系；`7 实体 / 17 关系` 保持不变 |
| 测试 | 全 agents 套件 **713 passed**（基线 692 → +21，零回归）；`verified.json` 未触碰 |
| 红线 | **6/6 守约**（3.7.6 巩固④自动报价/成交价，并新增⑤伪造市场价格红线拦截 `market_price`） |

---

## 二、六任务交付明细

### 任务1：BOM 模型（`BOMEntity`）
**文件**：`agents/engineering/knowledge/graph/entities.py`

新增 `@dataclass class BOMEntity`，字段：
- `bom_id: str`（必填，唯一标识）
- `solution_id: str`（必填，关联方案）
- `item_type: str = PENDING_PLACEHOLDER`
- `item_name: str = PENDING_PLACEHOLDER`
- `quantity: Any = PENDING_PLACEHOLDER`
- `unit: str = PENDING_PLACEHOLDER`
- `source_ref: str = PENDING_PLACEHOLDER`
- `status: str = PENDING_VERIFICATION`（默认待人工核验转正）

**关键设计**：与 `SolutionConstraint` 一致的**独立纯数据占位壳**，不继承图谱实体契约、`to_node`/`from_node` 不参与、不进入 `KnowledgeGraphEntityType` 枚举、不进入 `_ENTITY_DISPATCH`、不新增关系白名单。因此基座测试 `test_knowledge_graph.py` 的 `EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 断言**无需改动**，图谱白名单零污染。已并入 `__all__` 导出。

### 任务2：成本规则模型（`CostRule`）
**文件**：`agents/engineering/knowledge/graph/entities.py`

新增 `@dataclass class CostRule`，字段：
- `rule_id: str`（必填，唯一标识）
- `source_ref: str = PENDING_PLACEHOLDER`（价格必须有来源）
- `formula: str = PENDING_PLACEHOLDER`
- `unit_price: Optional[Any] = None` ⚠️ **禁止硬编码价格**：默认 `None`，真实单价须经 `source_ref` 指向可信来源（专家双签 + 主理人核准的价目/定额），由人工填充
- `status: str = PENDING_VERIFICATION`（默认待人工核验转正）

**关键设计**：价格必须有来源、禁止硬编码价格（红线⑤），`unit_price` 恒 `None` 占位，绝不落任何硬编码数值。

### 任务3：成本估算器（`CostEstimator`）
**文件**：`agents/engineering/knowledge/graph/solution_cost.py`

四类能力（**仅占位估算，禁止报价/成交价/伪造市场价**）：
- `material_cost(candidate)` → `CostEstimateDraft`
- `labor_cost(candidate)` → `CostEstimateDraft`
- `auxiliary_cost(candidate)` → `CostEstimateDraft`
- `total_estimate(candidate)` → `CostEstimateDraft`

所有方法返回 `CostEstimateDraft`（`requires_human_review=True`；真实金额字段 `material_cost`/`labor_cost`/`auxiliary_cost`/`total_estimate`/ `currency` 恒 `PENDING_PLACEHOLDER`，不填真实价）。构造与方法均断言 `UnifiedActivationGate.safety_invariants_ok()`（红线①/⑥）；继承 `_RedLineForbiddenMixin`，`_FORBIDDEN` 含 `quote`/`pricing`/`deal_price`/`final_price`/`market_price`/`approve`/`select`/`finalize`/`activate`/`engineering_approved`（红线③/④/⑤），访问这些名一律抛 `SolutionRedLineViolationError`。

### 任务4：成本解释链（`CostExplanation`）
**文件**：`solution_cost.py`

`explain(candidate, *, bom_entries=None, cost_rules=None)` 关联四类来源载体 **Solution / BOM / Rule / SourceRef** 构建完整来源链（`CostExplanationReport.source_chain` + 按四类型归类的 `referenced_types`），使成本依据可被人工核验。可选 `repository` 时沿图谱 `traverse` 补充 `SourceRef`/`Rule` 节点。只读聚合不写图、不报价、不成交价（红线③/⑤/⑥），无写图/选终/报价路径。

### 任务5：成本人工审核队列（`CostReviewQueue`）
**文件**：`solution_cost.py`

状态机：`draft` → `reviewing` → `approved_by_human` / `rejected`。
- `submit(candidate, *, draft)`：入队（状态 draft）
- `begin_review(review_id)`：draft → reviewing
- `approve(review_id, *, by_human=False)`：**仅 `by_human=True`** 可进入 `approved_by_human`；AI 调用（`by_human=False`）抛 `SolutionRedLineViolationError`（红线②）
- `reject(review_id, *, by_human=False)`：同守卫（红线④）
- 非法状态转移抛 `SolutionReviewError`（正常业务校验，非红线）

AI 始终无法进入 `approved_by_human`。

### 任务6：测试（`tests/agents/test_knowledge_graph_cost.py`）
**文件**：`tests/agents/test_knowledge_graph_cost.py`（新增，+21 用例）

六类覆盖（用户要求）：
1. **BOM 测试**：默认占位壳 + 不污染图谱白名单
2. **CostRule 测试**：`unit_price` 默认 `None`（禁硬编码价）+ `source_ref` 占位 + 不污染白名单
3. **Estimator 测试**：四方法仅产出占位估算壳（不报价）+ 10 个 forbidden 方法名拦截
4. **Explanation 测试**：关联 Solution/BOM/Rule/SourceRef 四类来源链（含无 repository 变体）
5. **Review 测试**：状态机 draft→reviewing→approved_by_human/rejected，AI 不能进入 approved_by_human
6. **RedLine 测试**：6 条最高红线 fail-closed（含自动报价/成交价/伪造市场价拦截 + BOMEntity/CostRule 不污染图谱白名单）

**红线约束落实**：不修改 `verified.json`（全用例用内存图谱，绝不传 `store_path`）；不开启 `engineering_enabled`（构造/估算/解释/审核全断言 `safety_invariants_ok`）；夹具用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-*），不写真实值。

---

## 三、六红线核验（6/6 守约）

| # | 红线 | 本层落地 | 核验 |
|---|---|---|---|
| ① | 禁止开启 `engineering_enabled` | Estimator/Explanation/ReviewQueue 构造即 `safety_invariants_ok()` 只读断言 | ✅ 真实 `config.yaml` 仍 `false`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | `CostReviewQueue.approve`/`reject` 仅 `by_human=True` 可入 `approved_by_human`/`rejected` | ✅ AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| ③ | 禁止 AI 自动选择最终方案 | Estimator 无 `select`/`finalize`/`winner` | ✅ `_RedLineForbiddenMixin` 拦截 forbidden 方法名；测试显式断言方法不可达 |
| ④ | 禁止自动报价 / 自动成交价格 | 巩固：forbidden 方法名补 `quote`/`pricing`/`deal_price`/`final_price` | ✅ Estimator 访问四者均抛 `SolutionRedLineViolationError`；本层无报价/成交价路径 |
| ⑤ | 禁止伪造市场价格 / 硬编码价格 | 本轮新增：`market_price` 拦截；`CostRule.unit_price` 默认 `None`（禁硬编码）、须有 `source_ref` | ✅ `market_price` 访问抛错；`CostRule` 默认价恒 `None`；估算金额恒 `PENDING_PLACEHOLDER` |
| ⑥ | 禁止绕过 `UnifiedActivationGate` | 构造/估算/解释/审核所有写/决策路径先断言 `safety_invariants_ok()` | ✅ 闸门复用 fail-closed，无绕过设计 |

> 注：3.7.5 将「自动报价」提升为最高红线④（体系 6 条）；3.7.6 巩固④并新增「伪造市场价格」拦截（`market_price` + `CostRule` 禁硬编码价 + 须 `source_ref`），红线体系仍为 **6 条**，已在 `project_status.json` 与 `roadmap_v7.md` 同步刷新计数。

---

## 四、测试报告

```
backend/.venv/bin/python -m pytest tests/agents -q
→ 713 passed in 17.61s   （基线 692 → +21，零回归）
```

- 基座 `test_knowledge_graph.py`：`EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 全部仍成立（BOM/CostRule 零污染白名单）
- 新增 `test_knowledge_graph_cost.py`：21 用例，覆盖 BOM / CostRule / Estimator / Explanation / Review / RedLine 六类
- `verified.json`：未被任何用例修改（仅内存图谱，未传 `store_path`）

---

## 五、与 3.7.5 的兼容性

| 扩展点 | 影响 | 结论 |
|---|---|---|
| `BOMEntity` / `CostRule` 是否进图谱枚举 | 不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系 | 白名单 7 实体 / 17 关系不变 |
| 复用 `_RedLineForbiddenMixin` | 沿用 3.7.4/3.7.5 的 mixin，本层 `_FORBIDDEN` 进一步补 `deal_price`/`final_price`/`market_price` | 自动报价/成交价/伪造市场价拦截到位 |
| 复用异常类型 | `SolutionRedLineViolationError` / `SolutionReviewError` 直接复用，无新增异常类 | 向后兼容，既有 `test_knowledge_graph_constraint.py` 全绿 |
| 包导出 | `graph/__init__.py` 追加成本层 7 个符号 + docstring 3.7.6 | 公开 API 扩展，不影响既有导入 |

---

## 六、激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认，未自动开启）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实价格 / 工程量 / 参数进入。
- **按指令停止**：成本智能层（3.7.6）实现完成即止，不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动选终、不自动报价、不自动成交价、不伪造市场价。
- **解锁路径（纯人工）**：主理人 + 专家经 ESW 窗口提交真实双签价目/定额（来源系统 `verified=true` + 真实 `unit_price`）→ 人类终端显式置 `engineering_enabled=true` → 人类对成本估算作 `Engineering_Approved`（经 `CostReviewQueue.by_human` 终裁）。

---

## 七、交付文件清单

**代码**
- `agents/engineering/knowledge/graph/entities.py`（新增 `BOMEntity` / `CostRule` + `__all__` 导出）
- `agents/engineering/knowledge/graph/solution_cost.py`（新建：`CostEstimator` / `CostEstimateDraft` / `CostExplanation` / `CostExplanationReport` / `CostReviewQueue` / `CostReviewItem` + `_FORBIDDEN` 含 `quote`/`pricing`/`deal_price`/`final_price`/`market_price`）
- `agents/engineering/knowledge/graph/__init__.py`（追加成本层导出 + docstring 3.7.6）

**测试**
- `tests/agents/test_knowledge_graph_cost.py`（新建，+21 用例）

**文档**
- `.ai/reviews/phase3.7.6_cost_intelligence_layer_report.md`（本报告）
- `.ai/roadmap_v7.md`（§1 进度链 / §2.8 3.7.6 / §3.6 红线 6/6）
- `.ai/project_status.json`（`task_status.phase_3_7.3.7.6` 块 + `current_stage.phase_3_7_status` + `phase_3_7._phase_status`，红线计数 → 6/6）

---

## 八、结论

Phase 3.7.6 成本智能层已完整交付并收口：**6 任务全完成、6 红线全守约（巩固④、新增⑤伪造市场价拦截）、713 测试全绿、图谱白名单零污染、verified.json 零触碰、engineering_enabled 维持 false、未输出 engineering_approved**。本层仅建立成本占位估算与来源解释能力（BOM 数据壳 / 成本规则数据壳禁硬编码价 / 占位估算 / 四类来源链 / 仅人工审核队列），真实价格、报价与成交仍严格保留在「主理人 + 专家经 ESW 窗口线下提交来源 → 人类终端显式激活 → `CostReviewQueue.by_human` 终裁」的激活流程之外。按指令**停止**，等待人工解锁。
