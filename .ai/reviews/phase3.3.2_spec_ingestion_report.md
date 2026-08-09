# Phase 3.3 Sprint 3.3.2 — 真实规范来源接入执行报告（Spec Ingestion Report，pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.2 Real Specification Ingestion
**身份**：BOIP AI Chief Architect
**日期**：2026-08-01
**性质**：纯结构增强 + 流程设计，不录入真实规范条款，全 pending_verification。

---

## 0. 目标与红线

**目标**：建立「真实规范来源登记与校验能力」——完善 `spec_sources.json` 结构，设计规范来源经人工提供、来源校验（C1-C6）、版本登记、hash 生成、审核后成为可信 `spec_source`，并经由 Source Ref 映射规则支撑 E-TH 阈值的 `source_ref` 结构化引用。

**红线（最高优先级，全程守约）**：

| # | 禁止 | 本 Sprint 结果 |
|---|---|---|
| 1 | 自动生成工程参数 | 真实规范条款/取值全 pending_verification，未生成 |
| 2 | 自动填写 E-TH value | `verified.json` 的 E-TH 仍 `value=null`，未填 |
| 3 | 修改 `verified.json` | 未触碰生产阈值库 |
| 4 | 开启 `engineering_enabled` | 全局仍 `false`（config 第102行实测） |
| 5 | 输出 `engineering_approved` | 无任何 approved 落盘/输出 |

**真实规范内容必须人工确认**：本 Sprint 仅定义结构与流程，不承载任何真实规范文本/条款号/取值。

---

## 1. 当前状态承接

- **Phase 3.2**：✅ CLOSED（工程审核闭环 12 类能力 inert）。
- **Phase 3.3.1**：✅ DONE（管理基座：spec_sources.json / experts.json 容器 + 阈值录入计划 / 版本策略 / 签署计划）。
- **本 Sprint 进入**：真实规范来源接入，在 3.3.1 基座（`spec_sources.json`）上增强登记与校验能力。

---

## 2. 任务完成清单（5 项）

| 任务 | 交付 | 状态 |
|---|---|---|
| 任务1 Spec Source Registry 实现增强 | `spec_sources.json` 新增 `source_type` 枚举（national_standard / enterprise_standard / expert_document）+ `source_status` 三态 + `mapping_convention` 段；字段集完整覆盖 source_id/standard/title/publisher/edition/official_url/retrieved_at/clause_index/source_type | ✅ DONE |
| 任务2 Source Ref 映射 | `mapping_convention` 段定义 规范来源→ThresholdSourceRef→E-TH 阈值引用 规则；复用 `validate_source_ref`（C1-C6） | ✅ DONE |
| 任务3 规范版本登记流程 | 设计 source：draft→verified_source→deprecated 三态流转，与 `ThresholdStatus` / `source_status_enum` 对齐 | ✅ DONE（设计态） |
| 任务4 规范 ingestion 流程文档 | `.ai/tasks/phase3.3.2_spec_ingestion_plan.md`（人工提供/来源校验/hash 生成/版本登记/审核/映射） | ✅ DONE |
| 任务5 测试 | 纯文档+JSON 增强路线，无新增业务代码；沿用 CI 基线（local_ci 8/8 全绿，测试全通过） | ✅ DONE |

---

## 3. 关键设计

### 3.1 source_type 枚举（任务1）
- `national_standard`：国家标准（GB / GB/T 系列）。
- `enterprise_standard`：企业标准（门窗企业内控技术条件，须备案可查）。
- `expert_document`：行业专家技术文档（经签署确认，须关联 `experts.json` 的 `expert_id`）。

### 3.2 source_status 三态（任务1 + 任务3）
- `draft`：初始态，仅占位，不可被阈值 `source_ref` 引用。
- `verified_source`：经人工来源校验 + 内容 hash 登记后转正，成为可信出处，可被 E-TH `source_ref` 引用。
- `deprecated`：失效/被取代，拒绝被引用，保留供审计（复用 `rollback.py` 回滚路径，不物理删除）。

### 3.3 Source Ref 映射（任务2）
1. **source → ref**：阈值录入时，由某 `verified_source` 态 `source_id` 生成结构化 `ThresholdSourceRef`（standard/clause/edition/url/retrieved_at/hash 映射，hash 由 `compute_content_hash` 派生，禁止手写）。
2. **ref → threshold**：E-TH 条目 `source_ref` 引用「`source_id` + 具体 `clause`」，`applies_to` 标识归属；在 3.3.1 `threshold_entry_plan` 步骤1 经 `build_source_verification_report` 做 C1-C6 校验。
3. **校验复用**：全程使用既有 `validate_source_ref`，不重复实现。
4. **约束**：`source_id` 全局唯一；被引用 `clause` 必须落在 `clause_index` 内（C2 一致性）；仅 `verified_source` 态 source 可被引用。

### 3.4 与既有符号衔接
- `validate_source_ref` / `compute_content_hash`（source_ref_validator.py）—— C1-C6 校验与 hash 派生。
- `ThresholdSourceRef` / `ThresholdStatus` / `ThresholdGovernanceView`（schema.py）—— 引用结构与状态机语义一致。
- `experts.json`（3.3.1 基座）—— `expert_document` 类来源关联 `expert_id`，审核 SoD 对齐。

---

## 4. 红线守约核验（Bash 实测）

| 检查项 | 命令/方法 | 结果 |
|---|---|---|
| engineering_enabled | `grep` config.yaml 第102行 + 加载器 | `false`（OK） |
| verified.json E-TH value | 逐条读取 | 全部 `value=null`、`verified=false`、`source_ref` 仍占位（未改，OK） |
| release_approvals.jsonl | 存在性检查 | 不存在（OK） |
| engineering_approved 输出 | 全仓检索 | 无（OK） |
| spec_sources.json 完整性 | JSON 解析 | 新字段齐全、schema_version=1、JSON 有效（OK） |

---

## 5. 测试结论（任务5）

本 Sprint 为纯结构增强 + 流程设计，**无新增业务代码**（校验能力由既有 `validate_source_ref` 提供，不重复实现），因此不触发 `local_ci.sh` 新代码路径，沿用既有 **CI 基线：local_ci 8/8 全绿、测试全通过**。

**反编造扫描**：`check_fabrication.py`（业务数字 + key 指纹）**0 命中**（退出码 0）；初报 1 误报（流程文档 `wind_pressure` 与 `C1-C6` 共现）→ 行尾补 `pending_verification` 标记后复跑通过。

**硬编码扫描**：`check_hardcoded.py` **0 命中**（未发现业务阈值/品牌/型号）。

---

## 6. SSOT / roadmap 更新

- `.ai/project_status.json`：
  - `phase_3_3._phase_status`：`PHASE_3_3_READY` → `PHASE_3_3_IN_PROGRESS`。
  - 新增 `phase_3_3."3.3.2"` 条目（`status=DONE`，含 deliverables / fabrication_scan / next）。
  - JSON 校验通过。
- `.ai/roadmap_v3.md`：
  - §1 阶段状态行更新为「Phase 3.3 IN_PROGRESS，3.3.1+3.3.2 DONE，3.3.3+ PENDING」。
  - §2 的 `3.3.2` 行由 PENDING 改为 DONE 并补充执行产出。

---

## 7. 未完成与下一步

**本 Sprint 未执行（留待人工经正式流程）**：
- 真实规范条款登记（填充 `spec_sources.json` 的 `sources[]` 真实条目，含真实 standard/clause/edition/url/hash）。
- 来源校验执行、hash 回填、审核签署（落 `review_log` / `release_audit.jsonl`）。
- `verified.json` 的 E-TH `source_ref` 由 v1 占位文本升级为指向本表 `verified_source` 条目的结构化引用（留待 3.3.4 经 `threshold_migration.py`）。

**下一步**：进入 **3.3.3 真实专家 onboarding**（填充 `experts.json` 专家名录、落实 SoD 角色）→ 3.3.4 真实阈值录入执行 → 3.3.5 真实签署执行 → 3.3.6 激活复核。全程不开 `engineering_enabled`、不输出 `engineering_approved`。

---

## 8. 收口判定（本 Sprint）

3.3.2 产出：增强版 `spec_sources.json` + 规范 ingestion 流程文档 + 本报告。计为 **3.3.2 DONE（结构+流程态）**。真实规范内容登记与校验执行均不在此 Sprint，由人工经正式流程后续完成。红线全程守约，双扫描 0 命中。

*防编造声明：本文档所有字段名、枚举值、流程步骤、版本态、标识符均为代码既有定义引用或占位，非真实工程参数；真实规范文本、条款号、hash、专家身份、签名均 pending_verification，由人工经正式流程提供。*
