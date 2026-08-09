# BOIP Phase 3.2 Sprint 3.2.5-G3 — Final Release Governance Review 报告

- **阶段**：首次工程灰度（风压 `wind_pressure` 接口）最终发布治理审核（pending_verification）
- **负责人**：BOIP AI Release Governance 负责人
- **基线依赖**：3.2.5-F（执行基础设施）/ G1（Pre-flight）/ G2（Production Readiness Remediation 已完成）
- **最高红线**：未开启 `engineering_enabled` / 未输出 `engineering_approved` / 未修改真实 `verified.json` / 未自动生成工程参数 / 未自动生成专家签名（pending_verification）
- **数据来源**：本报告 G1–G6 状态由 `release_precheck(interface="wind_pressure", return_report=True)` 在**真实生产态**（默认缺省条件：CI/回滚/授权均未注入）实测，非假设（见附录 A 原始 JSON）。

> 风压 `wind_pressure` 接口的真实工程参数（E-TH-01 至 E-TH-03）仍须人工提供（pending_verification）。本阶段**仅产出治理包与审核结论，不开启任何开关、不输出 approved、不修改生产数据**。

---

## 一、G1–G6 最终状态（真实态快照，release_precheck 实测）

接口 `wind_pressure` 于真实生产态（review_log 缺完整 intake 链 / 无授权 / verified.json 全 draft）下实测：

| 门禁 | 名称 | 状态 | 实测依据 |
|---|---|---|---|
| G1 | 阈值治理 | ❌ 失败 | `threshold_status` 非 verified（draft/review），不纳入工程判定 |
| G2 | 双签 | ❌ 失败 | E-TH-01 至 E-TH-03 双签（`verified_by` / `expert_verified_by`）均为 null |
| G3 | CI | ❌ 失败 | `ci_green` 注入 False（发布前须重新实跑确认全绿） |
| G4 | 审核链 | ❌ 失败 | review_log 缺 `intake_submit` / `intake_review_approve` / `intake_expert_recheck` / `intake_verified`（缺失 4 类必需事件，event_count=1 非必需链） |
| G5 | 回滚就绪 | ❌ 失败 | `rollback_ready` 注入 False（未确认就绪） |
| G6 | 授权 | ❌ 失败 | `EngineeringReleaseApproval` 未签署（approval_present=false，count=0） |
| 守卫 | verified_integrity | ✅ 通过 | 全 draft / `value=null`，无绕过（bypassed_ids=[]，checked_count=0）（pending_verification） |

**结论**：`allowed=false`，6 道门禁全阻断；`verified_integrity` 守卫通过（无绕过）。E-TH-01 至 E-TH-03 的 `realized` 均为 false（缺 value / unit / source_ref / version / dual_sign）（pending_verification）。

---

## 二、Blocking Reasons（阻断原因，原始字段）

1. `G1_threshold_governance_incomplete`：threshold_status 非 verified（draft/review）不纳入工程判定
2. `G2_dual_sign_incomplete`：E-TH 双签缺失
3. `G3_ci_not_green`：CI 未确认绿
4. `G4_audit_chain_incomplete`：审核链缺四类必需 intake 事件
5. `G5_rollback_not_ready`：回滚未就绪
6. `G6_authorization_missing`：`EngineeringReleaseApproval` 缺失

---

## 三、Readiness Score（就绪度评分）

- **评分口径**：发布就绪度 = 通过的发布门禁数 / 总发布门禁数（G1–G6 共 6 道）。`verified_integrity` 为守卫项，不计入就绪度分母。
- **当前得分**：0 / 6 = **0%**
- **Go / No-Go 判定**：**NO-GO**（G1–G6 未全绿）
- 说明：E-TH 真实化（G1/G2/G4 前置）、CI 绿（G3）、回滚就绪（G5）、主理人 G6 书面授权（G6）四项外部条件全部未满足，故就绪度为 0。

---

## 四、风险列表（Risk Register）

| 编号 | 风险 | 影响门禁 | 当前敞口 | 缓解 / 拦截 |
|---|---|---|---|---|
| R1 | E-TH 真实工程参数缺失（value/unit/source_ref/version/dual_sign 全缺） | G1/G2/G4 | 高（硬阻塞） | 须人工真实录入 + 双签；AI 不代填 |
| R2 | 审核链缺失（review_log 缺四类 intake 事件） | G4 | 高（硬阻塞） | `required_audit_events` + `can_enable_engineering` 判失败；空/断裂链均拒 |
| R3 | 双签缺失（verified_by / expert_verified_by 均 null） | G2 | 高（硬阻塞） | 双签校验；AI 不代签 |
| R4 | CI 未确认绿 | G3 | 中 | 发布前须重跑 `local_ci.sh` 8/8 确认 |
| R5 | 回滚未确认就绪 | G5 | 中 | 须确认 snapshot 机制 + rollback_owner 指定 |
| R6 | G6 授权缺失（approval count=0） | G6 | 高（硬阻塞） | `EngineeringReleaseApproval` 校验；SoD（authorized_by ≠ rollback_owner） |
| R7 | verified.json 直接篡改 / 绕过 ThresholdIntakeWorkflow | 守卫 | 低 | `manual_modified_thresholds` 技术拦截；仍须线下责任确认 |
| R8 | 红线违规（AI 自动 enable / 自动参数 / 自动签名） | 全局 | 极低 | 全局 `engineering_enabled=false` 双保险 + `release_precheck` 默认拒绝 + 红线约束 |

---

## 五、责任矩阵（首次灰度责任链，任务3）

| 角色 | 核心职责 | 责任边界（可） | 不可越权（禁） |
|---|---|---|---|
| 阈值提供方 | 提供真实 E-TH-01~03 数值 + 结构化 `source_ref` + 版本 | 提交数据至 ThresholdIntakeWorkflow | 不得代签、不得改 verified 判定、不得自行 enable |
| 主理人 | G6 单独书面授权 + 经 G6 后显式置 `engineering_enabled=true` | 唯一授权主体（SoD 独立于 3.2.4 双签主体） | 不得代专家签字、不得伪造 CI/回滚状态 |
| 专家 | E-TH 双签（`expert_verified_by`）+ `intake_expert_recheck` 技术背书 | 真实性背书 | 不得代主理人授权、不得改业务参数 |
| 发布执行人 | 执行 `scripts/release/gray_release_ctl.py enable wind_pressure`（前置快照+授权+G1-G6 重判） | 按授权执行放量 | 门禁不通过则拒绝执行；不决策是否放量 |
| 回滚负责人 | `rollback_owner`；Path B 触发与执行；恢复快照 | 回滚决策与执行 | 须独立于 authorized_by（SoD）；不兼授权 |

**SoD 要点**：G6 授权主体（主理人）与回滚负责人（rollback_owner）必须异人；3.2.4 双签主体（阈值提供方 + 专家）与 G6 授权主体亦相互独立。

---

## 六、上线与回滚双路径（任务4）

### Path A — 正常灰度开启

- **触发条件**：G1–G6 全绿（release_precheck `allowed=true`）+ G6 授权在场 + `engineering_enabled=true`（经 G6 显式置位）+ 显式 enable 命令。
- **负责人**：发布执行人（受主理人授权）。
- **操作步骤**：
  1. 主理人经 G6 书面授权后，于 config 显式置 `engineering_enabled=true`（独立于接口级开关，且须经 G6）。
  2. 发布执行人执行 `scripts/release/gray_release_ctl.py enable wind_pressure`。
  3. 脚本自动：① 快照 `verified.json` → ② 校验 `EngineeringReleaseApproval` 在场且生效 → ③ 重跑 G1–G6（release_precheck）→ ④ 全通过后翻接口级灰度开关。
  4. 监控灰度指标，按既定比例放量；写入 `release_audit.jsonl`。
  5. 任一条件缺失 → 脚本非 0 退出，开关不翻。

### Path B — 立即回滚

- **触发条件**（任一）：灰度期出现质量/安全/合规异常（风压计算偏差、规范冲突、CI 转红、绕过检测命中、用户反馈阈值失效、监控越限）。
- **负责人**：回滚负责人（rollback_owner）。
- **操作步骤**：
  1. 回滚负责人确认触发条件 → 执行 `scripts/release/gray_release_ctl.py rollback wind_pressure`。
  2. 恢复至 enable 前快照（snapshot）。
  3. 若快照损坏 → 执行 `restore` 子命令。
  4. 写入 `release_audit.jsonl`，通知主理人；保留现场供复盘。
  5. 复盘后由主理人决定是否重新走 Path A。

---

## 七、最终禁止条件检查（任务5）

**不变量（强制）**：任何情况下，G1–G6 未全绿 → **不得进入 enable**。

执行保障（代码层已落地，非本阶段新增）：
- `can_enable_engineering` 委托 G1–G6 判定；空 review_log / 缺必需 intake 事件 → G4 失败。
- `release_precheck` 默认返回 `(False, reasons)`，所有外部条件缺省取"不满足"，确保闸门默认拒绝。
- 全局 `engineering_enabled=false` 为双保险：`load_engineering_enabled()` 返回 False 时 `is_interface_gray_allowed` 恒 False；controller 仅翻接口级灰度开关，绝不翻全局开关。
- `manual_modified_thresholds` 拦截绕过 ThresholdIntakeWorkflow 直接改 `verified.json`。
- 本阶段（G3）**零代码改动**，上述保障沿用 3.2.5-G2 基线；纯文档治理包。

**红线守约确认**：
- ❌ 未开启 `engineering_enabled`（实测 `load_engineering_enabled() is False`，核验零翻转）。
- ❌ 未输出 `engineering_approved`。
- ❌ 未修改真实 `verified.json`（仍全 draft / `value=null`）。
- ❌ 未自动生成真实工程参数（E-TH 仍 draft / pending_verification）。
- ❌ 未自动生成专家签名（双签均 null）。

---

## 八、是否具备进入真实灰度（G2/G3 放量）条件

**结论：不具备。** 当前 G1–G6 全阻断（就绪度 0%），仅 `verified_integrity` 守卫通过。

**放行前置清单（须全部满足）**：
1. 主理人**单独书面**签署 `EngineeringReleaseApproval`（G6，SoD 独立于 3.2.4 双签主体）；
2. 人工以真实数据录入 **E-TH-01 至 E-TH-03**（双签齐全、`verified=true`、结构化 `source_ref` + 真实 intake 审核链，满足 G1 / G2 / G4）；
3. 发布负责人重跑 `bash scripts/ci/local_ci.sh` 确认 **CI 全绿**（G3）；
4. 确认 **回滚就绪**（G5，snapshot + rollback_owner 指定）；
5. 显式 `scripts/release/gray_release_ctl.py enable wind_pressure`（脚本校验 快照 + 授权 + G1–G6）；
6. 主理人于 config 显式置 `engineering_enabled=true`（独立于 enable，且须经 G6）。

---

## 九、交付物与更新

- `.ai/reviews/phase3.2.5G3_final_release_governance_report.md`：本报告（G1–G6 状态 / blocking reasons / readiness score / 风险列表 / 责任矩阵 / 双路径 / 禁止条件）。
- `.ai/tasks/phase3.2.5G3_release_approval_checklist.md`：发布授权签字清单（阈值/双签/CI/审核链/回滚/授权 六确认）。
- `.ai/project_status.json`：`phase_status` → `SPRINT_3_2_5G3_DONE`，新增 `3.2.5-G3` 条目。
- `.ai/roadmap_v2.md`：里程碑追加 3.2.5-G3 DONE。

> 本阶段为**纯文档治理包**，零代码改动，沿用 3.2.5-G2 基线 481 passed @ 90%（任务书约定：纯文档沿用基线，不强制重跑；如需复核可运行 `bash scripts/ci/local_ci.sh` 验证 8/8 PASS）。

---

## 附录 A：release_precheck 原始输出（节选）

```
gate_status:
  G1_threshold_governance: false
  G2_dual_sign: false
  G3_ci: false
  G4_audit_chain: false
  G5_rollback: false
  G6_authorization: false
  verified_integrity: true
blocking_reasons:
  - G1_threshold_governance_incomplete
  - G2_dual_sign_incomplete
  - G3_ci_not_green
  - G4_audit_chain_incomplete
  - G5_rollback_not_ready
  - G6_authorization_missing
e_th_realization.all_realized: false   (E-TH-01/02/03 均 missing value/unit/source_ref/version/dual_sign)
review_log_chain.ok: false             (missing intake_submit/intake_review_approve/intake_expert_recheck/intake_verified)
approval_present: false
verified_integrity.ok: true             (bypassed_ids=[], checked_count=0)
```

等待主理人审核与 G6 单独书面授权；授权后由人工真实化 E-TH-01 至 E-TH-03 → 重跑确认 CI 绿 → 显式置 `engineering_enabled=true`（经 G6）→ `gray_release_ctl.py enable wind_pressure`。本阶段已停止（pending_verification）。
