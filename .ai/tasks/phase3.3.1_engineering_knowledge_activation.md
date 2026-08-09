# Phase 3.3 Sprint 3.3.1 — Real Engineering Knowledge Activation（pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation（真实工程知识接入）
**Sprint**：3.3.1 Real Engineering Knowledge Activation
**身份**：BOIP AI Chief Architect（知识接入基座设计）
**日期**：2026-08-01
**前置**：Phase 3.2 已正式收口（`.ai/reviews/phase3.2_closing_report.md`），工程审核闭环治理与基础设施 inert 就绪。

---

## 0. 目标与红线

**目标**：建立「真实工程知识接入」的**管理基座**——规范来源、专家资料、阈值录入、规范版本、专家签署五类管理能力的容器与计划。本 Sprint **仅建管理基座，不录入任何真实数据**。

**红线（不可逾越）**：

| # | 禁止项 | 说明 |
|---|---|---|
| 1 | 录入真实参数 | `E-TH-01/02/03` 真实 `value` 由人工经 `ThresholdIntakeWorkflow` 另行填写，本 Sprint 不填 |
| 2 | 开启 `engineering_enabled=true` | 全局仍 `false`；基座就绪不改变该约束 |
| 3 | 输出 `engineering_approved` | 全 `pending_verification`，无 approved 落盘/输出 |

> 沿用 Phase 3.2 已建能力：`ThresholdSourceRef`（C1-C6 校验）、`ThresholdIntakeWorkflow`（六字段 + 双签 SoD）、`can_enable_engineering`（G1-G6 默认拒绝）、`review_log` / `release_approvals.jsonl` 容器。**本 Sprint 只编排「这些容器如何被真实知识填充」，不实际填充。**

---

## 1. 任务1：真实规范来源管理（Real Spec Source Management）

**目标**：建立真实规范（GB 50009 建筑结构荷载规范 / GB 5237 铝合金建筑型材 等）的**来源元数据登记基座**，使每条阈值 `source_ref` 可追溯到权威出处。

**输入**：
- 规范清单（标准号 / 名称 / 发布机构 / 版本 / 获取渠道）——由人工/规范提供方提供。
- 既有 `ThresholdSourceRef` 结构化 schema（standard/clause/edition/url/retrieved_at）。

**输出（仅设计/登记容器，不拉取真实条款内容）**：
- 规范来源登记表（建议 `agents/engineering/knowledge/spec_sources.json` 占位骨架）：每条含 `standard / title / publisher / edition / official_url / retrieved_at / clause_index`。
- 来源登记流程说明：登记 → `validate_source_ref` C1-C6 校验 → 准入；缺项即拒，不入库。
- 来源与 `E-TH` 阈值 `source_ref` 的映射约定。

**负责人**：规范提供方 + 主理人审核；AI 仅编排容器与校验逻辑。
**失败处理**：来源缺 C1-C6 任一项 → 拒绝登记，标记 `pending_verification`，不降级强行入库。
**不变量**：不写入真实规范条款数值；`engineering_enabled` 不变；`verified.json` 不改动。

---

## 2. 任务2：专家资料管理（Expert Profile Management）

**目标**：建立可签署真实阈值/授权的**专家资料基座**，与 `review_log` signer 标识符体系对齐，为后续双签 + G6 授权提供主体清单。

**输入**：
- 专家领域清单（风工程 / 结构 / 型材 / 五金 / 安装 等）。
- 既有 `review_log` 事件-签名链 signer 标识符约定（`principal-xxx` / `expert-xxx`）。

**输出（仅资料容器，非真实身份落盘）**：
- 专家资料登记表（建议 `agents/engineering/knowledge/experts.json` 占位骨架）：每条含 `expert_id / domain / qualification_ref / sign_scope / sod_role`（主理人 vs 专家）。
- 专家与 `ThresholdIntakeWorkflow` 双签位（`verified_by` / `expert_verified_by`）、G6 授权位（`authorized_by` / `rollback_owner`）的标识符对齐规则。
- SoD 校验约定：`expert_verified_by ≠ verified_by`；`authorized_by ≠ rollback_owner`。

**负责人**：主理人 + 人事/资质审核；AI 仅编排容器与 SoD 规则。
**失败处理**：专家缺资质引用或 SoD 角色冲突 → 标记 `pending_verification`，不纳入签署主体。
**不变量**：不填写真实专家姓名/证书号；不生成签名；`engineering_enabled` 不变。

---

## 3. 任务3：真实阈值录入计划（Real Threshold Entry Plan）

**目标**：编排 `E-TH-01/02/03` 真实阈值经 `ThresholdIntakeWorkflow` 录入的**执行计划**（谁、经何流程、何时），本 Sprint **不执行录入**。

**输入**：
- 既有 `ThresholdIntakeWorkflow`（submit→review→expert_recheck→finalize_verified，六字段，双签 SoD，`evaluate_gates` 恒 `False`）。
- 待录入阈值 `E-TH-01`(风压相关) / `E-TH-02` / `E-TH-03`。

**输出（计划文档，非执行）**：
- 录入步骤编排：授权边界 → `build_source_verification_report`(C1-C6) → submit → review_approve → expert_recheck → finalize_verified。
- 执行人/复核人/时间窗规划（由人工指定，AI 不代填真实值）。
- 录入前置门禁清单：G1（governance_status=ok）、G2（双签齐备）、G4（review_log 四类事件）须在录入后满足。

**负责人**：阈值提供方（录入）+ 主理人（review）+ 专家（recheck）；AI 仅编排流程。
**失败处理**：source_ref 未通过 C1-C6 / 双签 SoD 冲突 / 缺主理人复核 → 拒绝录入，保持 `value=null`。
**不变量**：不以真实数据调用 `ThresholdIntakeWorkflow`；不写 `verified.json` 真实 value；`engineering_enabled` 不变。

---

## 4. 任务4：规范版本管理（Spec Version Management）

**目标**：确立真实规范与阈值的**版本管理策略**，使 `schema_version` 与每条 `version` 语义化、历史可回溯、deprecated 可回滚。

**输入**：
- 既有 `ThresholdGovernanceView`（schema_version / version / deprecated 拒绝加载）。
- 阈值迁移工具（`threshold_migration.py` v1→v2，失败自动回滚）。

**输出（策略与约定，非数据变更）**：
- 版本策略：`schema_version` 全局常量 + 每条 `version` 语义化（如 `GB 50009-2012`）；多阈值聚合取「最小版本」或「联合版本字符串」约定（沿用 3.2.5-A open_decision）。
- 历史保留约定：deprecated 条目保留供降级展示，不物理删除；回滚路径 = 快照 + deprecated + 审核链不可篡改。
- 版本冲突处理：同一 `applies_to_scheme` 出现版本冲突 → deprecated 拒绝加载，标记 `pending_verification`。

**负责人**：主理人 + 规范提供方；AI 仅编排策略。
**失败处理**：版本冲突或无 `version` → 拒绝加载并告警，不静默采用。
**不变量**：不修改生产 `verified.json`；不触发迁移工具写入；`engineering_enabled` 不变。

---

## 5. 任务5：专家签署计划（Expert Signing Plan）

**目标**：编排真实阈值双签 + G6 主理人书面授权的**签署计划**（流程、落点、SoD），本 Sprint **不执行签署**。

**输入**：
- 既有双签机制（`ExpertBackedEngineeringValidation` 四签状态机 + `review_log` 链）。
- 既有 `EngineeringReleaseApproval` 七字段（approval_id/interface/scope/authorized_by/effective_time/rollback_owner/approval_document_ref）。
- 既有 open_decision：监控落点（独立专表 vs 复用 review_log）、SoD 主体边界。

**输出（计划文档，非签署）**：
- 双签签署流程：主理人 `verified_by/at` → 专家 `expert_verified_by/at`（SoD，专家≠主理人）→ 落 `review_log` 四类 intake 事件。
- G6 授权签署流程：主理人书面 `EngineeringReleaseApproval`（scope=wind_pressure，指定 `rollback_owner`，满足 `authorized_by ≠ rollback_owner`）→ 落 `release_approvals.jsonl`。
- 签署落点确认建议：双签落 `review_log`；G6 授权落 `release_approvals.jsonl`（独立专表）；`approved_monitor.jsonl` 仅作激活后监控落点。
- SoD 复核清单：`expert_verified_by ≠ verified_by`、`authorized_by ≠ rollback_owner`、G6 授权签署人独立于 3.2.4 双签主体。

**负责人**：主理人（主签 + G6 授权）+ 专家（复核签）；AI 仅编排流程与 SoD 校验。
**失败处理**：SoD 冲突 / 落点未决 → 标记 `pending_verification`，不创建 `ReleaseApproval`、不输出 approved。
**不变量**：不代签、不代授权；不创建 `release_approvals.jsonl`；不输出 `engineering_approved`；`engineering_enabled` 不变。

---

## 6. 收口与下一步

**本 Sprint 交付物（建议）**：
- `agents/engineering/knowledge/spec_sources.json`（占位骨架）
- `agents/engineering/knowledge/experts.json`（占位骨架）
- `.ai/tasks/phase3.3.1_engineering_knowledge_activation.md`（本文件）
- 真实阈值录入计划 / 规范版本管理策略 / 专家签署计划（文档）

**收口判定**：五类管理基座（来源/专家/阈值录入计划/版本/签署计划）容器与流程就绪 → 3.3.1 DONE（基座态）。
**红线守约核验**：未录入真实参数（E-TH 仍 null）/ 未开 `engineering_enabled`（仍 false）/ 未输出 `engineering_approved` / 未创建 `ReleaseApproval` / 全 `pending_verification`。

**下一步（后续 Sprint，待本基座就绪后定义）**：真实规范 ingestion → 真实专家 onboarding → 真实阈值录入执行（人工经 `ThresholdIntakeWorkflow`）→ 真实签署执行（双签 + G6）→ 重跑 `release_precheck` 复核各门禁全绿 → RC 转 GO → `gray_release_ctl.py enable wind_pressure`。

*防编造声明：本任务所有规范号（GB 50009 / GB 5237 等）、E-TH 标识符、版本号均为引用或占位，非真实工程参数；真实数值、专家身份、签名、授权均 pending_verification，由人工经正式流程提供。*
