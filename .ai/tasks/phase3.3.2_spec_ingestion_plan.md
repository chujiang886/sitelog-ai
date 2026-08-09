# Phase 3.3 Sprint 3.3.2 — 真实规范来源接入流程（Spec Ingestion Plan，pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.2 Real Specification Ingestion
**身份**：BOIP AI Chief Architect（流程编排与结构增强，不录入真实规范内容）
**日期**：2026-08-01
**性质**：纯流程设计文档 + `spec_sources.json` 结构增强，不写盘任何真实规范条款，全 pending_verification。

---

## 0. 目标与红线

**目标**：建立「真实规范来源登记与校验能力」——人工提供的规范来源经来源校验、版本登记、hash 生成、审核后，成为可信的 `spec_source`，并经由 Source Ref 映射规则支撑 E-TH 阈值的 `source_ref` 结构化引用（C1-C6 校验）。

**红线**：

| # | 禁止 | 说明 |
|---|---|---|
| 1 | 自动生成工程参数 | 真实规范条款、取值、参数由人工经正式流程提供 |
| 2 | 自动填写 E-TH value | `verified.json` 的 `value` 仍 `null`，本 Sprint 不改 |
| 3 | 修改 `verified.json` | 本 Sprint 不触碰生产阈值库 |
| 4 | 开启 `engineering_enabled` | 全局仍 `false` |
| 5 | 输出 `engineering_approved` | 全 `pending_verification` |

**真实规范内容必须人工确认**：本文件与 `spec_sources.json` 仅定义结构与流程，不承载任何真实规范文本/条款号/取值。

---

## 1. 人工提供（Source Material Submission）

- **输入**：行业专家或主理人提供规范来源材料（标准文本/企业标准文件/专家签署文档）。
- **登记目标**：写入 `agents/engineering/knowledge/spec_sources.json` 的 `sources[]` 一条目，初始 `source_status=draft`。
- **必填元数据字段**（结构见 `spec_sources.json`）：
  - `source_id`：全局唯一标识符（建议 `SRC-` 前缀 + 语义 slug），人工指定。
  - `source_type`：枚举 `national_standard` / `enterprise_standard` / `expert_document`。
  - `standard`：规范/标准编号（C1）。
  - `title`：规范标题。
  - `publisher`：发布机构。
  - `edition`：版本/年号（C3，须 4 位年份或 `vX.Y`）。
  - `official_url`：可公开复核链接（C4）。
  - `retrieved_at`：检索时间（ISO8601）。
  - `clause_index`：本规范可用条款号清单（C2 候选集）。
- **失败处理**：缺必填字段 / `source_id` 重复 → 拒绝登记，保持草稿态占位。

---

## 2. 来源校验（Source Validation，C1-C6）

- **复用**：`agents/engineering/thresholds/source_ref_validator.py` 的 `validate_source_ref`。
- **校验对象**：以本条 `spec_source` 构造临时 `ThresholdSourceRef`（standard/clause 取 clause_index 逐项试校验，edition/url/retrieved_at 取自元数据），逐条判定：
  - C1 `standard` 完整且非占位；
  - C2 `clause` 完整且非占位；
  - C3 `edition` 合规（4 位年份或 `vX.Y`）；
  - C4 `url` 为 http(s) 可复核链接；
  - C5 `hash` 为 64 位十六进制 sha256（条目级 hash 在步骤4 生成后回填）；
  - C6 C1+C2 完整（`ThresholdSourceRef.is_complete()`）。
- **输出**：逐条 `SourceVerificationReport`（通过/不通过 + reason）。
- **失败处理**：任一 C 不满足 → 拒绝进入版本登记，标记 `pending_verification`，不降级强行入库。

---

## 3. 版本登记流程（Source Version Lifecycle）

对应 `spec_sources.json` 的 `source_status_enum`，三态流转：

```
draft ──(人工来源校验通过 + hash 登记)──▶ verified_source
verified_source ──(被新版本取代/撤销)──▶ deprecated
deprecated ──(回滚恢复)──▶ verified_source   （保留旧条目，不物理删除）
```

- **draft**：初始态，仅占位，不可被阈值 `source_ref` 引用（`mapping_convention.rule_status_gating`）。
- **verified_source**：经人工来源校验 + 内容 hash 登记后转正，成为可信出处，可被 E-TH `source_ref` 引用。
- **deprecated**：失效/被取代，拒绝被引用，保留供审计与降级展示（与 `ThresholdStatus.DEPRECATED` 语义一致，复用 `rollback.py` 回滚路径）。
- **约束**：同 `standard` 出现新版 → 旧版置 `deprecated`，不静默采用，标记 `pending_verification` 直至人工确认。

---

## 4. hash 生成（Content Hash，C5）

- **唯一合法来源**：`source_ref_validator.compute_content_hash(content)`（sha256，64 位十六进制）。
- **生成时机**：来源校验通过、条款内容确定后，对每条被引用条款内容计算 hash，回填至该 `spec_source` 派生出的 `ThresholdSourceRef.hash`（禁止手写）。
- **一致性比对**：若录入时提供条款原文 `content`，`validate_source_ref` 将比对 `hash == compute_content_hash(content)`，不一致即 `SOURCE_REF_HASH_MISMATCH` 拒绝。
- **失败处理**：hash 缺失 / 格式非法 / 与内容不符 → 拒绝登记为 `verified_source`。

---

## 5. 审核流程（Review & Sign-off）

- **审核人**：来源校验与版本登记转正由主理人或其指定审核人执行，审核人标识符来自 `experts.json`（`sod_role=principal` 或指定 `sign_scope` 含 source_review）。
- **落 audit**：来源登记与转正动作落 `review_log`（或既有 `release_audit.jsonl`），记录 `source_id` / `source_status` 变迁 / 操作人 / 时间戳，确保不可篡改可追溯。
- **SoD 对齐**：来源登记操作人与审核人应分离（参考 3.3.1 `experts.json` 的 `sod_role` 规则）；`expert_document` 类来源须关联 `experts.json` 的 `expert_id`，且签署主体不得为同一条目的登记操作人。
- **失败处理**：缺审核人 / SoD 冲突 / audit 断裂 → 拒绝转正，保持 `draft`。

---

## 6. Source Ref 映射规则（规范来源 → ThresholdSourceRef → E-TH 引用）

详见 `spec_sources.json` 的 `mapping_convention` 段，要点：

1. **source → ref**：阈值录入（3.3.4）时，由某 `source_id`（须 `verified_source` 态）生成结构化 `ThresholdSourceRef`：`standard←standard`、`clause←clause_index` 中对应条款、`edition←edition`、`url←official_url`、`retrieved_at←retrieved_at`、`hash←条款内容 sha256`。
2. **ref → threshold**：E-TH 条目的 `source_ref` 引用「`source_id` + 具体 `clause`」，`applies_to` 标识归属方案（如 `wind_pressure`）；在 3.3.1 `threshold_entry_plan` 步骤1 经 `build_source_verification_report` 对该 ref 做 C1-C6 校验（pending_verification）。
3. **校验复用**：全程使用既有 `validate_source_ref`，不重复实现。
4. **约束**：`source_id` 全局唯一；被引用 `clause` 必须落在 `clause_index` 内（C2 一致性）；仅 `verified_source` 态 source 可被引用。

> 当前 `verified.json` 的 E-TH 条目 `source_ref` 仍为 v1 自由文本占位（"待行业专家签字填入规范/标准号 pending_verification"）。真实化时由 3.3.4 经 `threshold_migration.py` 升级为指向本表 `verified_source` 条目的结构化引用，本 Sprint 不执行。

---

## 7. 收口判定（本 Sprint）

本 Sprint 产出：
- `spec_sources.json` 结构增强（`source_type` / `source_status` / `mapping_convention`）；
- 本流程文档（含人工提供 / 来源校验 / 版本登记 / hash 生成 / 审核 / 映射规则）。

计为 **3.3.2 DONE（结构+流程态）**。真实规范内容的登记、校验执行、hash 回填、审核签署均留待人工经正式流程在后续操作中完成（仍须主理人审核 + 单独书面授权）。`engineering_enabled` 保持 `false`，`verified.json` 不变。

*防编造声明：本文档所有字段名、枚举值、流程步骤、版本态均为代码既有定义引用或占位，非真实工程参数；真实规范文本、条款号、hash、专家身份、签名均 pending_verification，由人工经正式流程提供。*
