# Phase 3.3 Sprint 3.3.1 — 任务5：专家签署计划（Expert Signing Plan，pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.1 Real Engineering Knowledge Activation
**身份**：BOIP AI Chief Architect（流程编排，不执行签署）
**日期**：2026-08-01
**性质**：纯计划文档，不代签、不代授权、不创建 `ReleaseApproval`、不输出 `engineering_approved`，全 pending_verification。

---

## 0. 目标与红线

**目标**：编排真实阈值**双签** + G6 主理人书面授权的**签署计划**——流程、落点、SoD 规则。本 Sprint **不执行签署**。

**红线**：

| # | 禁止 | 说明 |
|---|---|---|
| 1 | 代签 / 代授权 | 签名与授权由人工线下经正式流程提供 |
| 2 | 创建 `ReleaseApproval` | G6 授权由主理人书面创建 `release_approvals.jsonl` |
| 3 | 输出 `engineering_approved` | 全 `pending_verification` |
| 4 | 开启 `engineering_enabled` | 全局仍 `false` |

---

## 1. 双签流程（阈值级）

复用 `agents/engineering/threshold_intake.py` 双签机制 + `review_log` 链：

1. **主理人核准**：主理人人工写入 `verified_by` / `verified_at`（标识符来自 `experts.json` 中 `sod_role=principal` 主体），落 `review_log` 第二类 intake 事件。
2. **行业专家复核签**：行业专家人工写入 `expert_verified_by` / `expert_verified_at`（标识符来自 `experts.json` 中 `sod_role=expert` 主体），落 `review_log` 第三类 intake 事件。
3. **SoD 约束**：`expert_verified_by ≠ verified_by`（专家不得为主理人本人）。
4. **落点**：双签均落 `review_log`（append-only 事件链），与 `verified.json` 双签位（`verified_by` / `expert_verified_by`）对应。

**失败处理**：SoD 冲突 / 缺任一签 / 审核链断裂 → 拒绝转正，保持 `verified=false`。

---

## 2. G6 流程（发布级书面授权）

复用 `agents/engineering/release/approval.py` 七字段 `EngineeringReleaseApproval`：

- 七字段：`approval_id` / `interface` / `scope` / `authorized_by` / `effective_time` / `rollback_owner` / `approval_document_ref`。
- 流程：主理人书面创建 `EngineeringReleaseApproval`（scope 如 `wind_pressure`，指定 `rollback_owner`，满足 `authorized_by ≠ rollback_owner`）→ 落 `release_approvals.jsonl`（append-only）。
- `can_enable_engineering` 以 G6 `authorization_present` 作为唯一可信源之一；无授权即无效。
- **落点**：G6 授权落 `release_approvals.jsonl`（独立专表）；`approved_monitor.jsonl` 仅作激活后监控落点，不复用为授权落点。

**失败处理**：缺 G6 授权 / `authorized_by = rollback_owner` / 落点未决 → 拒绝放行，不创建 `ReleaseApproval` 占位、不输出 approved。

---

## 3. SoD 规则（全程）

| 约束 | 规则 | 校验位置 |
|---|---|---|
| 阈值双签 SoD | `expert_verified_by ≠ verified_by` | `threshold_intake.expert_recheck` |
| G6 授权 SoD | `authorized_by ≠ rollback_owner` | `release/readiness.py` SoD 软约束 |
| G6 主体独立 | G6 授权签署人须独立于 3.2.4 双签主体（verified_by / expert_verified_by） | 主理人审核时人工确认 |
| 回滚就绪 | `rollback_owner` 须为可承接回滚的责任主体，独立于授权人 | `release_precheck` G5 |

---

## 4. 签署落点确认建议

- **双签**：落 `review_log`（四类 intake 事件链）。
- **G6 授权**：落 `release_approvals.jsonl`（独立专表，append-only）。
- **激活后监控**：落 `approved_monitor.jsonl`（仅监控，不作为授权/双签落点）。
- 复用 `experts.json` 的 `sign_scope` 字段约束每个主体的可签范围（`verified_by` / `expert_verified_by` / `authorized_by` / `rollback_owner`），与 `signer_alignment` 映射一致。

---

## 5. 收口判定（本 Sprint）

本任务仅产出**签署计划**，不执行签署 → 计为 3.3.1 任务5 DONE（计划态）。真实签署执行留待 3.3.5（须主理人审核 + 单独书面授权）。

*防编造声明：本文档所有签署字段、七字段、SoD 规则均为代码既有定义引用或占位，非真实工程参数；真实专家身份、签名、授权均 pending_verification。*
