# BOIP Phase 3.2 Sprint 3.2.5-H1 — Human Authorization & Production Readiness Confirmation 报告

- **阶段**：首次 `wind_pressure` 灰度发布前**人工授权最终确认**（pending_verification）
- **负责人**：BOIP AI Release Governance 负责人
- **基线依赖**：3.2.5-F（执行基础设施）/ G1（Pre-flight）/ G2（Production Readiness）/ G3（Final Release Governance Review）
- **最高红线（本阶段）**：仍**禁止开启 `engineering_enabled`**；禁止自动生成工程参数 / 自动生成专家签名 / 输出 `engineering_approved` / 自动创建 `ReleaseApproval`；**所有真实信息必须人工提供**（pending_verification）
- **数据来源**：G1–G6 状态由 `release_precheck(interface="wind_pressure", return_report=True)` 在真实生产态实测（见附录 A）。

> 本阶段为**人工作业确认包**：仅产出模板与清单，供主理人 / 专家 / 阈值提供方线下填写与签字。AI 不代填任何真实值、不自动创建授权、不开启开关、不输出 approved。

---

## 一、当前真实态快照（release_precheck 实测）

| 门禁 | 状态 | 实测依据 |
|---|---|---|
| G1 阈值治理 | ❌ 失败 | `threshold_status` 非 verified（draft/review），E-TH-01~03 `value=null` |
| G2 双签 | ❌ 失败 | E-TH-01~03 双签位（`verified_by` / `expert_verified_by`）均 null |
| G3 CI | ❌ 失败 | `ci_green` 注入 False（发布前须重跑确认全绿） |
| G4 审核链 | ❌ 失败 | review_log 缺 `intake_submit` / `intake_review_approve` / `intake_expert_recheck` / `intake_verified` |
| G5 回滚就绪 | ❌ 失败 | `rollback_ready` 注入 False |
| G6 授权 | ❌ 失败 | `EngineeringReleaseApproval` 未签署（count=0） |
| 守卫 verified_integrity | ✅ 通过 | 全 draft / `value=null`，无绕过（bypassed_ids=[]） |

**结论**：`allowed=false`，6 道门禁全阻断；就绪度 **0/6 = 0%**（NO-GO）。`engineering_enabled` 仍 **False**（零翻转）。

---

## 二、任务3 — 最终 G1–G6 核验流程（人工确认顺序）

人工确认须**严格按 G1→G2→G3→G4→G5→G6 顺序**逐项打勾；前序未过不得跳至下序。

```
G1 阈值治理确认
   └─ 人工核对 E-TH-01/02/03 真实化（value/unit/source_ref/version/双签/verified=true）
        ↓（G1 通过）
G2 双签确认
   └─ 人工核对 verified_by + expert_verified_by 均非 null（阈值提供方 + 专家亲签）
        ↓（G2 通过）
G3 CI 确认
   └─ 发布负责人重跑 bash scripts/ci/local_ci.sh 确认 8/8 全绿
        ↓（G3 通过）
G4 审核链确认
   └─ 人工核对 review_log 含四类必需 intake 事件（经 ThresholdIntakeWorkflow 自动写入）
        ↓（G4 通过）
G5 回滚确认
   └─ 确认 snapshot 机制可用 + rollback_owner 指定（≠ authorized_by）+ 回滚演练通过
        ↓（G5 通过）
G6 授权确认
   └─ 主理人书面签署 EngineeringReleaseApproval（SoD：authorized_by ≠ rollback_owner）
        ↓（G6 通过）
最终动作：主理人显式置 engineering_enabled=true（经 G6） + gray_release_ctl.py enable wind_pressure
```

### Final Human Checklist（最终人工清单）

| # | 门禁 | 人工确认项 | 责任角色 | 当前 |
|---|---|---|---|---|
| 1 | G1 | E-TH-01/02/03 真实化、verified=true | 阈值提供方 | ❌ 未确认 |
| 2 | G2 | 双签齐全（verified_by + expert_verified_by） | 阈值提供方 + 专家 | ❌ 未确认 |
| 3 | G3 | CI 全绿（重跑确认） | 发布执行人 | ❌ 未确认 |
| 4 | G4 | 四类 intake 事件完整 | 阈值提供方 + 专家 + 主理人 | ❌ 未确认 |
| 5 | G5 | 回滚就绪 + rollback_owner 指定 | 回滚负责人 | ❌ 未确认 |
| 6 | G6 | EngineeringReleaseApproval 书面签署（SoD） | 主理人 | ❌ 未确认 |

> 以上 1–6 **全部**打勾 → 可进入最终动作（enable）。任一未过 → NO-GO。

---

## 三、任务4 — 首次灰度责任确认（责任边界）

| 角色 | 核心职责 | 责任边界（可） | 不可越权（禁） |
|---|---|---|---|
| 阈值提供方 | 人工提供真实 E-TH-01~03 + `source_ref` + 版本 | 经 ThresholdIntakeWorkflow 提交 | 不得代签、不得改 verified 判定、不得自行 enable |
| 主理人 | G6 单独书面授权 + 经 G6 后显式置 `engineering_enabled=true` | 唯一授权主体（独立于 3.2.4 双签） | 不得代专家签字、不得伪造 CI/回滚状态 |
| 专家 | E-TH 双签（`expert_verified_by`）+ `intake_expert_recheck` | 真实性背书 | 不得代主理人授权、不得改业务参数 |
| 发布执行人 | 执行 `gray_release_ctl.py enable`（前置快照+授权+G1-G6 重判） | 按授权执行放量 | 门禁不通过则拒绝执行；不决策是否放量 |
| 回滚负责人 | `rollback_owner`；Path B 触发与执行；恢复快照 | 回滚决策与执行 | 须独立于 authorized_by（SoD）；不兼授权 |

**SoD 要点**：G6 授权主体（主理人）与回滚负责人（rollback_owner）必须异人；3.2.4 双签主体与 G6 授权主体相互独立。

---

## 四、任务5 — 禁止条件确认（最终硬约束）

**不变量（强制）**：任何情况下，**G1–G6 未全绿 → 不得进入 enable `wind_pressure`**。

代码层已落地的执行保障（非本阶段新增，沿用 G2 基线）：
- `can_enable_engineering` 委托 G1–G6 判定；空 review_log / 缺必需 intake 事件 → G4 失败。
- `release_precheck` 默认返回 `(False, reasons)`，所有外部条件缺省取"不满足"。
- 全局 `engineering_enabled=false` 为双保险：`load_engineering_enabled()` 返回 False 时 `is_interface_gray_allowed` 恒 False。
- `manual_modified_thresholds` 拦截绕过工作流直接改 `verified.json`。

**本阶段红线守约确认**：
- ❌ 未开启 `engineering_enabled`（实测 False，零翻转）。
- ❌ 未输出 `engineering_approved`。
- ❌ 未自动生成真实工程参数（E-TH 仍 value=null / pending_verification）。
- ❌ 未自动生成专家签名（双签位均 null）。
- ❌ 未自动创建 `ReleaseApproval`（库 count=0）。
- ✅ 全部 `pending_verification`。

---

## 五、交付物与更新

- `.ai/tasks/phase3.2.5H1_threshold_confirmation.md`：E-TH-01/02/03 真实阈值确认清单（人工填写模板）。
- `.ai/tasks/phase3.2.5H1_release_authorization_template.md`：G6 EngineeringReleaseApproval 授权模板（人工填写，AI 不自动创建）。
- `.ai/reviews/phase3.2.5H1_human_authorization_readiness.md`：本报告（当前态 / G1-G6 流程 + 最终人工清单 / 责任确认 / 禁止条件）。
- `.ai/project_status.json`：`phase_status` → `SPRINT_3_2_5H1_DONE`，新增 `3.2.5-H1` 条目。
- `.ai/roadmap_v2.md`：里程碑追加 3.2.5-H1 DONE。

> 本阶段为**纯文档人工作业确认包**，零代码改动，沿用 3.2.5-G2 基线 481 passed @ 90%（任务书约定：纯文档沿用基线；如需复核可运行 `bash scripts/ci/local_ci.sh` 验证 8/8 PASS）。

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
blocking_reasons: G1,G2,G3,G4,G5,G6 各一项
e_th_realization.all_realized: false   (E-TH-01/02/03 均 missing value/unit/source_ref/version/dual_sign)
review_log_chain.ok: false             (missing intake_submit/intake_review_approve/intake_expert_recheck/intake_verified)
approval_present: false
verified_integrity.ok: true             (bypassed_ids=[], checked_count=0)
```

等待主理人 / 专家 / 阈值提供方**人工**完成填写与签字；授权后由人工真实化 E-TH-01 至 E-TH-03 → 重跑确认 CI 绿 → 显式置 `engineering_enabled=true`（经 G6）→ `gray_release_ctl.py enable wind_pressure`。本阶段已停止（pending_verification）。
