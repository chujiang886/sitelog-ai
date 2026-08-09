# BOIP Phase 3.6.0 — Controlled Human Activation Execution (DRILL) 执行报告

- **Phase**：3.6.0
- **标题**：Controlled Human Activation Execution（首次人工受控激活执行 · 演练）
- **日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **模式**：DRILL（所有人工专属输入均为 `DRILL-*` 占位符；AI **仅运行真实工作流机制与校验**，绝不伪造真实数据或代行人工动作）
- **结论**：**NO-GO**（fail-closed 安全机制维持；红线 5 条 0 违规）
- **权威证据**：`.ai/phase3.6.0_drill/result.json`（286 行，六任务 + 红线全字段）
- **演练入口**：`.ai/phase3.6.0_drill_run.py`（位于 `.ai/` 根，与真实 repo 隔离于 `.ai/phase3.6.0_drill/`）

---

## 0. 摘要（Executive Summary）

Phase 3.3 / 3.4 / 3.5.0 均已 ✅ 收口，本阶段执行**首次人工受控激活的端到端演练（DRILL）**：沿 G1–G6 激活闸门，把真实工作流机制（Threshold Intake → G2 双签 → G4 审核链 → G6 授权 → UnifiedActivationGate → Rollback Dry Run）完整跑通一遍，验证机制在 fail-closed 前提下**可被人工在真实场景下走通**，同时严守 5 条红线、绝不翻转 `engineering_enabled`、绝不输出 `engineering_approved`、绝不代建 `ReleaseApproval`、绝不代专家/主理人签署或授权。

**核心结论**：
- ✅ 六任务机制全部跑通（Task1–Task6 证据齐全）。
- ✅ 红线 6 项校验**全 True**（含真实参数 / 专家签名 / 主理人授权均未伪造）。
- ⛔ 顶层 `UnifiedActivationGate`  verdict = **NO-GO**：因 knowledge 域无 `Engineering_Approved` 候选 + 全局 `engineering_enabled` 须保持 `False`，fail-closed 默认全 FAIL。
- 🔬 **接口级诊断**：仅注入 `wind_pressure` 接口所需的 E-TH-01/02/03（排除全局表中仍 draft 的 D-TH）且假设 CI/回滚/授权到位时，阈值域 G1–G6 **全 PASS** —— 证明数据路径在人工补齐真实资料后**可行**，仅因 fail-closed 安全机制维持 NO-GO，符合"不进入真实激活态"红线。

---

## 1. 最高红线（5 条禁止）+ DRILL 占位符约定

### 1.1 五条红线（绝不可逾越）

| # | 禁止项 | 本阶段守约情况 |
|---|---|---|
| ① | AI 生成真实工程参数 | ✅ `real_params_not_generated=True`；所有 value 均为 `__DRILL_PLACEHOLDER__` |
| ② | AI 生成专家签名 | ✅ `expert_signature_not_faked=True`；专家身份仅 `DRILL-EXPERT-002` 占位 |
| ③ | AI 代替主理人授权 | ✅ `principal_authorization_not_faked=True`；主理人身份仅 `DRILL-PRINCIPAL-001` 占位 |
| ④ | AI 自动创建 ReleaseApproval | ✅ `release_approval_not_created_by_ai=True`；AI 仅 `validate_release_approval`，未调 `append_approval_record` |
| ⑤ | 自动开启 `engineering_enabled` | ✅ `engineering_enabled_still_false=True`；演练前后恒 `False`；`engineering_approved_never_written=True` |

### 1.2 DRILL 占位符约定（本阶段关键设计）

因红线②③⑤，所有**人工专属输入**均以明确 `DRILL-*` 标识符占位，使 AI 可跑机制与校验而**不伪造**任何真实身份/数值/授权：

- 主理人身份：`DRILL-PRINCIPAL-001`
- 专家身份：`DRILL-EXPERT-002`
- 回滚责任人：`DRILL-ROLLBACK-003`
- 授权人：`DRILL-AUTHORIZER-004`
- 阈值数值：`value="__DRILL_PLACEHOLDER__"`，`unit="DRILL-UNIT"`
- 来源引用：`source_ref` 用确定性 `compute_content_hash(f"DRILL-SPEC-CONTENT-{tid}")` 生成 64 位 sha256（满足 C5 可追溯，但内容为 DRILL 占位，非真实规范条文）

> ⚠️ **所有 DRILL 占位符在真实激活时须由主理人/专家以真实资料替换**；本阶段产出**不构成**任何真实生效的签署、授权或参数记录。

---

## 2. 六任务执行结果

### 任务 1 — 真实 Threshold Intake（E-TH-01 / E-TH-02 / E-TH-03）

必经四步：`submit → review_approve → expert_recheck → threshold_verified`，每步落 `review_log.jsonl`，终态写入 `verified.json`。

| 阈值 | submit | review_approve | expert_recheck | threshold_verified | 双签转正 |
|---|---|---|---|---|---|
| E-TH-01 | ✅ | ✅ | ✅ | ✅ | ✅ |
| E-TH-02 | ✅ | ✅ | ✅ | ✅ | ✅ |
| E-TH-03 | ✅ | ✅ | ✅ | ✅ | ✅ |

- `all_verified = True`
- `source_passed = True`（占位来源引用通过校验）
- `verification_status = pending_verification`（仍为占位资料，待真实录入）
- `gate_allowed = False` / `engineering_enabled = False`：四步转正**不等于**解锁工程态——仍受 `engineering_enabled` 闸门约束（符合设计）。

### 任务 2 — G2 双签验证（SoD）

| 阈值 | verified_by | expert_verified_by | SoD（专家≠主理人） |
|---|---|---|---|
| E-TH-01 | DRILL-PRINCIPAL-001 | DRILL-EXPERT-002 | ✅ |
| E-TH-02 | DRILL-PRINCIPAL-001 | DRILL-EXPERT-002 | ✅ |
| E-TH-03 | DRILL-PRINCIPAL-001 | DRILL-EXPERT-002 | ✅ |

- `sod_ok = True`，`all_signed = True`
- SoD 规则：`expert_verified_by` 必须与 `verified_by` 为不同身份（职责分离硬校验，`sod_principal_ne_expert = True`）。

### 任务 3 — G4 审核链验证

- `event_count = 12`（3 阈值 × 4 类事件）
- 四类规范事件齐全：`submit / review / expert_recheck / verified`
- `chain_intact = True`（`prev_event_id` 链式无断裂）
- `required_actions_present = True`，`all_thresholds_have_full_chain = True`
- `g4_pass = True`

### 任务 4 — G6 授权（AI 仅 validate）

- `approval_validated_by_ai = True`，**`approval_created_by_ai = False`**（红线④守约）
- `seven_fields_present = True`（approval_id / interface / scope / authorized_by / effective_time / rollback_owner / approval_document_ref）
- `validation_errors = []`，`is_effective = True`
- `sod_authorized_by_ne_rollback_owner = True`（授权人 ≠ 回滚责任人，职责分离）
- `g6_mechanism_ready = True`
- 说明：真实 `EngineeringReleaseApproval` 须由主理人**书面创建**并 append-only 落盘 `release_approvals.jsonl`；AI 仅校验其存在性/合法性/SoD。

### 任务 5 — UnifiedActivationGate（G1–G6）

运行模式：`fail-closed`（无外部条件注入）→ `allowed = False`，`verdict = NO-GO`，`safety_invariants_ok = True`。

三域闸门结果：

| 域 | G1 | G2 | G3 | G4 | G5 | G6 | 域 verdict |
|---|---|---|---|---|---|---|---|
| knowledge | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| threshold | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| publishing | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |

顶层阻塞原因（节选）：
- `[knowledge] G1_knowledge_governance_incomplete:no_Engineering_Approved_candidate`
- `[knowledge]/[threshold]/[publishing] G2_dual_sign_incomplete`
- `[*] G3_ci_not_green`、`G5_rollback_not_ready`、`G6_authorization_missing`

### 任务 6 — Rollback Dry Run

| 步骤 | 结果 | 说明 |
|---|---|---|
| snapshot | ✅ | 写入 `snapshots/gray_release.*.snapshot.json` |
| disable | ✅ | 关闭 `wind_pressure` 接口灰度（恢复 `pending_verification`） |
| rollback | ✅ | 全局熔断/接口关闭，恢复 `pending_verification` |
| restore | ✅ | 从快照恢复灰度配置 |

- `gray_allowed_before_dryrun = False`，`gray_allowed_after_dryrun = False`（全局闸门 `engineering_enabled=False` 时 `is_interface_gray_allowed` 恒 False，不可绕过）
- `review_log_untouched = True`（回滚流程仅动 `GrayReleaseConfig`，不触碰 `review_log`/`verified.json`）
- `mechanism_ok = True`

---

## 3. 红线校验汇总

`result.json → red_lines` 全部为 `True`：

| 校验项 | 结果 |
|---|---|
| `engineering_enabled_still_false` | ✅ True |
| `engineering_approved_never_written` | ✅ True |
| `release_approval_not_created_by_ai` | ✅ True |
| `real_params_not_generated` | ✅ True |
| `expert_signature_not_faked` | ✅ True |
| `principal_authorization_not_faked` | ✅ True |

---

## 4. 接口级 vs 全局级 G1/G2 诊断差异（关键澄清）

顶层 `can_enable_engineering` 评估的是**全局合并表**（E-TH + 全局表中仍 `draft` 的 D-TH）。因此：

- **全局诊断**：因存在仍 `draft` 的 D-TH，全局 G1/G2 默认 FAIL（符合"未全量转正不解锁"设计）。
- **接口级诊断（`diagnostic_interface_scoped`）**：仅注入 `wind_pressure` 所需的 **E-TH-01/02/03**（排除 draft 的 D-TH），并假设 CI 绿 / 回滚就绪 / G6 授权到位 → **阈值域 G1–G6 全 PASS**、发布域 G1–G6 全 PASS；仅 `knowledge` 域因无 `Engineering_Approved` 候选而受阻，整体仍 `NO-GO`。

> 该诊断**仅用于证明机制可行性**，不改变任何真实状态，亦不绕过红线。它说明：当主理人补齐真实 E-TH 数值、完成真实双签/审核链/G6 授权、CI 8/8 绿、回滚就绪后，对应接口的数据路径可满足 G1–G6；但**统一闸门仍须 knowledge 域放行**（即主理人显式置 `engineering_enabled=true` 并在治理层确认）方翻 GO。

---

## 5. 结论

1. **机制可行**：G1–G6 全链路（Intake → G2 双签 → G4 审核链 → G6 授权 → UnifiedActivationGate → Rollback）在 fail-closed 前提下**可被真实工作流走通**，演练证据完整。
2. **红线 0 违规**：5 条红线 + 防伪造 6 项校验全部通过。
3. **维持 NO-GO**：因 knowledge 域无 `Engineering_Approved` 候选 + 全局 `engineering_enabled` 须保持 `False`，顶层 verdict = **NO-GO**。
4. **停止**：按指令，完成后停止。未开启 `engineering_enabled`，未输出 `engineering_approved`，未代建 `ReleaseApproval`，未代专家/主理人签署或授权。

---

## 6. 交付物清单

| 类型 | 路径 |
|---|---|
| 执行报告 | `.ai/reviews/phase3.6.0_controlled_activation_execution_report.md`（本文件） |
| 权威证据 | `.ai/phase3.6.0_drill/result.json` |
| 演练入口脚本 | `.ai/phase3.6.0_drill_run.py`（位于 `.ai/` 根，隔离于 `.ai/phase3.6.0_drill/`） |
| SSOT 更新 | `.ai/project_status.json`（current_roadmap_version → V6；新增 `phase_3_6` 块） |
| 路线更新 | `.ai/roadmap_v6.md`（取代 V5） |

---

## 7. 下一步（人工动作，非 AI 范畴）

解锁真实激活态须主理人逐项完成（沿用 §3.2 前置清单，且全部为线下/人工动作）：

1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD，替换 DRILL 占位）；
2. 确认 `review_log` 含完整四类规范事件且链式无断裂；
3. 线下创建 **真实** `EngineeringReleaseApproval`（七字段齐全、SoD、`effective_time` 生效），append-only 落盘 `release_approvals.jsonl`；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. **显式**置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

> 禁止自动激活：无论 CI 是否全绿、治理流程是否齐备，AI 不得自动置 `engineering_enabled=true`、不得输出 `engineering_approved`、不得代建 `ReleaseApproval`、不得代专家/主理人签署或授权。
