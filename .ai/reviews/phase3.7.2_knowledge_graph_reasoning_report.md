# Phase 3.7.2 — Knowledge Graph Query & Reasoning Layer 收口报告

- **阶段**：Phase 3.7.2（Engineering Intelligence Expansion → 知识图谱推理能力）
- **身份**：BOIP AI Chief Architect（只读推理实现；非激活、非审批）
- **日期**：2026-08-03
- **前序**：Phase 3.7.0 ✅ 架构设计 / Phase 3.7.1 ✅ Knowledge Graph Foundation
- **本轮性质**：在 3.7.1 基础层之上新增 **只读推理层**（代码实现）；无真实证据载荷、无数值实现、无审批。
- **停止状态**：✅ 完成即停止；`engineering_enabled=false`；未输出 `engineering_approved`。

---

## 0. 最高红线（本轮 5 条，全部守约）

| # | 红线 | 本轮遵守 |
|---|---|---|
| 1 | 禁止开启 `engineering_enabled` | ✅ 引擎构造即 `safety_invariants_ok()` 只读断言；每次调用前重新断言；真实 `config.yaml` 仍为 `false` |
| 2 | 禁止输出 `engineering_approved` | ✅ 引擎无 `approve`/`engineering_approved` 方法或属性；`trace`/`impact` 输出 `approval_forbidden` 恒 True |
| 3 | 禁止自动修改知识状态 | ✅ 推理层全只读；审计测试验证 node/edge count 不变；绝不 `add_node`/`add_edge`/`delete` |
| 4 | 禁止自动解决冲突 | ✅ `conflict_scan` 复用检测器，`review_required` 恒 True、`auto_resolvable` 恒 False；引擎无 merge/delete/approve |
| 5 | 禁止伪造工程参数 | ✅ 受影响集合仅由图谱结构推导；`Threshold.value` 仍为 `pending_verification`；`CalcAgent` 恒 pending 候选，绝不编造真实计算主体 |

---

## 1. 任务1 — Graph Query Engine

新增 `agents/engineering/knowledge/graph/query.py`，类 `KnowledgeGraphQueryEngine`：

- **构造即断言**（红线①）：`__init__(graph)` 立即调用 `graph.safety_invariants_ok()`，
  若 `engineering_enabled is not False` 抛 `RedLineViolationError`（fail-closed）。
- **`node_query(...)`**：包装 `graph.query(entity_type / attribute_contains / node_id_prefix / pending_build_only)`。
- **`edge_query(...)`**：按 `relation_type` / `source_id` / `target_id` 只读过滤 `graph._edges`；
  不触碰持久化、不写盘。
- **`path_query(start, end, ...)`**：start→end **双向 BFS 寻路**，支持 `relation_types` 白名单 +
  `max_depth` 最大跳数；不可达返回空列表；返回节点序列（每段含 `relation_type`/`via_edge_id`/`direction`）。
- **`impact_analysis(threshold_id)`**：threshold 影响分析（任务3 承载），返回 `ThresholdImpactReport`。

`__init__.py` 追加导出：`KnowledgeGraphQueryEngine` / `KnowledgePathTrace` /
`ThresholdImpactReport` / `ReasoningConflictCandidate` / `CalcAgentCandidate` / `RedLineViolationError`。

---

## 2. 任务2 — 知识路径分析（KnowledgeItem → Threshold → Rule → CalcAgent 候选）

`trace_knowledge_path(knowledge_item_id) -> KnowledgePathTrace`：

- `KnowledgeItem --basis--> Threshold`（out 方向）；
- `Rule --applies--> KnowledgeItem`（in 方向）；
- `CalcAgent` 仅以 **pending 候选**（`CalcAgentCandidate.from_rule(rule_id)`）形式出现，
  `computation_body="pending_verification"`，**绝不编造真实计算主体**（红线⑤）；
- 输出 `candidate analysis`：`requires_human_review=True`、`approval_forbidden=True`，
  **禁止 approve**（红线②）。

---

## 3. 任务3 — 影响分析（threshold impact）

`impact_analysis(threshold_id) -> ThresholdImpactReport`：

- 受影响 `KnowledgeItem`：沿 `used_by`（Threshold→KI，out）+ `basis`（KI→Threshold，in）反向收集；
- 受影响 `Rule`：对每个受影响 KI 沿 `applies`（in 方向）收集；
- 受影响 `Case`：扫描 `Case` 节点 `related_thresholds` 属性包含该 threshold（pending_build 骨架，不编造）；
- 受影响 `CalcAgent 候选`：由受影响 Rule 派生（pending，不编造）；
- `requires_human_review=True`、`approval_forbidden=True`；**仅报告、不处置**（红线③）。

---

## 4. 任务4 — 知识关联推理（relationship traversal）

`reason_associations(node_id, relation_types=...)`：

- 默认支持 `parent_child` / `references` / `cites` / `basis`（双向 `direction="both"`）；
- 复用 `graph.traverse` 做 BFS 遍历；只读。

---

## 5. 任务5 — 冲突保持人工审核

`conflict_scan() -> list[ReasoningConflictCandidate]`：

- 复用 `KnowledgeGraphConflictDetector().detect(graph)`（基础层，review_required 恒 True）；
- 包装为 `ReasoningConflictCandidate`：`review_required` 恒 True、`auto_resolvable` 恒 False、
  `recommended_action="manual_review"`；
- 引擎本身**不提供**任何 `merge` / `delete` / `approve` 方法（红线④）；
- 检测器亦无 merge/delete/approve（3.7.1 延续）。

---

## 6. 任务6 — 测试

新增 `tests/agents/test_knowledge_graph_reasoning.py`，**27 用例全绿**，分 5 类：

- **query 测试**（8）：`node_query` 过滤 / `edge_query` 过滤 / `path_query` 直连·多跳·不可达·`max_depth`；
- **path 测试**（4）：`trace` 返回 Threshold/Rule/CalcAgent 候选、永不审批、CalcAgent pending、拒绝非 KI；
- **impact 测试**（4）：收集 KI/Rule/Case/Agent 候选、仅报告、Agent 候选 pending、拒绝非 Threshold；
- **audit 测试**（4）：引擎无写方法、所有查询全只读（count 不变）、`conflict_scan` 不改图、返回 ReasoningCandidate；
- **red line 测试**（7）：构造断言 `safety_invariants`、无 approve/merge/delete、`approval_forbidden`、`impact` 不伪造、冲突 review_required 恒 True、复用检测器无 merge/delete、输出无 `engineering_approved`/`approved`。

**回归**：既有 `test_knowledge_graph.py`（3.7.1 基础层）33 用例无回归；**合计 60 passed**。

**红线要求满足**：全部用例使用**内存图谱**（无 `store_path`），绝不触碰磁盘 `verified.json` 与 `engineering_enabled`；夹具一律纯标识符，不写任何真实 value 或真实专家身份。

运行命令：
```bash
backend/.venv/bin/python -m pytest tests/agents/test_knowledge_graph.py tests/agents/test_knowledge_graph_reasoning.py -q
# 60 passed
```

---

## 7. 伪造扫描（fabrication scan）

**0 命中**。推理层零真实工程数值、零行业常数硬编码；受影响集合仅由图谱既有结构推导，
不生成任何新数值/结论；`CalcAgent` 仅 pending 候选；`Threshold.value` 仍为 `pending_verification`；
Case/Rule 仍为 `pending_build` 骨架。

---

## 8. 交付物清单

- `agents/engineering/knowledge/graph/query.py`（新增，推理层）
- `agents/engineering/knowledge/graph/__init__.py`（追加导出推理层）
- `tests/agents/test_knowledge_graph_reasoning.py`（新增，27 passed）
- `.ai/reviews/phase3.7.2_knowledge_graph_reasoning_report.md`（本报告）
- `.ai/roadmap_v7.md`（新增 §2.4 + §3.2）
- `.ai/project_status.json`（新增 `phase_3_7.3.7.2` 块 + `_phase_status` / `phase_3_7_status` 更新）

---

## 9. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认；`safety_invariants_ok()` 断言 True）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实证据/参数进入。
- **推理输出均为候选分析**，禁止在 `enabled` 前被当作工程判定依据。
- **按指令停止**：推理层完成即止，不进入编码消费、不开 `enabled`、不输出 `approved`。
- **解锁路径（纯人工）**：主理人 + 专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）
  → 人类终端显式置 `engineering_enabled=true` → 人类对方案/报价作 `Engineering_Approved`；
  此后推理层方可由激活态代码消费其候选输出驱动真实计算。

---

## 10. 后续（非本轮范围）

- Phase 3.7.3+ 候选实现：知识推理的真实消费（阈值转正 / 成本计算 / 方案生成），
  须在主理人 + 专家提交真实双签阈值并显式置 `enabled=true` 后启动。
- `CalcAgent` 真实计算主体补全（当下仅为 pending 候选，红线⑤ 保护）。
