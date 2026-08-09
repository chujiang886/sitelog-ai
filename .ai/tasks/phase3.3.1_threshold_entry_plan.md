# Phase 3.3 Sprint 3.3.1 — 任务3：真实阈值录入计划（Threshold Entry Plan，pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.1 Real Engineering Knowledge Activation
**身份**：BOIP AI Chief Architect（流程编排，不执行录入）
**日期**：2026-08-01
**性质**：纯计划文档，不调用任何录入代码，不写盘 verified.json 真实 value，全 pending_verification。

---

## 0. 目标与红线

**目标**：编排 `E-TH-01` / `E-TH-02` / `E-TH-03` 三条 wind_pressure 相关阈值的真实录入**执行计划**——谁、经何流程、何时、需满足哪些门禁。本 Sprint **不执行录入**。

**红线**：

| # | 禁止 | 说明 |
|---|---|---|
| 1 | 录入真实参数 | `E-TH-01/02/03` 真实 `value` 由人工经 `ThresholdIntakeWorkflow` 在后续 Sprint 3.3.4 填写，本计划不填 |
| 2 | 开启 `engineering_enabled` | 全局仍 `false` |
| 3 | 输出 `engineering_approved` | 全 `pending_verification` |
| 4 | 创建 `ReleaseApproval` | G6 授权由主理人书面创建，本计划不创建 |

---

## 1. 前置：既有 `ThresholdIntakeWorkflow`

复用 Phase 3.2 建成的 `agents/engineering/threshold_intake.py`：

- 六字段录入态：submit → review_approve（主理人核准写 `verified_by/at`）→ expert_recheck（专家复核写 `expert_verified_by/at`，SoD 强制 `expert_verified_by ≠ verified_by`）→ finalize_verified（置 `verified=true`）。
- `evaluate_gates` 恒返回 `False`：任何经此工作流转正的值，**不自动**满足 G1-G6 放行；仍须 `can_enable_engineering` 显式授权 + G6 书面授权。
- `build_source_verification_report`：对 `source_ref` 逐条 C1-C6 校验，供提交前准入判定。
- 设计不变式：AI 仅做格式校验与流程编排，**绝不**生成参数、绝不猜测缺失、绝不修改专家签署、绝不自动补 `source_ref`。

---

## 2. 录入编排（E-TH-01 / E-TH-02 / E-TH-03）

三条阈值当前态（`agents/engineering/thresholds/verified.json`）：`verified=false`、`value=null`、`verified_by=null`、`expert_verified_by=null`、`source_ref` 为占位文本。录入后将经下述五步流转：

### 步骤 1：source_ref 验证（C1-C6）
- 输入：真实规范来源（来自 3.3.2 规范 ingestion 登记的 `spec_sources.json` 条目）。
- 动作：调用 `build_source_verification_report(source_ref)` 逐条校验 C1（standard 完整）/ C2（clause 完整）/ C3（edition 合规）/ C4（url 可达）/ C5（hash 为 64 位 sha256）/ C6（C1+C2 完整）。
- 输出：`SourceVerificationReport`（逐条通过/不通过 + 总体结论）。
- 失败处理：任一 C 不满足 → 拒绝进入提交，标记 `pending_verification`，不降级强行入库。

### 步骤 2：submit（提交）
- 输入：阈值提供方（人工）填入 `value` / `unit` / `source_ref` / `version`；提交人标识符。
- 动作：`ThresholdIntakeWorkflow.submit` 校验授权范围 → `validate_source_ref` → 写入 draft 态（双签位仍 null）。
- 输出：draft 条目进入审核链，落 `review_log` intake 事件。
- 失败处理：未授权 / source_ref 未过 / 已转正 → 拒绝提交，保持 `value=null`。

### 步骤 3：review_approve（主理人核准）
- 输入：主理人人工核准，写入 `verified_by` / `verified_at`（标识符，来自 `experts.json` 中 `sod_role=principal` 主体）。
- 动作：`review_approve` 写主理人核准位，落 `review_log` 第二类 intake 事件。
- 失败处理：缺 `verified_by` 或标识符不在 principal 名录 → 拒绝核准。

### 步骤 4：expert_recheck（行业专家复核签）
- 输入：行业专家人工复核，写入 `expert_verified_by` / `expert_verified_at`（标识符，来自 `experts.json` 中 `sod_role=expert` 主体）。
- 动作：`expert_recheck` 校验 SoD（`expert_verified_by ≠ verified_by`），落 `review_log` 第三类 intake 事件。
- 失败处理：SoD 冲突（专家=主理人）或缺专家签 → 拒绝复核，双签不完整。

### 步骤 5：finalize_verified（转正）
- 输入：双签俱全 + 审核链四事件齐备。
- 动作：`finalize_verified` 置 `verified=true`，落 `review_log` 第四类 intake 事件。
- 输出：阈值条目进入 `VERIFIED` 态（仍受 `engineering_enabled` 闸门约束，不自动放量）。
- 失败处理：双签缺失 / 审核链断裂 → 拒绝转正，保持 `verified=false`。

---

## 3. 执行人 / 复核人 / 时间窗规划（占位）

| 步骤 | 执行人 | 复核人 | 时间窗 | 标识符落点 |
|---|---|---|---|---|
| source_ref 验证 | 阈值提供方 | 主理人 | pending_verification | source_ref（C1-C6） |
| submit | 阈值提供方 | — | pending_verification | draft 态 |
| review_approve | 主理人 | 主理人上级 | pending_verification | `verified_by` / `verified_at` |
| expert_recheck | 行业专家 | 主理人 | pending_verification | `expert_verified_by` / `expert_verified_at` |
| finalize_verified | 工作流 | 主理人 | pending_verification | `verified=true` |

> 上述执行人/时间窗均为占位，由人工经正式流程指定；AI 不代填真实值或真实身份。

---

## 4. 录入前置门禁清单

录入并转正后，须满足以下门禁方可进入激活复核（3.3.6）：

- **G1 阈值治理**：`governance_ok()` 为真（`status=VERIFIED` + `source_ref.is_complete()` + 双签齐全）。
- **G2 双签齐备**：`verified_by/at` + `expert_verified_by/at` 俱全且 SoD 成立。
- **G4 审核链**：`review_log` 含四类 intake 事件（schema_established / submit / review / expert_recheck / finalize），链路连续不可篡改。
- G3（CI 绿）、G5（回滚就绪）、G6（主理人书面授权）在激活复核阶段另行确认。

---

## 5. 红线守约与失败处理

- 不以真实数据调用 `ThresholdIntakeWorkflow`；不写 `verified.json` 真实 value；`engineering_enabled` 不变。
- source_ref 未过 C1-C6 / 双签 SoD 冲突 / 缺主理人复核 → 拒绝录入，保持 `value=null`。
- 本计划文档不含任何真实工程取值；真实数值、专家身份、签名、授权均 `pending_verification`，由人工经正式流程提供。

---

## 6. 收口判定（本 Sprint）

本任务仅产出**录入计划**，不执行录入 → 计为 3.3.1 任务3 DONE（计划态）。真实执行留待 3.3.4（须主理人审核 + 单独书面授权）。

*防编造声明：本文档所有 E-TH 标识符、版本号、流程步骤均为引用或占位，非真实工程参数；真实数值、专家身份、签名、授权均 pending_verification。*
