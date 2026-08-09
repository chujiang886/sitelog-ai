# BOIP Phase 3.4.0 — Engineering Knowledge Activation Readiness Architecture（激活准备架构）

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **性质**：**设计-only（只设计，不执行）**。本阶段不新增可执行代码、不修改 `verified.json`、不开 `engineering_enabled`、不输出 `engineering_approved`、不创建 `ReleaseApproval`。
- **依据**：`agents/engineering/gate/enable_gate.py`（G1–G6 阈值门禁语义，Phase 3.2.5）、`agents/engineering/knowledge/repository.py`（3.3.8 Repository/审计）、`agents/engineering/knowledge/connector.py`（KnowledgeItem 七态）。
- **当前激活状态**：`engineering_enabled = False`；3.3.6 激活复核 verdict = **NO-GO**（维持关闭）；G1–G6 全 FAIL 维持关闭。

---

## 1. 架构变化（Architecture Changes）

本阶段在既有"工程审核闭环容器"（Phase 3.2）+ "知识资产仓库"（Phase 3.3.8）之上，**叠加一层"知识激活准备架构"**——它定义"一条 KnowledgeItem 何时、凭什么条件才能成为 Engineering AI 可权威引用的依据"，并明确 AI 的读取边界与失效回滚路径。

```
                         ┌─────────────────────────────────────────┐
                         │      Engineering Knowledge Layer         │
                         │                                           │
  Obsidian Vault ──▶ Connector ──▶ KnowledgeItem ──▶ Repository      │
                         │                    │            │          │
                         │              [3.3.9 智能层]      │          │
                         │         Quality / Relationship / Conflict  │
                         │                    │            │          │
                         │                    ▼            ▼          │
                         │        ActivationGate (G1–G6, 设计) ◀──────┘
                         │              /  Consumption Policy  \      │
                         │             /   AI Read Boundary    \     │
                         │            /      Rollback Chain     \    │
                         └─────────────────────────────────────────┘
                                          │
                                          ▼  (仅当 G1–G6 + G6 人工授权)
                              engineering_enabled = true  ← 由主理人显式置（非 AI）
                                          │
                                          ▼
                              Engineering AI 消费 Engineering_Approved 知识
```

**关键边界**：ActivationGate / Consumption Policy / AI Read Boundary / Rollback 均为**声明性设计**，不编写会翻转 `engineering_enabled` 的代码。真实翻转仍由主理人在 `config.yaml` 显式置 `orchestrator.engineering_enabled=true` 并经 G6 书面授权（沿用 `can_enable_engineering` 默认拒绝语义）。

---

## 2. 文件变化（File Changes）

| 文件 | 变化 | 说明 |
|---|---|---|
| `.ai/reviews/phase3.4.0_activation_readiness_architecture.md` | **新增** | 本报告 |
| `.ai/project_status.json` | **更新** | `task_status.phase_3_1.phase_3_4` 插入设计 DONE 块 |
| `.ai/roadmap_v4.md` | **新增** | Phase 3.4 路线（取代 v3，作为 3.4 起唯一路线） |
| `agents/engineering/knowledge/activation/` | **占位（可选）** | 设计阶段不写代码；实现期拟放 `activation_gate.py` / `consumption_policy.py` / `read_boundary.py` / `rollback.py` |

> ⚠️ **本阶段零可执行业务代码改动**：未新建 `.py` 实现、未改 `agents/`/`backend/app`/`frontend/src`。仅文档与 SSOT/roadmap 元数据更新。

---

## 3. 任务 1 — 激活条件定义（Activation Conditions）

明确 `KnowledgeItem → Engineering_Verified → Engineering_Approved` 所需的递进条件。

### 3.1 七态激活链

```
Captured ─▶ Pending_Verification ─▶ Source_Verified ─▶ Expert_Verified
                                                     ─▶ Engineering_Verified
                                                     ─▶ Engineering_Approved
                                                                  └─▶ Deprecated
```

### 3.2 各跃迁的前提条件（设计）

| 跃迁 | 前提条件（须全部满足） | 责任主体 |
|---|---|---|
| Captured → Pending_Verified | 13 核心字段抽取完成（非全 `pending_verification`） | Connector（已实现） |
| → Source_Verified | `SourceRefBinder` C1–C6 通过（标准/条款/版本引用完整） | 来源校验（已实现） |
| → Expert_Verified | 专家资料存在且 `ExpertBinder` 校验通过 + 专家人工复核确认 | **专家人工** |
| → Engineering_Verified | 双签齐备（专家 + 管理，`mgmt_signed` AND `expert_signed`）+ 质量报告 `overall ≥ 阈值`（阈值待治理确认） | **管理 + 专家人工** |
| → Engineering_Approved | 上一步 + **G6 主理人单独书面授权**（`ReleaseApproval` 已创建，SoD 独立于双签） + 无活跃冲突（`ConflictDetector` 零 `review_required`） + CI 绿（G3） | **主理人人工** |
| → Deprecated | 知识失效 / 被取代（见任务5 Rollback） | 治理流程 |

> 🔴 **红线重申**：`Engineering_Approved` 与 `ReleaseApproval` **只能由人工经正式流程产生**，AI 不得代签、不得自动创建、不得输出 `engineering_approved`。激活条件在此仅作"判定清单"设计，AI 仅做校验与编排。

---

## 4. 任务 2 — ActivationGate 设计（G1–G6，只设计不执行）

复用 `enable_gate.py` 的 G1–G6 门禁语义，将其**适配到知识激活域**，形成 `KnowledgeActivationGate`（设计）：

| Gate | 知识域定义 | 默认态 | 对应既有 |
|---|---|---|---|
| **G1** knowledge_governance | 待激活 item 治理完备：`validation_status` 已达 `Engineering_Verified` + `source_ref` C1–C6 完整 + 双签齐 | ❌ 失败 | `G1_threshold_governance_incomplete` |
| **G2** dual_sign | 专家 + 管理双签齐备（独立于 G1 给精确原因） | ❌ 失败 | `G2_dual_sign_incomplete` |
| **G3** ci_status | `local_ci.sh` 8/8 全绿（注入，默认红） | ❌ 失败 | `G3_ci_not_green` |
| **G4** audit_chain | 知识审计链（`KnowledgeEventLog`）完整：`create→update→verify→deprecated` 无断裂、含必需事件类 | ❌ 失败 | `G4_audit_chain_incomplete` |
| **G5** rollback_ready | 回滚就绪：item 有 `deprecate(successor=)` 谱系或替换计划（注入，默认不就绪） | ❌ 失败 | `G5_rollback_not_ready` |
| **G6** authorization | 主理人单独书面授权（`ReleaseApproval`）到位，SoD 独立于 G2 双签主体 | ❌ 失败 | `G6_authorization_missing` |

**门禁函数语义（设计签名，不实现）**：

```python
def can_activate_knowledge(
    *,
    items: Iterable[KnowledgeItem] | None = None,
    ci_green: bool = False,
    rollback_ready: bool = False,
    authorization_present: bool = False,
    event_log_path: Path | str | None = None,
    require_audit_chain: bool = True,
) -> tuple[bool, list[str]]:
    """返回 (allowed, blocking_reasons)。
    默认全 False → (False, [G1..G6 reasons])。
    红线：不翻转 engineering_enabled、不输出 approved、不创建 ReleaseApproval。
    """
```

> 默认拒绝（fail-closed）：所有外部条件默认不满足 → `can_activate_knowledge()` 默认 `(False, reasons)`，与 `can_enable_engineering` 一致的"默认关闸"安全姿态。

---

## 5. 任务 3 — Knowledge Consumption Policy（知识消费策略）

定义哪些知识可被 Engineering AI 引用、哪些仅辅助、哪些不可引用。

| 类别 | 适用 `validation_status` | Engineering AI 行为 |
|---|---|---|
| **可引用（citable）** | `Engineering_Approved`（且仅在 `engineering_enabled=true` 且经 G6 后） | 可作为权威工程依据进入计算/报告 |
| **仅辅助（auxiliary-only）** | `Source_Verified` / `Expert_Verified` / `Engineering_Verified` | 仅作上下文/提示，**不得**作为数值/条款权威来源；输出须标注 `pending_verification` |
| **不可引用（not-citable）** | `Captured` / `Pending_Verification` / `Deprecated` | 一律不进入工程结论；`Pending_Verification` 与 `Deprecated` 须显式规避 |

**消费策略不变量**：
- 任何 `validation_status` 非 `Engineering_Approved` 的知识，被 Engineering AI 引用时**必须**带 `pending_verification` 标注。
- `Deprecated` 知识即使曾被 Approved，一旦 Deprecated 即退出可引用集，引用方须重定向到 `successor`（见任务5）。

---

## 6. 任务 4 — Engineering AI 读取边界（Read Boundary）

明确 AI 可读取 / 不可读取的边界（声明性约束，设计期写入 `read_boundary.py` 常量与文档，运行期由消费层遵守）。

### 6.1 AI 可以读取
- KnowledgeItem 全部 13 元数据字段（用于展示、检索增强、关系/冲突分析）。
- `KnowledgeQualityReport`（3.3.9，`quality_report()`）——**仅作辅助评估信号**，不作为权威结论。
- `RelationshipCandidate` / `ConflictReport`（3.3.9）——用于**规避**引用冲突/重复，不自动解决。
- `KnowledgeEventLog` 事件（只读审计轨迹，用于 G4 完整性校验）。

### 6.2 AI 不能读取 / 不能消费
- ❌ `verified.json` 真实 `value`（红线③：未经 G1/G2/G4/G6 流程不得作为工程参数使用）。
- ❌ `engineering_enabled` 的写权限（读 `load_engineering_enabled()` 仅用于只读断言）。
- ❌ 任何 `pending_verification` 裸数字当作已确认工程常数。
- ❌ `ReleaseApproval` 的创建权限（G6 由主理人线下产生，AI 不代建）。
- ❌ `Engineering_Approved` 状态的自助产生（AI 仅校验，不签发）。

### 6.3 读取边界不变量
- AI 对知识的所有读取**不改变**任何 item 的 `validation_status`、不写审计事件、不翻 `engineering_enabled`。
- 检索增强（RAG/上下文拼接）仅输出辅助上下文；凡进入工程结论的数值/条款须回溯到 `Engineering_Approved` 且 `engineering_enabled=true`。

---

## 7. 任务 5 — Rollback 策略（失效 → Deprecated → Successor → Replacement）

若知识失效（规范作废、参数错误、被新版本取代），按以下链回滚：

```
有效 KnowledgeItem (Engineering_Approved)
        │  发现失效（ConflictDetector status 冲突 / 人工判定 / 规范版本过期）
        ▼
deprecate(successor=<新 item id>)   → validation_status = Deprecated
        │  写 deprecated 审计事件（白名单允许）
        ▼
Successor 新 KnowledgeItem（承载取代内容，重新走 3.1–3.2 激活链）
        │
        ▼
Replacement 生效：所有原引用方（parent_knowledge_id / linked_entities）重定向到 successor
```

**回滚设计要点**：
- `Repository.deprecate(successor=)`（3.3.8 已实现）支持 successor 谱系，这里予以**正式化**为 Rollback 主路径。
- `ConflictDetector` 的 `status` 冲突检测（同 domain 下 Deprecated 被引用）作为"悬垂引用"哨兵，确保回滚后无残留引用。
- Rollback 不删除旧 item（保留审计与可溯），仅置 `Deprecated` + 链接 `successor`，满足 G5 rollback_ready 的"可回退"要求。
- 激活态维持 NO-GO：回滚路径本身不改变 `engineering_enabled`，仅治理知识生命周期。

---

## 8. 测试结果（Test Results）

> **本阶段为设计-only，无可执行测试新增/运行。**
> 红线相关不变量已由 3.3.8 测试覆盖并持续成立：
> - `KnowledgeEventLog` 拒 `approved`（`record('x','approved')` 抛 `ValueError`）✅
> - `verify()` 仅置 `Source_Verified`，永不 `Engineering_Approved` ✅
> - `safety_invariants_ok()` = `engineering_enabled is False` ✅
> - Connector 集成测试字节级证明 `verified.json` 未变、`release_approvals.jsonl` 不存在 ✅

实现期（待主理人确认后进入 3.4.1+）将补 `tests/agents/test_knowledge_activation.py`：
- `can_activate_knowledge` 默认 `(False, [G1..G6])`（fail-closed）；
- 注入全 green 仍由主理人置 `engineering_enabled`（函数不翻转）；
- Consumption Policy 分类断言；
- Read Boundary 不变量断言（不读 verified.json value / 不建 ReleaseApproval）。

---

## 9. 红线检查（Red-Line Verification）

| 红线 | 本阶段遵守情况 |
|---|---|
| ① 不开 `engineering_enabled` | ✅ 仅读取 `load_engineering_enabled()`；设计上 `can_activate_knowledge` 不翻转 |
| ② 不输出 `engineering_approved` | ✅ 报告中 `Engineering_Approved` 仅作条件输入与策略分类，AI 绝不产生 |
| ③ 不修改 `verified.json` value | ✅ 全程未读未写 `verified.json` |
| ④ 不创建 `ReleaseApproval` | ✅ G6 授权明确由主理人线下创建，AI 不代建 |
| ⑤ AI 不代专家审核 | ✅ 激活链中 Expert/管理/主理人步骤均为人工责任，AI 仅校验编排 |

---

## 10. 技术债记录（Tech Debt）

| ID | 描述 | 严重度 | 状态 |
|---|---|---|---|
| TD-3.4.0-1 | 激活阈值（`overall ≥ ?`、`freshness` 分桶）待治理确认，当前仅为设计占位 | 中 | open（待主理人确认） |
| TD-3.4.0-2 | `KnowledgeActivationGate` 尚未与 `can_enable_engineering` 统一编排（阈值域 vs 知识域两套 G1–G6 需上层聚合） | 中 | open（设计待实现） |
| TD-3.4.0-3 | Consumption Policy 运行时强制（辅助引用须标 `pending_verification`）需在消费层（Agent/RAG）落地校验，目前仅声明 | 高 | open |
| TD-3.4.0-4 | 沿用 3.2.5-H3-B：冻结记录 bundle_id 不一致（建议重生成） | 低 | 沿用，待主理人确认 |
| TD-3.4.0-5 | `local_ci.sh` 完整运行下 `test_smoke_e2e.py` 触发 WorkBuddy `[safe-delete]` 守卫（环境级，与 3.4.0 无关） | 低 | 沿用，待基建处理 |

---

## 11. 下一阶段建议（Next-Phase Recommendations）

1. **3.4.1（实现期，待确认）**：按本报告落地 `agents/engineering/knowledge/activation/` 四个模块（gate/consumption/read_boundary/rollback），全部为只读/声明性，不翻转 `engineering_enabled`。
2. **激活前置人工动作（非 AI）**：真实知识双签、真实审核链、G6 书面授权、CI 绿确认、回滚就绪确认 —— 均 pending_verification，须主理人/专家线下完成。
3. **与阈值域 G1–G6 聚合**：建议 3.4.2 设计 `UnifiedActivationGate` 同时校验"阈值参数"与"知识资产"两套门禁，避免分裂。
4. **消费层落地 TD-3.4.0-3**：在 Engineering Agent / RAG 检索拼接处强制 `pending_verification` 标注与 `Deprecated` 规避。
5. **维持 NO-GO**：在本架构完全就位且 G1–G6 全绿 + G6 授权前，`engineering_enabled` 保持 `False`，激活态维持 NO-GO。

---

## 12. 收尾

> 🛑 **本阶段已停止（设计-only 完成）。未开启 `engineering_enabled`（仍 `False`）、未输出 `engineering_approved`、未创建 `ReleaseApproval`、未修改 `verified.json`、未以任何未验证工程参数填充知识库。等待主理人确认激活阈值与实现排期后，方可进入 3.4.1 实现。**
