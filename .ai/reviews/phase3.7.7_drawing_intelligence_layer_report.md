# Phase 3.7.7 Drawing Intelligence Layer（图纸智能解析层）收口报告

- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-02
- **前置就绪**：Phase 3.7.0 架构 ✅ / 3.7.1 基础层 ✅ / 3.7.2 推理层 ✅ / 3.7.3 案例层 ✅ / 3.7.4 方案生成层 ✅ / 3.7.5 方案约束与优化层 ✅ / 3.7.6 成本智能层 ✅
- **本次交付**：Phase 3.7.7 图纸智能解析层（6 任务全交付，6 红线全守约）
- **激活态**：`engineering_enabled = false`（真实读取 `agents/config.yaml` line 102）；**NO-GO 维持**；未输出 `engineering_approved`

---

## 一、交付概览

Phase 3.7.7 在 3.7.6 成本智能层之上建立「图纸智能解析层」，目标为**建立图纸解析占位壳、视觉分析只读壳、人工尺寸审核队列与知识图谱只读关联能力**而非做出任何尺寸确认/工程参数生成/报价结论。本层纯粹承载**DesignCandidate 增强字段（占位）、图纸解析占位壳、视觉分析只读壳、人工审核状态机、知识关联只读报告**；所有真实尺寸、工程参数、报价**不**在本层发生，须经专家双签 + 主理人核准（G6）写入来源系统，并在激活后由人类经 `DesignReviewQueue.by_human` 终裁。

| 维度 | 真实状态 |
|---|---|
| 阶段 | 🟢 **3.7.7 图纸智能层 DONE（2026-08-02）** |
| 新增符号 | `DesignCandidate` 增强 7 字段 + `DrawingParser` / `ParsedDesignDraft` / `VisionAdapter` / `VisionAnalysisReport` / `DesignReviewQueue` / `DesignReviewItem` / `DesignGraphConnector` / `DesignKnowledgeLinkReport` |
| 图谱白名单影响 | **零**：`DesignCandidate` 是方案生成器契约入参（非持久化图谱节点，不进 `KnowledgeGraphEntityType` / 不进 `_ENTITY_DISPATCH` / 不新增关系），`7 实体 / 17 关系` 保持不变 |
| 测试 | 全 agents 套件 **740 passed**（基线 713 → +27，零回归）；`verified.json` 未触碰 |
| 红线 | **6/6 守约**（3.7.7 将「自动确认图纸尺寸」「自动生成真实工程参数」提升为最高红线③/④，并保留⑤自动报价拦截 `quote`/`pricing`，移除 3.7.6 的「自动成交价 / 伪造市场价」——红线清单仍为 6 条） |

---

## 二、六任务交付明细

### 任务1：DesignCandidate 增强模型
**文件**：`agents/engineering/knowledge/graph/entities.py`（`DesignCandidate`，line 566）

在既有 `design_id` / `components` / `metadata` / `constraints` 之后扩展 7 个新字段（全部默认占位）：
- `source_files: list[str] = field(default_factory=list)`
- `geometry: Any = PENDING_PLACEHOLDER`（红线③：AI 不自动确认图纸尺寸）
- `opening_type: str = PENDING_PLACEHOLDER`
- `glass_config: Any = PENDING_PLACEHOLDER`（红线④：AI 不自动生成真实工程参数）
- `profile_config: Any = PENDING_PLACEHOLDER`（红线④）
- `confidence: Any = PENDING_PLACEHOLDER`（红线⑤：解析须带 confidence 占位，AI 不输出报价依据）
- `verification_status: str = PENDING_VERIFICATION`（默认待人工核验转正）

**关键设计**：`DesignCandidate` 是**方案生成器契约入参**，**非持久化图谱节点**——不继承图谱实体契约、`to_node`/`from_node` 不参与、不进入 `KnowledgeGraphEntityType` 枚举、不进入 `_ENTITY_DISPATCH`、不新增关系白名单。因此基座测试 `test_knowledge_graph.py` 的 `EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 断言**无需改动**，图谱白名单零污染（零回归风险）。`__post_init__` 红线①断言（`load_engineering_enabled() is not False → RuntimeError`）保留。

### 任务2：图纸解析适配器（`DrawingParser`）
**文件**：`agents/engineering/knowledge/graph/solution_drawing.py`

解析 PDF / CAD / Image 图纸 → `DesignCandidate`。私有 `_parse` 共产出带 `source_ref` + `confidence` 占位的 `DesignCandidate`：
- `parse_pdf(file_path, *, design_id, source_ref=None)`
- `parse_cad(file_path, *, design_id, source_ref=None)`
- `parse_image(file_path, *, design_id, source_ref=None)`

所有解析结果 `geometry` / `opening_type` / `glass_config` / `profile_config` 恒为 `PENDING_PLACEHOLDER`（红线③/④），`verification_status` 默认 `PENDING_VERIFICATION`，`metadata` 必带 `source_ref` + `parse_format` + `confidence` 占位（溯源 + 不确定性标记）。构造与每次解析均断言 `UnifiedActivationGate.safety_invariants_ok()`（红线①/⑥）；继承 `_RedLineForbiddenMixin`，`_FORBIDDEN = _FORBIDDEN_DRAWING_METHODS`（红线②/③/④/⑤），访问 forbidden 名一律抛 `SolutionRedLineViolationError`。

### 任务3：Vision 接口（`VisionAdapter`）
**文件**：`solution_drawing.py`

提供图像/图纸视觉分析（**禁止直接进入工程结论**）：
- `image_analysis(image_path, *, source_ref=None)` → `VisionAnalysisReport`
- `drawing_analysis(drawing_path, *, source_ref=None)` → `VisionAnalysisReport`

`_analyze` 仅产出 `VisionAnalysisReport`（`geometry_hint` / `opening_hint` 恒 `PENDING_PLACEHOLDER`，`requires_engineering_review=True`，不输出真实尺寸/参数/报价，红线③/④/⑤）。构造与每次分析均断言 `safety_invariants_ok()`；继承 `_RedLineForbiddenMixin`。Vision 适配器可无 `repository` 构造（只读描述壳）。

### 任务4：尺寸审核流程（`DesignReviewQueue`）
**文件**：`solution_drawing.py`

状态机：`parsed` → `reviewing` → `verified_by_human` / `rejected`（载体 `DesignReviewItem`）：
- `submit(candidate)`：入队（状态 parsed）
- `begin_review(review_id)`：parsed → reviewing
- `verify(review_id, *, by_human=False)`：**仅 `by_human=True`** 可进入 `verified_by_human`；AI 调用（`by_human=False`）抛 `SolutionRedLineViolationError`（红线②）
- `reject(review_id, *, by_human=False)`：同守卫（红线②）
- 非法状态转移抛 `SolutionReviewError`（正常业务校验，非红线）

AI 始终无法进入 `verified_by_human`（`decided_by` 恒 `"human_reviewer"`）。构造断言 `safety_invariants_ok()`（红线①/⑥）。

### 任务5：知识图谱连接（`DesignGraphConnector`）
**文件**：`solution_drawing.py`

`link(candidate, *, solution_ids, case_ids, knowledge_item_ids, source_ref_ids)` 只读聚合四类载体 id（Solution / Case / KnowledgeItem / SourceRef + 解析期 `source_ref`），产出 `DesignKnowledgeLinkReport`（`requires_human_review=True`）。**不写图、不新增关系到 17 白名单**（可选 `repository` 时仅 `get_node` 校验实体类型，绝不落边）。构造断言 `safety_invariants_ok()`（红线①/⑥）。

### 任务6：测试（`tests/agents/test_knowledge_graph_drawing.py`）
**文件**：`tests/agents/test_knowledge_graph_drawing.py`（新增，+27 用例）

六类覆盖（用户要求）：
1. **DrawingParser 测试**：parametrize pdf/cad/image ×3（返回 DesignCandidate / 带 source_ref + confidence 占位 / 真实尺寸恒 PENDING_PLACEHOLDER / 显式 source_ref 透传）
2. **DesignCandidate 增强测试**：新字段默认占位 + 增强模型不进图谱白名单（`len(RELATIONSHIP_SPECS)==17`）
3. **VisionAdapter 测试**：image / drawing / 无 repository 变体（geometry_hint / opening_hint 恒占位）
4. **DesignReviewQueue 测试**：submit/begin_review/verify_by_human_ok/verify_ai_blocked/reject_by_human_ok/reject_ai_blocked/invalid_transition_rejected
5. **DesignGraphConnector 测试**：四类关联聚合 / 只读不新增关系（`len(RELATIONSHIP_SPECS)==17`）
6. **RedLine 测试**：构造期 `safety_invariants_ok` 翻转即抛错 / forbidden 尺寸与参数方法拦截 / forbidden 报价与批准方法拦截 / 增强 DesignCandidate 不污染图谱白名单

**红线约束落实**：不修改 `verified.json`（全用例用内存图谱，绝不传 `store_path`）；不开启 `engineering_enabled`（所有构造/解析/分析/审核/连接全断言 `safety_invariants_ok`）；夹具用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / DRAW-1 / D-1），不写真实值。

---

## 三、六红线核验（6/6 守约）

| # | 红线 | 本层落地 | 核验 |
|---|---|---|---|
| ① | 禁止开启 `engineering_enabled` | Parser/Vision/ReviewQueue/GraphConnector 构造即 `safety_invariants_ok()` 只读断言；`DesignCandidate.__post_init__` 断言未启用 | ✅ 真实 `config.yaml` 仍 `false`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | `DesignReviewQueue.verify`/`reject` 仅 `by_human=True` 可入 `verified_by_human`/`rejected` | ✅ AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| ③ | 禁止自动确认图纸尺寸 | 本轮新增：forbidden 方法名补 `confirm_dimension`；解析结果 `geometry`/`opening_type` 恒 `PENDING_PLACEHOLDER` | ✅ `confirm_dimension` 访问抛错；Parser 输出尺寸位恒占位，AI 不确认图纸尺寸 |
| ④ | 禁止自动生成真实工程参数 | 本轮新增：forbidden 方法名补 `generate_engineering_param`；`glass_config`/`profile_config` 恒 `PENDING_PLACEHOLDER` | ✅ `generate_engineering_param` 访问抛错；工程参数位恒占位，AI 不生成真实参数 |
| ⑤ | 禁止自动报价 | 保留：forbidden 方法名 `quote`/`pricing`（移除 3.7.6 的 `deal_price`/`final_price`/`market_price`） | ✅ `quote`/`pricing` 访问抛 `SolutionRedLineViolationError`；本层无报价路径 |
| ⑥ | 禁止绕过 `UnifiedActivationGate` | 构造/解析/分析/审核/连接所有决策路径先断言 `safety_invariants_ok()` | ✅ 闸门复用 fail-closed，无绕过设计 |

> 注：3.7.7 将「自动确认图纸尺寸」「自动生成真实工程参数」提升为最高红线③/④；移除 3.7.6 的「自动成交价 / 伪造市场价」红线（该两项属成本层范畴，本层不涉报价/成交）。红线体系仍为 **6 条**，已在 `project_status.json` 与 `roadmap_v7.md` 同步刷新计数。

---

## 四、测试报告

```
backend/.venv/bin/python -m pytest tests/agents -q
→ 740 passed in 21.60s   （基线 713 → +27，零回归）
```

- 基座 `test_knowledge_graph.py`：`EXPECTED_ENTITY_TYPES`(7) / `EXPECTED_RELATIONS`(17) / `len(RELATIONSHIP_SPECS)==17` 全部仍成立（`DesignCandidate` 增强零污染白名单）
- 新增 `test_knowledge_graph_drawing.py`：27 用例，覆盖 DrawingParser / DesignCandidate / Vision / Review / GraphConnector / RedLine 六类
- `verified.json`：未被任何用例修改（仅内存图谱，未传 `store_path`）

---

## 五、与 3.7.6 的兼容性

| 扩展点 | 影响 | 结论 |
|---|---|---|
| `DesignCandidate` 增强是否进图谱枚举 | 不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系 | 白名单 7 实体 / 17 关系不变 |
| 复用 `_RedLineForbiddenMixin` | 沿用 3.7.4/3.7.5/3.7.6 的 mixin，本层 `_FORBIDDEN` 补 `confirm_dimension`/`generate_engineering_param`、移除 `deal_price`/`final_price`/`market_price` | 尺寸/参数/报价拦截到位 |
| 复用异常类型 | `SolutionRedLineViolationError` / `SolutionReviewError` 直接复用，无新增异常类 | 向后兼容，既有 `test_knowledge_graph_cost.py` / `test_knowledge_graph_constraint.py` 全绿 |
| 包导出 | `graph/__init__.py` 追加图纸智能层 9 个符号 + docstring 3.7.7 | 公开 API 扩展，不影响既有导入 |

---

## 六、激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认，未自动开启）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实尺寸 / 工程参数 / 报价进入。
- **按指令停止**：图纸智能层（3.7.7）实现完成即止，不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动确认图纸尺寸、不自动生成真实工程参数、不自动报价、不绕过 `UnifiedActivationGate`。
- **解锁路径（纯人工）**：主理人 + 专家经 ESW 窗口提交真实双签图纸尺寸/型材/玻璃来源（来源系统 `verified=true`）→ 人类终端显式置 `engineering_enabled=true` → 人类对尺寸核验作终裁（经 `DesignReviewQueue.by_human`）→ 真实工程参数经激活流程写入。

---

## 七、交付文件清单

**代码**
- `agents/engineering/knowledge/graph/entities.py`（扩展 `DesignCandidate` 7 字段 + 红线③/④ docstring + `__all__` 不变）
- `agents/engineering/knowledge/graph/solution_drawing.py`（新建：`DrawingParser` / `ParsedDesignDraft` / `VisionAdapter` / `VisionAnalysisReport` / `DesignReviewQueue` / `DesignReviewItem` / `DesignGraphConnector` / `DesignKnowledgeLinkReport` + `_FORBIDDEN_DRAWING_METHODS` 含 `approve`/`select`/`finalize`/`activate`/`engineering_approved`/`quote`/`pricing`/`confirm_dimension`/`generate_engineering_param`）
- `agents/engineering/knowledge/graph/__init__.py`（追加图纸智能层导出 + docstring 3.7.7）

**测试**
- `tests/agents/test_knowledge_graph_drawing.py`（新建，+27 用例）

**文档**
- `.ai/reviews/phase3.7.7_drawing_intelligence_layer_report.md`（本报告）
- `.ai/roadmap_v7.md`（§1 进度链 / §2.9 3.7.7 / §3.7 红线 6/6）
- `.ai/project_status.json`（`task_status.phase_3_7.3.7.7` 块 + `current_stage.phase_3_7_status` + `phase_3_7._phase_status`，红线计数 → 6/6）

---

## 八、结论

Phase 3.7.7 图纸智能解析层已完整交付并收口：**6 任务全完成、6 红线全守约（新增③自动确认图纸尺寸、④自动生成真实工程参数拦截，保留⑤自动报价拦截）、740 测试全绿、图谱白名单零污染、verified.json 零触碰、engineering_enabled 维持 false、未输出 engineering_approved**。本层仅建立图纸解析占位壳、视觉分析只读壳、人工尺寸审核队列与知识图谱只读关联能力（`DesignCandidate` 增强字段 / `DrawingParser` / `VisionAdapter` / `DesignReviewQueue` / `DesignGraphConnector`），真实尺寸、工程参数与报价仍严格保留在「主理人 + 专家经 ESW 窗口线下提交来源 → 人类终端显式激活 → `DesignReviewQueue.by_human` 终裁」的激活流程之外。按指令**停止**，等待人工解锁。
