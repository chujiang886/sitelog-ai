# Phase 3.6.2 — Activation Evidence Validation Dry Run（激活证据验证演练）

> **身份**：BOIP AI Chief Architect
> **阶段定位**：Phase 3.6.0 ✅ DRILL PASS（机制可运行）→ Phase 3.6.1 ✅ Real Activation Evidence Preparation（模板/映射/清单）→ **Phase 3.6.2 激活证据验证演练（结构验证，非真实录入）**
> **执行时间（本地）**：2026-08-03（dry run 产物 `generated_at = 2026-08-02T16:32:05Z`）
> **激活态结论**：**NO-GO 维持**（`engineering_enabled = false`，未翻转、未授权、未代签）
> **六条红线**：**0 违规**

---

## 0. 摘要（Executive Summary）

本阶段是对 **Phase 3.6.1 产出证据包模板/映射** 的一次**纯结构验证演练（Dry Run）**：我们构建一个内存态的 `ActivationEvidenceBundle`，喂入**真实闸门的校验代码**（`UnifiedActivationGate` / `can_enable_engineering` / `check_e_th_realization` / `validate_release_approval` / `review_log` 链式校验），验证「四类证据（Threshold / Expert / Approval / Rollback）的结构是否满足 G1–G6 输入要求」，而**不改变任何真实激活状态**。

**核心结论**：

1. **结构完整性（任务1）** — 四类证据字段齐全（Threshold 12 项 / Expert 5 项 / Approval 7 项 / Rollback 4 项），`all_complete = True`。
2. **G1–G6 输入格式（任务2）** — 在「CI 绿 / 回滚就绪 / 授权到位 / 审核链完整 / 阈值结构完整」的模拟输入下，`can_enable_engineering` 返回 `(allowed=True, reasons=[])`，证明**阈值域 bundle 输入格式被 gate 完全接受**；阈值域 G1–G6 全 `True`。但统一决策因知识域无仓库候选（G0）+ 发布域 G4 无仓库审计 → **verdict = NO-GO**（fail-closed 正确）。
3. **职责分离 SoD（任务3）** — 四角色两两异身份，`sod_ok = True`。
4. **可追溯性（任务4）** — 12 个审核事件、REQUIRED_FIELDS 齐全、event_id 确定性可重算、链式无断裂、source_ref.hash 64-hex、时间均为 ISO8601，`traceable = True`。
5. **G6 仅校验不创建（任务5）** — `validate_release_approval` 七字段有效，但 **AI 未调用 `append_approval_record`**（`approval_created_by_ai = False`）。
6. **红线 6/6 守约** — 见 §7。

> ⚠️ **诚实性声明**：bundle 中 `value/unit` 使用代码库自身「待人工填入」标记 `pending_verification`（非伪造真实数值）。`check_e_th_realization` 诚实判定 `real_data_present = False`——**尚未填入真实工程参数（红线①守约）**。本演练仅证明「结构骨架」可被 gate 接受，不等于已具备真实激活资格。

---

## 1. 身份与红线

**身份**：BOIP AI Chief Architect（仅运行机制与校验，不代行任何人工专属动作）。

**六条最高红线（全程禁止，本次 0 违规）**：

| # | 红线 | 本次守约判定 | 证据 |
|---|---|---|---|
| ① | AI 生成真实工程参数 | ✅ 守约 | `value/unit = "pending_verification"`，`real_data_present=False` |
| ② | AI 生成真实专家身份 | ✅ 守约 | 专家仅 `DRILL-EXPERT-002` 占位，未编造真实姓名/资质 |
| ③ | AI 代签 | ✅ 守约 | 双签仅为 DRILL 占位标识符，未生成真实签名 |
| ④ | AI 创建 ReleaseApproval | ✅ 守约 | 仅 `validate_release_approval`，未调 `append_approval_record` |
| ⑤ | 自动开启 `engineering_enabled` | ✅ 守约 | 全演练 `engineering_enabled` 恒 `False` |
| ⑥ | 输出 `engineering_approved` | ✅ 守约 | 仅输出 `NO-GO` 决策，未输出 `engineering_approved` |

**附加守约**：未触碰任何真实证据文件（`verified.json` / `review_log.jsonl` / `release_approvals.jsonl` 均未修改）。

---

## 2. 任务1 — Evidence Bundle 完整性验证

### 2.1 `ActivationEvidenceBundle` 结构（纯内存）

```python
ActivationEvidenceBundle = {
    interface,                  # "wind_pressure"
    threshold_evidence,         # E-TH-01/02/03 三条阈值证据
    expert_evidence,            # 专家签署证据（模板结构）
    approval_evidence,          # G6 授权证据（七字段结构）
    rollback_evidence,          # 回滚责任人证据
    roles,                      # verified_by / expert_verified_by / authorized_by / rollback_owner
}
```

> 该 bundle **仅做结构校验**，不落真实证据文件（与 3.6.1 模板一致，演练隔离）。

### 2.2 四类证据完整性结果

| 证据类别 | 校验字段数 | complete | missing |
|---|---|---|---|
| **Threshold Evidence** | 12（THRESHOLD_FIELDS） | ✅ True | `{}` |
| **Expert Evidence** | 5（EXPERT_FIELDS） | ✅ True | `[]` |
| **Approval Evidence** | 7（APPROVAL_FIELDS） | ✅ True | `[]` |
| **Rollback Evidence** | 4（ROLLBACK_FIELDS） | ✅ True | `[]` |

**`all_complete = True`** —— 证据包四类结构全部满足 G1–G6 输入要求。

- **Threshold Evidence** 字段（E-TH-01/02/03 各条）：`threshold_id / value / unit / threshold_status / version / verified / verified_by / verified_at / expert_verified_by / expert_verified_at / source_ref(hash) / applies_to`，双签齐全、`threshold_status=verified`、`source_ref` 含 64-hex hash。
- **Expert Evidence** 字段：`qualification / domain / sign_scope / signature_record.is_ai_generated(=false) / expert_verified_by`。
- **Approval Evidence** 字段（G6 七字段）：`approval_id / interface / scope / authorized_by / effective_time / rollback_owner / approval_document_ref`。
- **Rollback Evidence** 字段：`rollback_owner / snapshot_ref / disable_action / restore_action`。

---

## 3. 任务2 — G1–G6 输入格式验证（不改变激活态）

### 3.1 模拟输入（DRILL 占位 + 机制就绪态）

- `thresholds`：E-TH-01/02/03 三条，结构完整（`value/unit=pending_verification`，双签齐全，source_ref 完整）。
- `ci_green = True`、`rollback_ready = True`、`authorization_present = True`、`require_audit_chain = True`。
- `review_log_path`：指向演练目录 `review_log.jsonl`（12 事件，四类齐全，链式无断裂）。
- `context = ActivationContext(...)`：双签/CI/回滚/授权/审核链标志齐备。

### 3.2 阈值域门禁结果（核心证据）

调用 `can_enable_engineering(thresholds, ci_green=True, rollback_ready=True, authorization_present=True, review_log_path, require_audit_chain=True)`：

```json
{
  "threshold_domain_allowed": true,
  "threshold_domain_reasons": [],
  "threshold_domain_gate_format_accepted": true
}
```

→ **阈值域 G1–G6 全 `True`**，证明 bundle 输入格式被 gate **完全接受**。

| 闸门 | 域 | 结果 | 说明 |
|---|---|---|---|
| G1 governance | 阈值域 | ✅ True | `governance_status` 结构校验（不读 value） |
| G2 dual_sign | 阈值域 | ✅ True | `is_fully_verified` 双签齐全（不读 value） |
| G3 ci | 阈值域 | ✅ True | `ci_green=True` |
| G4 audit_chain | 阈值域 | ✅ True | review_log 链式完整 |
| G5 rollback | 阈值域 | ✅ True | `rollback_ready=True` |
| G6 authorization | 阈值域 | ✅ True | `authorization_present=True` |

### 3.3 统一决策（UnifiedActivationGate）

调用 `UnifiedActivationGate().evaluate(repository=None, context=ActivationContext(...), thresholds, review_log_path)`：

| 域 | G1 | G2 | G3 | G4 | G5 | G6 | 域 verdict |
|---|---|---|---|---|---|---|---|
| knowledge | null | null | null | null | null | null | 需仓库（G0_repository_required） |
| threshold | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | PASS |
| publishing | ✅ | ✅ | ✅ | ❌ False | ✅ | ✅ | G4 无仓库审计 → FAIL |

```json
{
  "unified_verdict": "NO-GO",
  "unified_decision_well_formed": true,
  "real_data_present": false
}
```

**顶层不变量**：`safety_ok = load_engineering_enabled() is False` → `True`；但 `allowed = safety_ok and all(domains)` 因 knowledge 域无仓库（G0）+ publishing G4 无仓库审计 → **恒 NO-GO**（fail-closed 正确）。

> 📌 **关键澄清**：阈值域 G1–G6 全 PASS **仅证明输入格式/结构被 gate 接受**；统一决策仍 NO-GO，因（a）知识域需真实知识仓库候选且未达 `Engineering_Approved`，（b）发布域 G4 需仓库审计链。本演练**未改变激活态**，与红线⑤⑥一致。

---

## 4. 任务3 — SoD（职责分离）验证

四角色映射（DRILL 占位标识符）：

| 角色 | 占位标识 |
|---|---|
| `verified_by`（主理人） | `DRILL-PRINCIPAL-001` |
| `expert_verified_by`（专家） | `DRILL-EXPERT-002` |
| `authorized_by`（授权人） | `DRILL-AUTHORIZER-004` |
| `rollback_owner`（回滚责任人） | `DRILL-ROLLBACK-003` |

SoD 检查（硬约束 + 软约束）：

| 检查项 | 约束类型 | 结果 |
|---|---|---|
| `expert_verified_by != verified_by` | 硬（专家≠主理人） | ✅ True |
| `authorized_by != rollback_owner` | 软（授权人≠回滚责任人） | ✅ True |
| `expert_verified_by != authorized_by` | 软（专家≠授权人） | ✅ True |
| `verified_by != rollback_owner` | 软（主理人≠回滚责任人） | ✅ True |

**`sod_ok = True`** —— 四角色职责分离在结构上满足 G2/G6 SoD 要求。

---

## 5. 任务4 — Evidence Hash / 版本 / 时间可追溯性

| 校验维度 | 方法 | 结果 |
|---|---|---|
| **Hash 算法** | `review_log.compute_event_id` 确定性 sha256 | ✅ 64-hex |
| **事件数** | 读 `review_log.jsonl`，按 tid×动作计数 | ✅ 12 事件 |
| **事件 id 可重算** | 用 REQUIRED_FIELDS 重算 event_id 比对落盘值 | ✅ 一致 |
| **链式完整性** | `prev_event_id` 指针逐跳校验无断裂 | ✅ intact |
| **REQUIRED_FIELDS 齐全** | 8 项必填字段逐事件检查 | ✅ 无缺失 |
| **source_ref.hash** | 64-hex 校验 | ✅ 通过 |
| **时间 ISO8601** | `datetime.fromisoformat` 校验 `verified_at`/`expert_verified_at`/`effective_time` | ✅ 通过 |
| **版本字段** | `version` 字段存在（默认 `1.0.0`） | ✅ 通过 |

**`traceable = True`，`issues = []`** —— 文件引用 / hash / 版本 / 时间全链路可追溯。

---

## 6. 任务5 — G6 Approval 仅校验（Validate-Only）& 最终报告

### 6.1 G6 校验（不创建）

```json
{
  "validate_only": true,
  "seven_fields_valid": true,
  "errors": [],
  "approval_created_by_ai": false
}
```

`validate_release_approval` 七字段 + `effective_time` ISO8601 + SoD 软校验全过；**AI 仅 validate，绝不 `append_approval_record`**（红线④守约）。

### 6.2 红线 6/6 守约汇总

```json
{
  "engineering_enabled_still_false": true,
  "real_params_not_generated": true,
  "expert_identity_not_fabricated": true,
  "release_approval_not_created_by_ai": true,
  "engineering_approved_not_output": true,
  "real_files_untouched": true
}
```

### 6.3 最终 verdict

```
verdict         = NO-GO
engineering_enabled = false
real_data_present   = false
```

---

## 7. 交付物清单（本阶段产出）

| 文件 | 类型 | 说明 |
|---|---|---|
| `.ai/reviews/phase3.6.2_activation_evidence_validation_dry_run.md` | 报告 | 本报告（任务5 主交付物） |
| `.ai/phase3.6.2_validation_run.py` | 脚本 | 纯内存 bundle + 真实 gate 校验（位于 `.ai/` 根，隔离于演练子目录） |
| `.ai/phase3.6.2_dryrun/result.json` | 证据 | 权威校验结果（任务1–4 + G6 + 红线） |
| `.ai/phase3.6.2_dryrun/review_log.jsonl` | 证据 | 12 事件审核链（演练副本，非真实文件） |
| `.ai/project_status.json` | SSOT | `roadmap.phase_3_6` 新增 `3.6.2` 块 |
| `.ai/roadmap_v6.md` | 路线 | 新增 § 3.6.2 节 |

> 未修改任何真实业务代码 / 真实证据文件（`verified.json` / `review_log.jsonl` / `release_approvals.jsonl` 均未触碰）。

---

## 8. 诚实性声明（pending_verification）

- 本演练的 `value/unit` 一律使用代码库自身「待人工填入」规范标记 `pending_verification`（与全局 `_PLACEHOLDER_STRINGS` / `DEFAULT_SOURCE_REF_PLACEHOLDER` 约定一致）。
- `check_e_th_realization._is_real_value` 拒绝 `pending_verification` 与 `""`，故 `real_data_present` 诚实为 `False`——**未含任何真实工程参数**。
- G1（governance）/ G2（dual_sign）闸门**不读 value**，仅校验 status / source_ref 完整性 / 双签，因此 `pending_verification` 占位 value 仍能让阈值域 G1–G6 全 PASS，但这**不构成真实激活资格**。

---

## 9. 下一步（收尾，停止）

本阶段按指令**完成后停止**。保持：

- `engineering_enabled = false`（红线⑤）
- 不输出 `engineering_approved`（红线⑥）
- 未创建 ReleaseApproval（红线④）
- 未代签 / 未代授权（红线③）
- 未编造专家身份（红线②）
- 未生成真实工程参数（红线①）

**真实激活解锁须主理人逐项完成（沿用 V6 §3.2 前置清单）**：
1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD，替换 DRILL 占位）；
2. 确认 `review_log.jsonl` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
3. 线下创建**真实** `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

**禁止自动激活**：无论结构验证是否通过、CI 是否全绿，AI 不得自动置 `engineering_enabled=true`、不得输出 `engineering_approved`、不得代建 `ReleaseApproval`、不得代专家/主理人签署或授权、不得伪造真实工程参数。

---

*报告结束。本演练仅验证「证据包结构满足 G1–G6 输入要求」，未改变任何真实激活状态。*
