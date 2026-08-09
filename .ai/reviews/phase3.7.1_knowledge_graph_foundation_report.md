# BOIP Phase 3.7.1 — Knowledge Graph Foundation Implementation（知识图谱基础层实现）

- **生成**：2026-08-03
- **身份**：BOIP AI Chief Architect
- **性质**：Phase 3.7.1 = **知识图谱基础层实现（Foundation，非激活）**：在 Phase 3.7.0 架构设计（5 实体 + 12 边）之上，落地可运行的图谱基础层——6 实体 Schema / 10 关系 Schema / `KnowledgeGraphRepository` / 单向接入既有 `KnowledgeRepository` / 冲突保护 / 测试套件。本轮为编码实现，但**不开启 `engineering_enabled`、不输出 `engineering_approved`、不伪造工程参数**。
- **依据**：`agents/engineering/knowledge/connector.py`（KnowledgeItem 13 字段七态）、`agents/engineering/knowledge/repository.py`（既有 Repository + 审计）、`agents/engineering/thresholds/schema.py`（ThresholdSourceRef / ThresholdStatus）、`agents/engineering/knowledge/experts.json`（专家字段）、`agents/engineering/knowledge/intelligence/conflict.py`（review_required 恒 True）。
- **权威声明**：本文件为 Phase 3.7.1 唯一收口报告；SSOT `.ai/project_status.json`（`task_status.phase_3_7.3.7.1`）与 `.ai/roadmap_v7.md` 同步更新。

---

## 0. 执行事实声明（基于真实代码）

本轮实现**完全锚定真实代码**，未虚构任何工程数值、未硬编码行业常数、未编造专家身份：

- 6 实体中，`KnowledgeItem` 复用 `connector.KnowledgeItem`（13 字段七态）；`Threshold` 复用 `thresholds.schema.ThresholdSourceRef` + 治理态，其 `value` 构造即 `pending_verification`；`Expert` 复用 `experts.json` 字段；`SourceRef` 复用 `ThresholdSourceRef`；`Case` / `Rule` 为**待建骨架**（`pending_build=True`），仅承载标识符与占位属性，**不填真实值**。
- 10 关系 Schema 的起止实体约束，与既有 `KnowledgeRelationshipEngine`（4 关系只读发现）及 `connector` 谱系语义一致。
- `KnowledgeGraphRepository` 的审计模型对齐既有 `KnowledgeEventLog`（append-only，白名单拒 `approved`）。
- 冲突保护延续 3.3.9 `KnowledgeConflictDetector` 的 `review_required` 恒 True 设计。

**红线核验（5/5 守约）**：见 §6。

---

## 1. 任务1 — KG 实体模型（6 实体 Schema）

| 实体 | 真实代码锚点 | 本轮实现 | 红线处理 |
|---|---|---|---|
| `KnowledgeItem` | `connector.KnowledgeItem`（13 字段 + 7 态） | `KnowledgeItemEntity` 包裹真实 item，`to_node()` 落图 | 直接复用，零改写 |
| `Threshold` | `thresholds.schema.ThresholdSourceRef` + `ThresholdStatus` | `ThresholdEntity`；`value` 字段构造即 `pending_verification` | 不提供任何填真实值的方法 |
| `Expert` | `experts.json`（expert_id/domains/qualification_status/sign_scope/sod_role/valid_until） | `ExpertEntity` 承载资料壳 | `qualification_status` 严禁 AI 翻转；不落签 |
| `SourceRef` | `thresholds.schema.ThresholdSourceRef` | `SourceRefEntity` 包裹结构化引用 | 缺引用时停留 pending |
| `Case` | 无真实代码（成本路线待建） | `CaseEntity`（`pending_build=True` 骨架） | 不填真实案例值/成本 |
| `Rule` | 无真实代码（规则路线待建） | `RuleEntity`（`pending_build=True` 骨架，`expression`=`pending_verification`） | 不填真实计算式/单价 |

统一承载：`graph/entities.py` 的 `GraphNode`（节点通用结构，含 `entity_type` / `label` / `attributes` / 审计字段 `created_at`/`updated_at`/`version`/`content_hash`/`actor`/`pending_build`）。各实体经 `to_node()` 落图、经 `from_node()` 还原；`entity_to_node()` 调度。

---

## 2. 任务2 — KG 关系模型（10 关系 Schema）

`graph/relationships.py` 定义 `RelationSpec` + `RELATIONSHIP_SPECS`，每关系含 `from_entity` / `to_entity` 约束、`required_attrs`、`invariant`。

| # | 关系 | from → to | 必需属性 | 不变量要点 |
|---|---|---|---|---|
| 1 | references | KnowledgeItem → KnowledgeItem | — | 不传递签署效力 |
| 2 | authored_by | KnowledgeItem → Expert | — | AI 不代签 |
| 3 | parent_child | KnowledgeItem → KnowledgeItem | no_cycle | 谱系禁环 |
| 4 | sourced_from | KnowledgeItem → SourceRef | standard, clause | 缺引用停留 pending |
| 5 | used_by | Threshold → KnowledgeItem | — | value 恒 pending 直至转正 |
| 6 | applies | Rule → KnowledgeItem | — | 待建骨架，不触发计算 |
| 7 | cites | KnowledgeItem → SourceRef | — | 不替代 sourced_from 校验 |
| 8 | basis | KnowledgeItem → Threshold | — | 阈值转正须双签+G6 |
| 9 | witnessed_by | KnowledgeItem → Expert | — | AI 不代见证 |
| 10 | signs | Expert → KnowledgeItem | — | 真实专家经正式流程驱动 |

`validate_edge(edge, node_index)` 在 `add_edge` 时校验：关系未注册 / 起止节点缺失 / 实体类型不符 / 缺必需属性 → 一律抛 `ValueError`（**fail-closed**，绝不静默降级或自动改写）。

---

## 3. 任务3 — Graph Repository

`graph/repository.py` 的 `KnowledgeGraphRepository`：

- `add_node(entity|GraphNode)`：入图（版本=1；同 id 视为 update，version+1，保留历史版本快照）。
- `add_edge(GraphEdge)`：先 `validate_edge` 校验 → 入图（版本=1；同 id update）；约束违例抛 `ValueError`。
- `query(entity_type / attribute_contains / node_id_prefix / pending_build_only)`：多维过滤。
- `traverse(start, relation_types, direction, max_depth)`：BFS 遍历，返回 `[(level, node_id, relation_type, via_edge_id)]`，`direction` 支持 out/in/both。
- `history(target_id)`：返回该节点/边审计时间线。
- **审计**：`GraphAuditLog` append-only，记录 `who / when / hash / version`；动作白名单 `add_node / update_node / add_edge / update_edge`，**显式拒绝 `merge / delete / approve`**。
- **持久化**：自身专属 `knowledge_graph.json`，**绝不**触碰 `verified.json` / `engineering_enabled` / `release_approvals`。
- `safety_invariants_ok()`：只读断言 `load_engineering_enabled() is False`。

---

## 4. 任务4 — 接入现有 KnowledgeRepository（单向）

`graph/integration.py` 的 `KnowledgeRepositoryToGraphSync`：

- 流程：`KnowledgeItem（connector）→ KnowledgeRepository（既有落库）→ KnowledgeGraph（本层）`。
- **单向**：图谱不回写 Repository；`KnowledgeRepository` 仍是唯一事实源（与 3.3.8 一致）。
- `sync_item(repo, knowledge_id)`：读取当前版本 `KnowledgeItem` → 落 `KnowledgeItem` 节点 → 派生观察边（authored_by / sourced_from / cites / parent_child / basis）。
- **不编造**：仅当标识符非 `pending_verification` 时建**存根节点**（仅承载标识符，`value` 恒 pending）；`pending` 标识符直接跳过对应边，避免伪造。
- 依赖方向：本模块 import 既有 `repository.KnowledgeRepository` 与 graph 包；graph 包不反向 import repository，**无循环依赖**。

**验证（测试 `test_integration_single_direction_no_writeback` / `test_integration_no_fabrication_on_pending`）**：同步后 Repository 条目数不变（0 回写）；pending 标识符下仅 1 个 KnowledgeItem 节点入图、0 边。

---

## 5. 任务5 — 冲突保护

`graph/conflict.py` 的 `KnowledgeGraphConflictDetector`（沿用 3.3.9 的 `review_required` 恒 True 设计）：

- 图谱级冲突类型：`duplicate_node`（同 entity_type+label 不同 id）、`dangling_edge`（起/止缺失）、`type_mismatch`（约束复核）、`pending_build_edge`（生产类关系引用待建骨架节点）。
- **所有冲突 `review_required` 恒定 `True`**。
- **本类不提供 `merge` / `delete` / `approve` / `auto_resolve` 任何方法**（红线：禁止自动 merge/delete/approve）。
- `detect()` 不写盘、不调 `add_node`/`add_edge`、不输出任何解决结论；冲突仅进入"待人工复核"队列（AI 不代专家审核）。

**验证（测试 `test_conflict_review_required_always_true` / `test_conflict_detector_has_no_merge_delete_approve` / `test_detect_does_not_mutate_graph`）**：review_required 恒 True；无 merge/delete/approve 方法；detect 前后节点/边数不变。

---

## 6. 任务6 — 测试 + 红线守约

新增 `tests/agents/test_knowledge_graph.py`，**33 用例全绿**，分五类：

1. **schema 测试**：6 实体类型齐全、10 关系规格齐全、起止约束正确、sourced_from 必需属性正确；
2. **entity 测试**：六实体 `to_node`/`from_node` 往返、Case/Rule `pending_build=True`、不伪造值；
3. **relationship 测试**：边校验 fail-closed（类型不符 / 节点缺失 / 未注册 / 缺必需属性一律抛错）；
4. **audit 测试**：add_node/add_edge 记审计、history 返回、update 递增版本、禁止 merge/delete/approve、query/traverse；
5. **red line 测试**：`engineering_enabled=False` 只读断言、冲突 `review_required` 恒 True、冲突检测器无 merge/delete/approve、不写 verified.json、单向接入不回写、pending 不编造。

**回归**：既有知识测试 `test_knowledge_repository.py` / `test_knowledge_connector.py` / `test_knowledge_intelligence.py` 共 **70 用例无回归**。合计 **103** 知识域用例通过。

测试**不修改 `verified.json`**（全部用例用内存图谱，不传 `store_path`），**不开启 `engineering_enabled`**。

### 红线守约（5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 禁止开启 `engineering_enabled` | ✅ 真实 `config.yaml` 仍为 `false`；`safety_invariants_ok()` 断言 True |
| 2 | 禁止输出 `engineering_approved` | ✅ 全文未输出 approved；审计白名单拒 `approved` |
| 3 | 禁止伪造工程参数 | ✅ KG 基础层零真实数值；`Threshold.value`/Case/Rule 恒 `pending_verification`；集成仅建存根不编造 |
| 4 | 禁止 AI 代替专家审核 | ✅ `Expert` 仅资料壳；`signs` 边由真实专家驱动，集成仅建 authored_by/witnessed_by 观察边；冲突 `review_required` 恒 True |
| 5 | 禁止绕过 `UnifiedActivationGate` | ✅ 沿用 fail-closed 闸门；图谱层不产出任何批准态；边校验 fail-closed |

---

## 7. 交付物清单

| 类型 | 路径 |
|---|---|
| 实体 Schema | `agents/engineering/knowledge/graph/entities.py` |
| 关系 Schema | `agents/engineering/knowledge/graph/relationships.py` |
| Graph Repository | `agents/engineering/knowledge/graph/repository.py` |
| 单向接入 | `agents/engineering/knowledge/graph/integration.py` |
| 冲突保护 | `agents/engineering/knowledge/graph/conflict.py` |
| 包导出 | `agents/engineering/knowledge/graph/__init__.py` |
| 测试 | `tests/agents/test_knowledge_graph.py`（33 passed） |
| 收口报告 | `.ai/reviews/phase3.7.1_knowledge_graph_foundation_report.md` |
| 路线图 | `.ai/roadmap_v7.md`（更新 §2.3） |
| SSOT | `.ai/project_status.json`（`task_status.phase_3_7.3.7.1` + `current_stage.phase_3_7_status`） |

---

## 8. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实证据/参数进入。
- **按指令停止**：知识图谱基础层实现完成即止，不进入激活、不开 enabled、不输出 approved。
- **解锁路径（纯人工）**：主理人+专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 人类对方案/报价作 `Engineering_Approved`；届时可启动知识推理（3.7.0 路线④）/ 成本计算（路线③）等基于图谱的后续实现。
