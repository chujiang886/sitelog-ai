# BOIP Phase 3.3.0 — Obsidian Knowledge System Integration Design

- **生成日期**：2026-08-01
- **身份**：BOIP AI Chief Architect
- **任务**：Obsidian Knowledge System Integration Design（架构设计）
- **性质**：**纯架构设计，零代码、零开发、不修改工程计算代码**；仅产出架构文档并更新 `roadmap_v3.md`
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V3）、`.ai/roadmap_v3.md`、`.ai/tasks/phase3.3.1_engineering_knowledge_activation.md`、`.ai/tasks/phase3.3.2_spec_ingestion_plan.md`、`agents/engineering/knowledge/spec_sources.json`、`agents/engineering/knowledge/experts.json`
- **知识流目标**：Obsidian（个人知识侧） ↓ BOIP Knowledge Layer（工程知识层） ↓ Engineering AI（受治理的工程智能）

---

## 0. 设计目标与边界

Phase 3.3 已进入「Engineering Knowledge Activation」。3.3.1 与 3.3.2 已建立 `spec_sources.json`（规范来源登记 + source_type/source_status + C1-C6 映射）与 `experts.json`（专家资料 + SoD 角色）两个 BOIP 侧容器。但规范来源与专家资料**原始采集**目前无统一入口。

本 Sprint（3.3.0）补齐「Obsidian 侧知识采集 → BOIP 侧结构化入库」的**协同架构设计**，使主理人/专家在 Obsidian 中按规范记笔记，经 AI 整理与人工校验后，安全落入 BOIP 既有容器。

**边界铁律**：
- 本阶段仅架构设计，**不写任何同步代码、不新增 `.py`、不改 `agents/` 工程计算逻辑**。
- 不录入真实工程参数；不开启 `engineering_enabled`；不输出 `engineering_approved`。
- 所有真实规范条款、专家身份、阈值数值仍保持 `pending_verification`，由人工经 3.3.3~3.3.5 正式流程登记。

---

## 1. 知识分层架构（任务1）

三层明确边界，自上而下治理强度递增，自下而上追溯链路闭合。

### 1.1 Personal Knowledge Layer（个人知识层）
- **归属**：主理人/专家本地 Obsidian Vault，自由笔记形态（Markdown + frontmatter）。
- **内容**：原始阅读摘录、现场经验、未结构化假设、待核实线索。
- **约束**：本层允许 `pending_verification` 与非正式表述；**不被 BOIP 工程计算直接消费**。
- **出口**：经「知识迁移流程（任务3）」升格为 Knowledge Item 后方可进入下一层。

### 1.2 Engineering Knowledge Layer（工程知识层）
- **归属**：BOIP 既有容器（`agents/engineering/knowledge/spec_sources.json`、`experts.json`，以及阈值引用 `agents/engineering/thresholds/verified.json`）。
- **内容**：已结构化的规范来源、专家资料、阈值 source_ref 引用。
- **约束**：接受 C1-C6 校验（来源）与 SoD 角色约束（专家）；仅 `verified_source` 态来源与 `verified` 态阈值可被工程 AI 引用；全程受 `engineering_enabled=false` 约束，引用即 inert 不触发真实计算。
- **出口**：经 G1-G6 门禁 + G6 授权后，工程 AI 在激活态方可消费（属 3.3.6 范畴，本设计不展开）。

### 1.3 Governance Knowledge Layer（治理知识层）
- **归属**：`agents/engineering/review_log.py`（事件链 signer）、`release_approvals.jsonl`（G6 授权）、`release_audit.jsonl` / `approved_monitor.jsonl`（监控审计）。
- **内容**：审核链、双签、授权、灰度发布与回滚记录。
- **约束**：**仅人工线下经正式流程落盘**；AI 仅编排容器与校验，不代签、不代授权、不自动创建 `ReleaseApproval`。
- **与上层关系**：工程知识层每一次「升格/入库」动作必须在治理层留痕（review_log signer 标识符 + 时间戳）。

### 1.4 边界矩阵

| 维度 | Personal | Engineering | Governance |
|---|---|---|---|
| 形态 | 自由笔记 | 结构化 JSON 容器 | 事件链 / 授权记录 |
| 谁可写 | 个人 | 人工经校验流程 | 人工线下 |
| AI 角色 | 整理/抽取 | 校验/编排 | 编排/留痕 |
| 工程消费 | 否 | 激活后仅引用 | 否（仅控制面） |
| 红线闸门 | 无 | C1-C6 / SoD | G1-G6 / G6 |

---

## 2. Obsidian Vault 结构（任务2）

设计七类目录，覆盖从原始来源到已核验知识的全生命周期，并与 BOIP 既有容器一一映射。

```
BOIP-Vault/
├── 00-Sources/               # 规范来源原始摘录（↔ spec_sources.json）
├── 01-Experts/               # 专家资料与资质（↔ experts.json）
├── 02-Cases/                 # 工程案例 / 失效复盘（经验型，不直接入库阈值）
├── 03-Engineering-Rules/     # 工程规则草稿（阈值/条款候选，待校验）
├── 04-Experience/            # 个人经验与现场笔记（Personal 层留存量）
├── 05-Pending-Verification/  # 待核实 Knowledge Item（draft 态）
└── 06-Verified-Knowledge/    # 已核验 Knowledge Item（verified_source 态，可入库）
```

### 2.1 各目录用途与边界
- **00-Sources**：按 `source_type` 分子目录（`national_standard` / `enterprise_standard` / `expert_document`）。每条笔记对应一个待登记 `source_id`，frontmatter 含 standard/edition/official_url 等，与 `spec_sources.json` 字段对齐。
- **01-Experts**：每位专家一个笔记，`expert_id` / `domain` / `qualification_ref` / `sign_scope` / `sod_role`，与 `experts.json` 字段对齐；`sod_role` 取值 `principal` / `expert`（沿用既有 SoD 定义）。
- **02-Cases**：工程案例与失效复盘，属经验证据，可为阈值录入提供 rationale，但**不直接改写阈值 value**。
- **03-Engineering-Rules**：工程规则草稿（条款候选 / 阈值候选），须先落入 `05-Pending-Verification` 经校验升格。
- **04-Experience**：个人经验留存量，Personal 层自由区，不被 BOIP 强制消费。
- **05-Pending-Verification**：所有经 AI 整理但尚未通过 Source 验证 + Expert 审核的 Knowledge Item 暂存区；对应 `source_status=draft`。
- **06-Verified-Knowledge**：通过校验的 Knowledge Item，对应 `source_status=verified_source`，具备进入 BOIP 入库条件。

---

## 3. 知识迁移流程（任务3）

从 Obsidian 笔记到 BOIP 入库的六阶段流水线，每阶段明确职责与闸门，并与既有 `ThresholdIntakeWorkflow` 衔接。

```
Obsidian 笔记
   ↓ (1) AI 整理
Knowledge Item（抽取 frontmatter + 正文结构化）
   ↓ (2) Source 验证
C1-C6 校验（standard/clause/edition/url/hash/completeness）
   ↓ (3) Expert 审核
专家 sign_scope 覆盖 + SoD 双签（principal ≠ expert）
   ↓ (4) BOIP 入库
写入 spec_sources.json / experts.json（仅元数据，不写阈值 value）
   ↓ (5) 引用绑定
生成/更新 ThresholdSourceRef（指向 verified_source）
```

### 3.1 阶段职责
- **(1) AI 整理**：读取 Obsidian 笔记，抽取 frontmatter 六字段，生成 Knowledge Item 草稿；不臆造任何数值，缺失标 `pending_verification`。
- **(2) Source 验证**：复用 `agents/engineering/thresholds/source_ref_validator.py` 的 `validate_source_ref` 做 C1-C6 校验；任一不满足则退回 `05-Pending-Verification`。
- **(3) Expert 审核**：由 `01-Experts` 中 `sign_scope` 覆盖该 domain 的专家复核；双签落 `review_log`（verified_by / expert_verified_by），满足 SoD（`authorized_by` 须另选 `rollback_owner`）。
- **(4) BOIP 入库**：仅将已核验元数据写入 `spec_sources.json`（`source_status=verified_source`）或 `experts.json`；**不触碰 `verified.json` 的阈值 value**（阈值真实数值录入属 3.3.4）。
- **(5) 引用绑定**：为后续阈值录入建立 `ThresholdSourceRef` 指向，满足 `source_status=verified_source` 闸门（沿用 3.3.2 的 `mapping_convention`）。

### 3.2 与 ThresholdIntakeWorkflow 衔接
3.3.4 真实阈值录入时，`ThresholdIntakeWorkflow` 的「source_ref 验证」步骤直接消费本流程已入库的 `verified_source`；即本流程是 3.3.4 的上游，不重叠、不越权。

---

## 4. Metadata 规范（任务4）

所有 Obsidian 笔记统一 frontmatter 六字段，取值与 BOIP 容器语义对齐，**禁止手写数值型 confidence**（用等级枚举规避编造）。

```yaml
---
source: <source_id 或 pending_verification>      # ↔ spec_sources.json source_id
author: <expert_id 或 pending_verification>      # ↔ experts.json expert_id
domain: <计算域标识，如 wind_pressure / pending_verification>
confidence: <unverified | low | medium | high | verified>   # 等级枚举，禁手写数字
verification_status: <draft | verified_source | deprecated> # ↔ source_status 三态
linked_threshold: <E-TH-xx 或 空>                # 字母标识符，仅引用不填值
---
```

### 4.1 字段约束
- **source**：须指向 `00-Sources` 已登记且 `source_status=verified_source` 的 `source_id`；草稿态标 `pending_verification`。
- **author**：须指向 `01-Experts` 已登记 `expert_id`；未登记标 `pending_verification`。
- **domain**：与 `experts.json` 的 `domain` 及工程计算域一致；未知标 `pending_verification`。
- **confidence**：等级枚举，**绝不以小数或百分比手写置信度**（防编造闸门）；`verified` 仅当 Expert 审核通过后由流程置位。
- **verification_status**：三态与 `spec_sources.json` 的 `source_status_enum` 完全一致，作为 Vault 内升格闸门。
- **linked_threshold**：仅记录字母标识符（如 `E-TH-01`），不承载真实数值；数值录入在 3.3.4。

---

## 5. MCP / 自动同步方案（任务5，仅设计）

仅设计 Obsidian → BOIP 单向采集同步接口，不实现。

### 5.1 同步拓扑
```
[Obsidian Vault]
      │  (ObsidianMCPConnector 读取笔记 + frontmatter)
      ▼
[KnowledgeItemExtractor]  → 抽取六字段 + 正文结构化
      │
      ▼
[SourceRefBinder]  → C1-C6 预校验 + 生成待入库 Knowledge Item
      │
      ▼
[SyncScheduler]  → 触发入 05-Pending-Verification；人工审核后落 BOIP 容器
      │
      ▼
[BOIP Knowledge Layer]  → 写入 spec_sources.json / experts.json（仅元数据）
```

### 5.2 接口设计（抽象）
- **ObsidianMCPConnector**：基于 Obsidian 本地 REST / 文件系统读取笔记与 frontmatter；提供 `list_notes(dir)`、`read_note(path)`、`write_back_status(path, status)`。
- **KnowledgeItemExtractor**：`extract(note) -> KnowledgeItem`（六字段 + 正文向量/摘要）。
- **SourceRefBinder**：`bind(item) -> (c1_c6_report, pending_item)`；调用既有 `validate_source_ref` 语义。
- **SyncScheduler**：`schedule(sync_policy)` 支持手动触发 / 定时 / Webhook；写入前做去重（按 `source_id` + `sha256(note_body)`）。

### 5.3 同步策略
- **方向**：Obsidian → BOIP 单向采集；**绝不反向覆盖 Obsidian 原笔记**（回写仅更新 Vault 内 `verification_status` 标签）。
- **去重**：`source_id` 全局唯一 + 笔记内容 `sha256` 摘要；重复笔记跳过或标记 merge。
- **校验闸门**：未过 C1-C6 的 Knowledge Item 留在 `05-Pending-Verification`，不写 BOIP 容器。
- **回写**：仅在人工审核后由 `SyncScheduler` 落盘 `spec_sources.json` / `experts.json`；**不写 `verified.json` 阈值 value，不创建 `release_approvals.jsonl`**。

### 5.4 不做清单（明确边界）
- 不实现任何同步代码（本 Sprint 纯设计）。
- 不自动改 `engineering_enabled`。
- 不自动输出 `engineering_approved`。
- 不代签、不代授权、不自动创建 `ReleaseApproval`。

---

## 6. 与现有 BOIP Knowledge Layer 映射对齐

| Obsidian 目录 | BOIP 容器 | 映射字段 | 闸门 |
|---|---|---|---|
| 00-Sources | spec_sources.json | source_id/standard/title/publisher/edition/official_url/retrieved_at/clause_index/source_type | C1-C6 |
| 01-Experts | experts.json | expert_id/domain/qualification_ref/sign_scope/sod_role | SoD |
| 05-Pending-Verification | （暂存，不入库） | 全部 `pending_verification` | draft 态 |
| 06-Verified-Knowledge | spec_sources.json（verified_source） | source_status=verified_source | 可引用 |
| 03-Engineering-Rules | verified.json（仅 linked_threshold 引用） | E-TH-xx 标识符 | 值仍 null（3.3.4 填） |

**一致性**：本设计与 3.3.1 / 3.3.2 既有容器**完全兼容**——Vault 是采集入口，BOIP 容器是落盘点，映射字段一一对应，无新增字段冲突。

---

## 7. 红线与治理不变式（本 Sprint）

1. **不修改工程计算代码**：`agents/engineering/thresholds/*.py`、`backend/app`、`frontend/src` 零改动；本产出仅为 Markdown 架构文档。
2. **不录入真实工程参数**：所有 source/author/value 保持 `pending_verification`，真实条款经 3.3.3~3.3.4 人工流程登记。
3. **不开 `engineering_enabled`**：全局仍 `false`；引用即 inert。
4. **不输出 `engineering_approved`**：全 `pending_verification`，无 approved 落盘。
5. **防编造/硬编码扫描**：本设计文档持续 0 命中（数值以枚举/字母标识符表达）。
6. **不代签/不代授权/不自动创建 ReleaseApproval**：G6 授权由主理人书面创建。

---

## 8. 下一步

- 本设计为 3.3.1 / 3.3.2 容器提供 Obsidian 侧采集入口；执行落地建议后续单独 Sprint（如 3.3.7 Obsidian Connector 实现）在 3.3.4 真实录入之前或并行排期。
- 进入 3.3.3（真实专家 onboarding，填充 `experts.json`）与 3.3.4（真实阈值录入）时，可直接复用本设计的 Metadata 规范与迁移流程作为人工操作手册。
- 红线全程守约，按指令「完成后停止」——不开发、不录真实数据。

**END**
