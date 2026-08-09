# BOIP Phase 3.2 Sprint 3.2.5-G1 — 首次 Engineering Gray Release Pre-Flight Check 报告

- **身份**：BOIP AI Release Governance 负责人
- **阶段目标**：wind_pressure 首次灰度发布前最终核验（Pre-Flight）
- **核验时间**：2026-07-31
- **结论**：❌ **不具备进入 G2（真实灰度放量）条件**；当前门禁默认拒绝，所有红线守约。

---

## §1 红线合规总览（最高红线 — 守约）

| 红线 | 状态 | 证据 |
|---|---|---|
| 不开启 `engineering_enabled=true` | ✅ 守约 | `load_engineering_enabled()` 实测返回 `false`；dry-run 前后不变 |
| 不输出 `engineering_approved` | ✅ 守约 | 全程未生成/输出该标识 |
| 不扩大灰度范围 | ✅ 守约 | 仅核验 `wind_pressure`，未触达 hardware / installation_risk（E-TH-04 至 E-TH-06） |
| 不修改未授权阈值 | ✅ 守约 | `verified.json` 仅读取，未写入；所有 `value` 仍为 `null` |

---

## §2 任务1 — 生产状态检查（verified.json）

**文件**：`agents/engineering/thresholds/verified.json`（schema_version 1，占位态）

**E-TH-01 / E-TH-02 / E-TH-03 现状**：

| 阈值 | param | value | verified | verified_by | expert_verified_by | source_ref | applies_to |
|---|---|---|---|---|---|---|---|
| E-TH-01 | 基本风压（基本风压标准值） | `null` | `false` | `null` | `null` | 待行业专家签字填入规范/标准号 pending_verification | wind_pressure |
| E-TH-02 | 体型系数（风载体型系数） | `null` | `false` | `null` | `null` | 待行业专家签字填入规范/标准号 pending_verification | wind_pressure |
| E-TH-03 | 粗糙度类别（地面粗糙度） | `null` | `false` | `null` | `null` | 待行业专家签字填入规范/标准号 pending_verification | wind_pressure |

**确认结果**：

- **threshold_status**：三项均为 `draft`（`verified=false`），未转正。
- **source_ref**：三项均为占位文本，无真实规范/标准号、无哈希。
- **双签**：`verified_by` 与 `expert_verified_by` 均为 `null`，双签缺失。
- **review_log**：无 E-TH-01 至 E-TH-03 对应的真实签字事件（审核链为空）。

> 结论：E-TH-01 至 E-TH-03 仍为占位态、`pending_verification`，不具备工程判定前提。

---

## §3 任务2 — Release Approval 检查（EngineeringReleaseApproval）

**文件**：`agents/engineering/release/release_approvals.jsonl`

| 项 | 值 |
|---|---|
| 文件是否存在 | **否**（不存在） |
| 授权记录数 | 0 |
| approval_id / interface / scope / authorized_by / rollback_owner / approval_document_ref | 均无（未签署） |

**确认结果**：

- G6 `authorization_present` 的**唯一可信源** `EngineeringReleaseApproval` 尚不存在。
- 主理人单独书面授权（G6）**缺失**，且 SoD（`authorized_by` / `rollback_owner` 须异于 3.2.4 双签主体）未建立。

> 结论：发布授权缺位，G6 门禁阻断。

---

## §4 任务3 — G1-G6 最终检查（release_precheck）

**执行**：`release_precheck(interface="wind_pressure")`（默认外部条件全 `false`，委托 `can_enable_engineering`）

**输出**：

```
allowed: false
blocking_reasons:
  - G1_threshold_governance_incomplete: threshold_status 非 verified（draft/review）不纳入工程判定
  - G2_dual_sign_incomplete
  - G3_ci_not_green
  - G5_rollback_not_ready
  - G6_authorization_missing
```

**逐门说明**：

| 门 | 结果 | 说明 |
|---|---|---|
| G1 阈值治理完备 | ❌ 阻断 | E-TH-01 至 E-TH-03 非 verified，结构化引用缺失 |
| G2 双签齐全 | ❌ 阻断 | verified_by / expert_verified_by 均为 null |
| G3 CI 全绿 | ❌ 阻断 | 本次预检未注入 `ci_green`（门禁默认拒绝；真实放量时由发布负责人确认 CI 绿后注入） |
| G4 审核链完整 | ✅ 通过（真空） | review_log 为空，链式完整性校验真空通过——无真实签字事件，故 G4 不具实质阻断力，但也不构成放行依据 |
| G5 回滚就绪 | ❌ 阻断 | 未注入 `rollback_ready` |
| G6 主理人书面授权 | ❌ 阻断 | `EngineeringReleaseApproval` 不存在 |

> 结论：`allowed=false`，5 道门禁阻断（G4 真空通过但不构成放行）。

---

## §5 任务4 — Rollback 最终演练（dry-run）

**方法**：在一次性 harness 中以 **temp 路径** 载入真实 `agents.engineering.release` 控制器，模拟「已放量」态（wind_pressure `enabled=true`），依次执行 snapshot → disable → rollback（全局熔断）-> restore；所有写操作指向 `/tmp`，**不触碰生产**。

**实测证据**：

| 步骤 | 结果 |
|---|---|
| snapshot 写入 | ✅ `/tmp/boip_preflight_g1_run/snapshots/gray_release.*.snapshot.json` |
| disable | ✅ success（恢复 pending_verification） |
| rollback（全局熔断） | ✅ success |
| restore（从快照恢复） | ✅ success |
| **review_log 不变** | ✅ `review_log_unchanged = true`（SHA256 前后一致） |
| **gray_release.json 未受污染** | ✅ `gray_release_unchanged = true` |
| **release_approvals.jsonl 未创建** | ✅ `approval_file_unchanged = true` |
| **审计仅写入 temp** | ✅ `audit_written_to_temp = true`（生产无 release_audit.jsonl） |
| **engineering_enabled 仍 false** | ✅ `engineering_enabled_still_false = true` |

> 结论：回滚子系统（快照/关闭/熔断/恢复）链路可用，且全程零生产污染、review_log 零改动。

---

## §6 红线复核（程序化断言）

```
engineering_enabled               = false
verified_json_modified            = false
engineering_approved_output       = false
scope_expanded                    = false
unauthorized_threshold_modified   = false
```

全部守约。

---

## §7 发布风险

### 7.1 技术风险（RT）

- **RT-G1 门过闸未开**：即便 G1-G6 全过，`engineering_enabled` 仍须主理人于 config 显式置位 + G6 授权，存在「门过而全局闸未开」的误操作风险。缓解：enable 仅翻接口级灰度开关，全局闸独立不可旁路。
- **RT-G2 生产回滚未实跑**：dry-run 仅覆盖 temp 路径，未在生产快照目录真跑。缓解：首次放量前须于生产快照目录执行一次干跑（保持 disabled）以确认生产回滚链路。
- **RT-G3 回滚不恢复阈值**：snapshot/restore 仅恢复灰度开关，不恢复 `verified.json`（设计使然）。缓解：文档明确回滚边界，避免误期恢复阈值。
- **RT-G4 空链真空放行**：review_log 为空时 G4 真空通过，可能掩盖「无审核链即放行」。缓解：真实放量前 review_log 须含 E-TH-01 至 E-TH-03 双签事件，G4 方具实质意义。

### 7.2 工程风险（RE）

- **RE-G1 占位值误用**：E-TH-01 至 E-TH-03 仍为 `null`/draft，任何工程判定若误用占位值将导致风压分析失准。缓解：`verified=false` 时 `is_interface_gray_allowed` 恒 False。
- **RE-G2 规范不可溯**：缺乏真实规范 `source_ref`，风压参数无法溯源。缓解：G1 要求结构化引用 + G2 双签 + review_log。
- **RE-G3 SoD 未建立**：`authorized_by` / `rollback_owner` 未定，责任链不完整。
- **RE-G4 熔断触发未演练**：灰度期异常如何熔断/监控阈值未演练。

### 7.3 责任风险（RL）

- **RL-G1 越权放量**：未获主理人单独书面 G6 授权前放量属越权（红线）。
- **RL-G2 责任不可溯**：审核链若缺 E-TH-01 至 E-TH-03 真实事件，责任不可溯。
- **RL-G3 范围越界**：放量若扩大至 hardware / installation_risk（E-TH-04 至 E-TH-06）属越界。
- **RL-G4 防编造**：真实数值须人工提供，AI 不生成（防编造红线）。

---

## §8 是否具备进入 G2 条件

**结论：不具备。** 当前 `allowed=false`，5 道门禁（G1/G2/G3/G5/G6）阻断，G4 仅真空通过。

**进入 G2（真实灰度放量）的前置闭环（须全部满足）**：

1. **G6 授权**：主理人单独书面签署 `EngineeringReleaseApproval`（七字段齐全，`effective_time` 已生效，SoD 独立于 3.2.4 双签主体）。
2. **G1 + G2 真实化**：由人工以真实数据录入 E-TH-01 至 E-TH-03（专家签字 + 主理人核准，双签齐全，`verified=true`，结构化 `source_ref` 含规范号与哈希），并写入 review_log 形成真实审核链（使 G4 具实质）。
3. **G3 CI 绿**：发布负责人确认 CI 全绿（460 passed @ 89.52%）后注入 `ci_green=true`。
4. **G5 回滚就绪**：确认回滚演练（§5）与熔断/恢复路径就绪，注入 `rollback_ready=true`。
5. **显式执行**：`scripts/release/gray_release_ctl.py enable wind_pressure`（须 snapshot + approval 存在 + G1-G6 全过），且仅翻接口级灰度开关。
6. **全局闸置位**：`orchestrator.engineering_enabled=true` 由主理人于 config 显式置位（独立于 enable，且须经 G6）。

> 当前仅 §5 回滚子系统就绪；§1-§4 显示生产状态与授权均未达标，故禁止进入 G2。

---

## §9 下一步与结论

- 本阶段为 Pre-Flight 核验，**不产生任何放行动作**，未开启 `engineering_enabled`，未输出 `engineering_approved`。
- 等待主理人审核与 G6 单独书面授权；授权后由人工真实化 E-TH-01 至 E-TH-03 → 确认 CI 绿 → 置 `engineering_enabled=true` 并经 G6 → `gray_release_ctl.py enable wind_pressure`。
- **完成后停止。**

---

*附：核验证据由一次性 harness（`/tmp/boip_preflight_g1.py`，未纳入仓库）基于真实 `agents.engineering.release` 模块产出；所有写操作指向 temp 路径，生产零污染。*
