# BOIP Phase 3.2 Sprint 3.2.5-G3 — Release Approval Checklist（发布授权签字清单）

- **接口**：`wind_pressure`（首次工程灰度）
- **用途**：进入真实灰度（enable）前的**人工六确认签字表**。本表为治理动作记录，**不替代**代码层 `release_precheck` 判定。
- **红线**：未开启 `engineering_enabled` / 未输出 `engineering_approved` / 未改真实 `verified.json` / 未自动生成工程参数 / 未自动生成专家签名（pending_verification）。
- **当前状态（2026-08-01 实测）**：六项确认**全部未通过**，就绪度 0%，**NO-GO**。

> 每一确认项须由对应责任角色**线下**确认并签字；任一未打勾 → 不得进入 enable。AI 不代签、不自动勾选。

---

## 1. 阈值确认（Threshold Confirmation）— G1 前置

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| E-TH-01 真实化 | value 真实、unit 真实、source_ref 完整、version 在场 | ❌ 缺失（pending_verification） | 阈值提供方 |
| E-TH-02 真实化 | value + unit 真实、source_ref 完整、version 在场 | ❌ 缺失（pending_verification） | 阈值提供方 |
| E-TH-03 真实化 | value + unit 真实、source_ref 完整、version 在场 | ❌ 缺失（pending_verification） | 阈值提供方 |
| verified 状态 | `verified=true`（非 draft/review） | ❌ 全 draft | 阈值提供方 |

**签字**：________________ 日期：__________

## 2. 双签确认（Dual-Sign Confirmation）— G2

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| E-TH-01 双签 | `verified_by` + `expert_verified_by` 均非 null | ❌ 均 null | 阈值提供方 + 专家 |
| E-TH-02 双签 | 同上 | ❌ 均 null | 阈值提供方 + 专家 |
| E-TH-03 双签 | 同上 | ❌ 均 null | 阈值提供方 + 专家 |

**签字（阈值提供方）**：________________ **签字（专家）**：________________ 日期：__________

## 3. CI 确认（CI Confirmation）— G3

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| 全量 CI 8/8 PASS | `bash scripts/ci/local_ci.sh` 实跑通过（agents+backend+jest+alembic+seed+双扫描） | ❌ 未重跑确认（基线 481@90% 存在但发布前须复跑） | 发布执行人 |
| 防编造扫描 0 命中 | 业务数字扫描 + 硬编码扫描均通过 | ❌ 未复跑 | 发布执行人 |

**签字**：________________ 日期：__________（复跑记录：`CIEXIT=0`）

## 4. 审核链确认（Review Chain Confirmation）— G4

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| intake_submit | review_log 含提交事件 | ❌ 缺失 | 阈值提供方 |
| intake_review_approve | review_log 含复核批准事件 | ❌ 缺失 | 专家 |
| intake_expert_recheck | review_log 含专家复审事件 | ❌ 缺失 | 专家 |
| intake_verified | review_log 含验证事件 | ❌ 缺失 | 主理人 |

**签字**：________________ 日期：__________（review_log 路径：`agents/engineering/review_log.jsonl`）

## 5. 回滚确认（Rollback Confirmation）— G5

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| 快照机制可用 | enable 前自动快照 `verified.json` | ✅ 脚本支持 | 发布执行人 |
| rollback_owner 指定 | 独立于 authorized_by（SoD） | ❌ 未指定 | 主理人 |
| 回滚演练通过 | `gray_release_ctl.py rollback` dry-run 通过 | ❌ 未确认 | 回滚负责人 |

**签字（回滚负责人）**：________________ 日期：__________

## 6. 授权确认（Authorization Confirmation）— G6

| 项 | 要求 | 当前状态 | 确认人 |
|---|---|---|---|
| EngineeringReleaseApproval 在场 | approval 库存在且 `approval_present=true` | ❌ count=0 | 主理人 |
| 生效 | `effective_time` 已到、文档引用完整 | ❌ 未生效 | 主理人 |
| SoD 合规 | `authorized_by` ≠ `rollback_owner` | ❌ 未签署 | 主理人 |

**签字（主理人）**：________________ 日期：__________

---

## 总判定（Go / No-Go）

- [ ] 以上 1–6 **全部**打勾 → 可进入 Path A（enable）
- [x] 当前：**NO-GO**（1–6 均未满足，就绪度 0%）

> 最终硬约束：G1–G6 未全绿，任何情况下不得进入 enable（见最终发布治理报告 任务5）。

---

## 责任矩阵速查（详见治理报告 任务3）

| 角色 | 对应确认项 |
|---|---|
| 阈值提供方 | 1 阈值 / 2 双签（其一侧）/ 4 审核链（submit） |
| 专家 | 2 双签（其一侧）/ 4 审核链（review_approve + expert_recheck） |
| 主理人 | 4 审核链（verified）/ 5 回滚（指定 owner）/ 6 授权 |
| 发布执行人 | 3 CI / 5 回滚（执行） |
| 回滚负责人 | 5 回滚（执行） |
