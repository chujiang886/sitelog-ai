# BOIP Phase 3.7.3 — Case Knowledge Layer（案例知识层）收口报告（补记）

- **生成日期**：2026-08-03（补记；代码已于 3.7.3 当轮落盘，本轮随 3.7.4 一并补齐收口文档）
- **身份**：BOIP AI Chief Architect
- **阶段**：Phase 3.7.1 ✅ 基础层 → 3.7.2 ✅ 推理层 → 🟢 **3.7.3 案例层 DONE**
- **性质**：案例知识层**实现**（`CaseEntity` + `CaseLifecycle` 状态机 + 3 关系扩展），基于真实代码，无真实证据载荷、无数值实现、无审批、不开启 `engineering_enabled`、不输出 `engineering_approved`
- **依据**：`.ai/project_status.json`（SSOT，phase_3_7.3.7.3 块）、`.ai/roadmap_v7.md`、真实源码 `agents/engineering/knowledge/graph/{entities,relationships,case_lifecycle}.py`

---

## 0. 红线守约（本轮 5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ 复用 `safety_invariants_ok()` 只读断言 True；真实 `config.yaml` 仍为 `false` |
| 2 | 不输出 `engineering_approved` | ✅ 案例层无任何批准态；`CaseLifecycle` 仅人工推进 |
| 3 | 不伪造真实案例 | ✅ Case 字段默认空串/`PENDING_PLACEHOLDER`；`from_empty` 仅壳，零真实值 |
| 4 | AI 不代替专家审核 | ✅ `CaseLifecycle.advance` 默认守卫，AI 不自动转移；`rule_expert` 签署位由真实专家驱动 |
| 5 | 不绕过 `UnifiedActivationGate` | ✅ 沿用 fail-closed 闸门；边校验 fail-closed |

---

## 1. 任务1：案例实体 ✅

- 新增 `@dataclass CaseEntity`，字段：
  `case_id / project_ref / environment / title / description / domain / design_context / solution / outcome / lessons / linked_thresholds / linked_rules / linked_experts / lifecycle_stage / status`
  - `to_node()` 标 `pending_build=True`（禁止在 enabled 前当就绪实体）；
  - `from_node()` 兼容旧键 `related_thresholds`（平滑迁移）；
  - `from_empty(case_id, ...)` 壳构造（仅 case_id 占位，不填真实值，红线③）。

**交付**：`agents/engineering/knowledge/graph/entities.py`

---

## 2. 任务2：案例生命周期 ✅

- 新增 `CaseLifecycleStage`：`Captured` / `Verified_Source` / `Expert_Reviewed` / `Engineering_Referenced`
- 新增 `CaseLifecycle`：
  - `advance(by_human_reviewer=False)` 守卫，非法转移抛 `CaseLifecycleError`；
  - `requires_human_review` 恒 `True`；真实推进仅人工驱动（红线⑤）。
- 新增 `CaseLifecycleError(ValueError)`。

**交付**：`agents/engineering/knowledge/graph/case_lifecycle.py`

---

## 3. 任务3：案例链路关系 ✅

- 扩展 `KnowledgeGraphRelationType` 枚举新增 3 值：`CASE_ITEM` / `THRESHOLD_RULE` / `RULE_EXPERT`
- `RELATIONSHIP_SPECS` 新增：
  - `case_item`：Case → KnowledgeItem（案例→KG 链路起点）
  - `threshold_rule`：Threshold → Rule（Threshold→Rule 链路）
  - `rule_expert`：Rule → Expert（Rule→Expert 链路，签署位）
- `validate_edge` fail-closed 校验不变；关系白名单 **10 → 13**。

**交付**：`agents/engineering/knowledge/graph/relationships.py`

---

## 4. 任务4：测试 ✅

- 新增 Case 实体 / 生命周期 / 关系 / red line 用例；
- 基座 `test_knowledge_graph.py` 同步 6 实体 / 13 关系断言（`EXPECTED_ENTITY_TYPES` / `EXPECTED_RELATIONS` / `EXPECTED_FROM_TO` / `len(RELATIONSHIP_SPECS)==13`）；
- 不碰 `verified.json` 与 `engineering_enabled`；
- 既有套件无回归（随 3.7.4 合并后 agents 全套 **670 passed**）。

---

## 5. 交付物清单

| 类型 | 路径 |
|---|---|
| 案例实体 + 生命周期 | `agents/engineering/knowledge/graph/entities.py`（CaseEntity）+ `case_lifecycle.py` |
| 关系扩展 | `agents/engineering/knowledge/graph/relationships.py`（case_item / threshold_rule / rule_expert，白名单 10→13） |
| 包导出 | `agents/engineering/knowledge/graph/__init__.py`（追加 CaseLifecycle 导出） |
| 测试 | `tests/agents/test_knowledge_graph.py`（Case 实体/生命周期/关系 用例） |
| 收口报告 | `.ai/reviews/phase3.7.3_case_knowledge_layer_report.md`（本轮补记） |
| 状态 | `.ai/project_status.json`（phase_3_7.3.7.3 块） |
| 路线 | `.ai/roadmap_v7.md`（§2.5 3.7.3 补记 + §3.3 红线计数） |

---

## 6. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；案例真实内容须人工经 ESW 窗口导入。
- 案例生命周期仅人工驱动；AI 不自动推进（Captured → Verified_Source → Expert_Reviewed → Engineering_Referenced）。
