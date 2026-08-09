# 3.2.5-H4-A Release Runbook（pending_verification）

**阶段**：3.2.5-H4-A（首次受控灰度发布准备 · Release Runbook 设计）（pending_verification）
**角色**：BOIP AI Release Governance 负责人
**日期**：2026-08-01
**目标**：建立首次 `wind_pressure` 灰度执行 Runbook（Pre-check → Authorization → Enable → Monitor → Rollback），每一步明确**负责人 / 输入 / 输出 / 失败处理**。

---

## 0. 红线守约声明（本 Runbook 仅描述流程，不执行、不翻转）

| 红线 | 状态 | 说明 |
|---|---|---|
| 1. 未开启 `engineering_enabled=true` | ✅ 守约 | Runbook 中 `enable` 仅翻转**灰度开关**（`gray_release.json` 的 `entries.wind_pressure.enabled`），**绝不**触碰 `agents/config.yaml` 的 `engineering_enabled`（全局仍 `false`） |
| 2. 未输出 `engineering_approved` | ✅ 守约 | 全文仅引用概念，无任何 approved 输出 |
| 3. 未生成真实工程参数 | ✅ 守约 | 阈值数值（E-TH-01/02/03）仍由人工经 `ThresholdIntakeWorkflow` 提供，本 Runbook 不承载任何数值 |
| 4. 未生成专家签名 | ✅ 守约 | 双签由专家/主理人线下落 `review_log`，Runbook 不代签 |
| 5. 未自动创建 `ReleaseApproval` | ✅ 守约 | G6 授权由主理人书面创建，Runbook 不代建；本阶段 `release_approvals.jsonl` 仍不存在（count=0） |

> 本 Runbook 引用的所有符号均为既有代码事实：`release_precheck()` / `ProductionReadinessChecker` / `can_enable_engineering()`（G1-G6）/ `gray_release_ctl.py`（precheck/enable/disable/rollback/restore）/ `release_audit.jsonl` / `approved_monitor.jsonl` / `review_log.jsonl`。真实放量执行须由人工在各角色就位后按本 Runbook 操作。

---

## 1. 概览

- **首个灰度接口**：`wind_pressure`
- **当前真实态**：G1-G6 全 `false`、就绪度 `0/6 = 0%`、`engineering_enabled = false` → **NO-GO**（详见 `.ai/reviews/phase3.2.5H3B_release_freeze_report.md`）
- **Runbook 性质**：操作手册（不自动执行）；进入 Enable 步骤前必须 G1-G6 全绿且 G6 授权生效
- **关键不变量**：`can_enable_engineering` 委托 + `release_precheck` 默认拒绝 + 全局 `engineering_enabled=false` + `manual_modified_thresholds` 拦截

---

## 2. Runbook 五步

### 2.1 Pre-check（发布前门禁检查）

| 项 | 内容 |
|---|---|
| **负责人** | Release Governance 负责人（或其授权的检查人；本步骤只读，可由发布执行人代跑检查） |
| **输入** | `interface=wind_pressure`；可选注入：`--thresholds <路径>`（阈值条目 JSON）、`--ci-green`（人工确认 CI 绿）、`--rollback-ready`（人工确认回滚就绪）、`--authorized`（声明已获 G6 授权，仅检查 G1-G5）、`--review-log <路径>` |
| **输出** | `ProductionReadinessReport`：`report.allowed`（bool）、`report.gate_status`（G1-G6 + verified_integrity 逐项 bool）、`report.blocking_reasons`（阻断原因列表） |
| **失败处理** | 任一 `G` 为 `false` → 输出 `blocking_reasons` 并**停止**，回到对应人工补齐项（G1/G2 阈值真实化+双签、G3 CI 确认、G4 审核链、G5 回滚就绪、G6 授权）；不得进入 2.2 |

**命令（CLI）**：
```bash
python scripts/release/gray_release_ctl.py precheck \
  --interface wind_pressure \
  [--ci-green] [--rollback-ready] [--authorized] \
  [--review-log <path>] [--thresholds <path>]
# 返回 JSON {"allowed": bool, "reasons": [...]}
```

**命令（代码内）**：
```python
from agents.engineering.release.gate import release_precheck
report = release_precheck(interface="wind_pressure", return_report=True)
# report.allowed / report.gate_status / report.blocking_reasons
```

> 判定链路：`release_precheck` → `ProductionReadinessChecker.run()` → `can_enable_engineering()`（G1-G6 唯一事实来源）。默认所有外部条件取"不满足" → `allowed=False`。

---

### 2.2 Authorization（G6 主理人书面授权）

| 项 | 内容 |
|---|---|
| **负责人** | 主理人（轩哥）——创建 `EngineeringReleaseApproval`；专家负责 G1/G2 双签（阈值真实化） |
| **输入** | `EngineeringReleaseApproval` 七字段：`approval_id` / `interface` / `scope` / `authorized_by` / `effective_time` / `rollback_owner` / `approval_document_ref`；**SoD 约束**：`authorized_by ≠ rollback_owner` 且独立于 3.2.4 双签主体 |
| **输出** | `release_approvals.jsonl` 追加一条记录（append-only，仅引用标识符，无真实数值）；`is_approval_effective()` 须为 `True`（`effective_time` 不晚于当前时刻） |
| **失败处理** | 缺字段 / `interface` 不匹配 / SoD 违例（`authorized_by == rollback_owner`）/ `effective_time` 在未来 → **拒绝创建**，保持 `count=0`、NO-GO；回到主理人补正 |

> ⚠️ **红线 5**：本阶段 AI **不自动创建** `ReleaseApproval`。本步骤由主理人线下经正式流程落库；Runbook 仅描述其字段与校验规则（见 `agents/engineering/release/approval.py` 的 `validate_release_approval` / `is_approval_effective`）。

---

### 2.3 Enable（启用灰度开关）

| 项 | 内容 |
|---|---|
| **负责人** | 发布执行人（`release-operator`） |
| **输入** | 审批通过的 `approval_id`；前置须同时满足：① `release_precheck` `allowed=True`（G1-G6 全绿）；② 授权存在且 `interface` 匹配且已生效；③ 启用前快照可写 |
| **输出** | `gray_release.json` 中 `entries.wind_pressure.enabled = True`（**仅翻转灰度开关**，绝不翻转 `engineering_enabled`）；`release_audit.jsonl` 追加 `enable` 成功记录；返回 `ReleaseResult`（`success=True, snapshot_path`） |
| **失败处理** | `enable_release` 任一前置不满足即拒绝并退出码非 0，审计落 `release_audit.jsonl`：`REJECTED_NO_APPROVAL`（授权缺失/不匹配）/ `REJECTED_NOT_EFFECTIVE`（未生效）/ `REJECTED_GATE_BLOCKED`（G1-G6 未过）/ `REJECTED_SNAPSHOT_FAILED`（快照失败）→ **停止，保持 NO-GO** |

**命令**：
```bash
python scripts/release/gray_release_ctl.py enable \
  --interface wind_pressure \
  --approval-id <approval_id> \
  [--ci-green] [--rollback-ready] [--review-log <path>] [--thresholds <path>]
# 返回 ReleaseResult JSON；success=False 时带 reasons
```

> 五步强制前置（见 `controller.enable_release`）：加载配置 → 授权存在且匹配 → 授权已生效 → G1-G6 通过 → 启用前快照成功 → 才翻转灰度开关。

---

### 2.4 Monitor（首次灰度监控）

| 项 | 内容 |
|---|---|
| **负责人** | 监控值守（建议与发布执行人职责分离；SoD 在监控职责内） |
| **输入** | 三类 append-only 监控源实时流：`release_audit.jsonl`（每次发布动作）、`approved_monitor.jsonl`（每次 `engineering_approved` 出现时落盘，**本阶段不触发**）、`review_log.jsonl`（四类 intake 审核事件链完整性） |
| **输出** | 异常告警；指标看板（仅引用标识符，无真实数值） |
| **失败处理** | 见"异常指标 → 触发 Rollback"；监控值守**无权**自行翻转开关，仅触发 Runbook 的 Rollback 步骤（由回滚负责人执行） |

**监控数据来源（真实模块）**：
- `agents/engineering/release/audit.py` → `release_audit.jsonl`（字段：`approval_id/interface/operator/action/timestamp/result`）
- `agents/engineering/approved_monitor.py` → `approved_monitor.jsonl`（字段：`interface/threshold_version/sign_off_id/review_log_ref/error/timestamp`）
- `agents/engineering/review_log.py` → `review_log.jsonl`（字段：`event_id/threshold_id/action/signer_role/signer/timestamp/source_ref/prev_event_id`）

> 异常指标与对应 Rollback 触发条件见评审报告「任务3 Monitor 方案」。

---

### 2.5 Rollback（回滚 / 熔断 / 恢复）

| 项 | 内容 |
|---|---|
| **负责人** | 回滚负责人（`rollback_owner`，须 ≠ `authorized_by`，满足 SoD） |
| **输入** | 触发源：监控告警异常；参数：`--interface wind_pressure`（接口级）或 `--global`（全局熔断） |
| **输出** | `gray_release.json` 中目标接口 `enabled=False`（或 `default_enabled=False` 全局）；相关接口恢复 `pending_verification`；`release_audit.jsonl` 追加 `rollback` 记录；快照自动前置保存 |
| **失败处理** | 无可用快照 → `restore` 拒绝（`REJECTED_NO_SNAPSHOT`）；回滚本身失败 → 保持当前态并人工介入；`restore` 仅从最近快照恢复灰度开关，**不触碰** `review_log` / `approvals` |

**命令**：
```bash
# 接口级关闭
python scripts/release/gray_release_ctl.py rollback --interface wind_pressure
# 全局熔断（所有接口拒绝工程审核）
python scripts/release/gray_release_ctl.py rollback --global
# 从最近快照恢复（回滚的回滚）
python scripts/release/gray_release_ctl.py restore
# 仅关闭灰度开关（不熔断其余）
python scripts/release/gray_release_ctl.py disable --interface wind_pressure
```

> 四路径（见 `controller` / `rollback.py`）：`snapshot`（enable 前置自动生成 `gray_release.*.snapshot.json`）/ `disable`（接口关闭）/ `rollback`（接口关闭或全局熔断）/ `restore`（从快照恢复）。回滚只翻转灰度开关，绝不触碰 `engineering_enabled`、不修改 `verified.json`、不输出 `engineering_approved`。

---

## 3. 角色与责任矩阵

| 角色 | 对应步骤 | 职责 | SoD 约束 |
|---|---|---|---|
| Release Governance 负责人（AI） | 2.1 Pre-check / 全程审核 | 门禁检查、报告、流程守约 | 不得兼任授权/执行 |
| 专家 | 2.2（G1/G2） | 阈值真实化、双签 `expert_verified_by` | ≠ 主理人 |
| 主理人（轩哥） | 2.2（G6） | 书面创建 `EngineeringReleaseApproval`（`authorized_by`） | `authorized_by ≠ rollback_owner` |
| 发布执行人（`release-operator`） | 2.3 Enable | 执行 `gray_release_ctl.py enable` | ≠ 回滚负责人 |
| 监控值守 | 2.4 Monitor | 实时流监控、触发回滚告警 | 与执行人分离 |
| 回滚负责人（`rollback_owner`） | 2.5 Rollback | 执行 `rollback` / `restore` | `≠ authorized_by`（SoD） |

---

## 4. 进入条件（Gate to Execution）

仅当满足以下全部条件，方允许从本 Runbook 进入真实执行（2.3 Enable）：
1. G1 阈值治理：E-TH-01/02/03 真实化且 `governance_status` ok；
2. G2 双签：`mgmt_signed` AND `expert_signed` 齐备；
3. G3 CI：人工确认 `ci_green`（最近绿跑基线 `481 passed@90%`）；
4. G4 审核链：`review_log` 含 `intake_submit/intake_review_approve/intake_expert_recheck/intake_verified` 四类事件且链完整；
5. G5 回滚：`rollback_ready` 人工确认；
6. G6 授权：`release_approvals.jsonl` 存在生效记录且满足 SoD；
7. `verified_integrity = true`（无绕过直接改库）。

否则保持 **NO-GO**，本 Runbook 仅作手册，不触发任何执行。

---

*防编造声明：本 Runbook 所有阈值标识（E-TH-01/02/03）、版本号（3.2.5-H4-A）、配置/证据哈希均为治理引用，非真实工程参数；真实数值、签名、授权均 `pending_verification`，由人工经正式流程提供。*
