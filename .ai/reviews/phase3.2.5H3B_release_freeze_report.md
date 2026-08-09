# 3.2.5-H3-B Release Freeze Report（pending_verification）

**阶段**：3.2.5-H3-B（首次 wind_pressure 灰度发布证据补齐与冻结）（pending_verification）
**角色**：BOIP AI Release Governance 负责人
**日期**：2026-08-01

---

## 0. 红线守约声明

| 红线 | 状态 | 证据 |
|---|---|---|
| 1. 未开启 `engineering_enabled=true` | ✅ 守约 | `agents/config.yaml` 第 102 行 `engineering_enabled: false`；`load_engineering_enabled()` 实测 `False` |
| 2. 未输出 `engineering_approved` | ✅ 守约 | 全程无任何 approved 输出 |
| 3. 未生成真实工程参数 | ✅ 守约 | `verified.json` 中 E-TH-01/02/03 `value` 全 `null` |
| 4. 未生成专家签名 | ✅ 守约 | `verified_by` / `expert_verified_by` 全 `null` |
| 5. 未自动创建 `ReleaseApproval` | ✅ 守约 | `release_approvals.jsonl` 不存在（count=0） |

> 全部真实证据（阈值数值、双签、授权）均须人工经正式流程提供；本阶段仅**引用证据哈希**，不承载任何真实工程数值（pending_verification）。

---

## 1. ReleaseEvidenceBundle 设计（任务1）

**新增文件**：`agents/engineering/release/evidence_bundle.py`

**数据类字段**（仅引用哈希，不承载真实工程参数）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `bundle_id` | str | 由 `interface + commit_hash` 决定的稳定标识（冻结可复现） |
| `interface` | str | `wind_pressure` |
| `threshold_evidence_hash` | Optional[str] | `verified.json` sha256（缺失为 None） |
| `review_log_hash` | Optional[str] | `review_log.jsonl` sha256（缺失为 None） |
| `authorization_hash` | Optional[str] | `release_approvals.jsonl` sha256（缺失为 None） |
| `ci_evidence_hash` | Optional[str] | CI 事实字典的确定性哈希（引用，不承载参数） |
| `rollback_evidence_hash` | Optional[str] | `gray_release_ctl.py` sha256（回滚路径证据） |
| `commit_hash` | str | 冻结时 git HEAD |
| `created_at` | str | 采集时刻（UTC ISO8601） |
| `threshold_evidence_present` / `review_evidence_present` / `authorization_present` | bool | 证据存在性标记 |
| `notes` | list[str] | 缺失证据说明 |

**设计原则**：`collect_release_evidence_bundle()` **只读**采集既有证据哈希；**不修改/不创建**任何生产证据文件；**不设置** `ci_green` / `rollback_ready`；**不开启** `engineering_enabled`；**不输出** `engineering_approved`；**不创建** `ReleaseApproval`。证据缺失时如实记录（`hash=None` / `present=False` / `notes`），绝不伪造。

**测试**：`tests/agents/test_evidence_bundle.py`（9 passed，覆盖确定性 / 缺失如实记录 / 只读性 / 完整性判定 / 哈希引用）。

---

## 2. Threshold Evidence Freeze（任务2）

| 项 | 真实值 |
|---|---|
| `verified.json` sha256 | `c4b44713a37529551fe9c8069b1ce069e1b9fc77cad357a70349349ece223845` |
| `schema_version` | `1` |
| threshold version | **待人工**（E-TH 仍 `draft` / 未 `verified`） |
| E-TH-01 `value` | `null`（待人工填入 pending_verification） |
| E-TH-02 `value` | `null`（待人工填入 pending_verification） |
| E-TH-03 `value` | `null`（待人工填入 pending_verification） |
| E-TH-01/02/03 `verified_by` | `null`（待双签 pending_verification） |
| E-TH-01/02/03 `expert_verified_by` | `null`（待专家双签 pending_verification） |

**结论**：阈值真实数值未提供 → G1（阈值治理）/ G2（双签）未过，如实记录为缺失。

---

## 3. Review Evidence Freeze（任务3）

| 项 | 真实值 |
|---|---|
| `review_log.jsonl` sha256 | `a4251636bd7726c06de36bb5a736ff909a5881352357d10f2ccf5f6375a6bb44` |
| `intake_submit` | ❌ 缺失 |
| `intake_review_approve` | ❌ 缺失 |
| `intake_expert_recheck` | ❌ 缺失 |
| `intake_verified` | ❌ 缺失 |

当前 `review_log` 仅含系统占位事件 `schema_established`，四类 intake 审核事件全缺 → G4（审核链）未过，如实记录为不完整。

---

## 4. Authorization Evidence Freeze（任务4）

| 项 | 真实值 |
|---|---|
| `EngineeringReleaseApproval` 文件 | **不存在** → `authorization_hash = None` |
| `approval_id` / `interface` / `scope` / `authorized_by` / `effective_time` / `rollback_owner` / `approval_document_ref` | 全部缺失（待人工创建 pending_verification） |
| SoD 规则 | `authorized_by ≠ rollback_owner` 且独立于 3.2.4 双签主体；因授权不存在，SoD **无法验证**（待人工创建后校验） |

**结论**：G6（授权）缺位，如实记录。

---

## 5. CI Evidence Record（任务5）

| 项 | 值 |
|---|---|
| commit hash | `543c3c7a651b158b6c8f76ad99666aef058a1502` |
| captured_at | `2026-08-01T11:33:49Z`（冻结采集时刻） |
| test result | `481 passed`（基线，来源 H3-A green `local_ci` run 2026-08-01） |
| coverage | `90%`（基线，同来源） |
| `ci_green` | **未自动设置**（待人工确认 CI 标志） |

> 说明：本阶段未重跑全集 `local_ci.sh`——sandbox 的 bulk-delete 防护在 coverage 合并阶段拦截临时文件删除（环境问题，非测试失败）；CI Evidence 引用最近一次绿跑基线（H3-A, 2026-08-01, 481 passed@90%）。`ci_green` 标志不自动置位，须人工确认。

---

## 6. Rollback Evidence Freeze（任务6）

| 路径 | 引用证据 |
|---|---|
| `snapshot` | `gray_release_ctl.py enable` 前置自动生成快照（回滚安全网） |
| `disable` | `gray_release_ctl.py disable` 子命令（顶层接线） |
| `rollback` | `gray_release_ctl.py rollback`（含 `global` 熔断） |
| `restore` | `gray_release_ctl.py restore` 子命令 |
| 脚本 sha256 | `bbeb58d05456af4be667a9d3c7e10f46efb1a3d923dcdf402e9e4dfe49014af0` |

`rollback_ready`：**未自动设置**（待人工确认回滚就绪标志）。四路径均在 `gray_release_ctl.py` 内接线，链路闭合。

---

## 7. Release Freeze Record（任务7）

**新增文件**：`release_freeze_record.json`（612B，仓库根）

```json
{
  "bundle_id": "BOIP-EB-0561f7197d25d24b",
  "commit_hash": "543c3c7a651b158b6c8f76ad99666aef058a1502",
  "config_hash": "9aa005aa598dedf75969d12a17f155aa6e27d86dec33cb1c173a7d5b6a0ff2cc",
  "threshold_hash": "c4b44713a37529551fe9c8069b1ce069e1b9fc77cad357a70349349ece223845",
  "created_at": "2026-08-01T11:33:49.972866+00:00",
  "frozen": true,
  "evidence_complete": false,
  "note": "Release Freeze Record：仅引用证据哈希，不承载真实工程参数；ci_green / rollback_ready 未自动设置；等待人工 G6 书面授权且 G1-G6 全绿，方可 gray_release_ctl.py enable wind_pressure。"
}
```

字段说明：`bundle_id` 来自 `ReleaseEvidenceBundle`；`commit_hash` 为冻结时 HEAD；`config_hash` 为 `agents/config.yaml` sha256；`threshold_hash` 为 `verified.json` sha256；`created_at` 为采集时刻。

---

## 8. 当前真实态与 GO / NO-GO

| Gate | 状态 | 阻塞原因 |
|---|---|---|
| G1 阈值治理 | ❌ false | 阈值真实数值未提供（value=null） |
| G2 双签 | ❌ false | 双签位 null |
| G3 CI | ❌ false | `ci_green` 未置位（CI 基线绿但标志待人工确认） |
| G4 审核链 | ❌ false | 四类 intake 事件缺失 |
| G5 回滚 | ❌ false | `rollback_ready` 未置位 |
| G6 授权 | ❌ false | `EngineeringReleaseApproval` 不存在 |
| verified_integrity | ✅ true | 无绕过（直接改 verified.json 检测通过） |

- **就绪度**：0/6 = 0%
- **ReleaseEvidenceBundle.complete**：`false`（阈值/审核/授权证据缺失）
- **结论**：**NO-GO**

**H3 进入规则**：仅当 G1–G6 全部通过（含人工确认 `ci_green` / `rollback_ready` 标志 + 真实授权 + 完整审核链 + 真实化阈值），方允许进入 H3；否则保持 NO-GO。三层不变量强制：`can_enable_engineering` 委托 + `release_precheck` 默认拒绝 + 全局 `engineering_enabled=false` + `manual_modified_thresholds` 拦截。

---

## 9. 后续人工动作（待各角色线下补齐）

1. **阈值提供方**：经 `ThresholdIntakeWorkflow` 填入 E-TH-01/02/03 六字段（value/unit/source_ref/version/verified_by/expert_verified_by）并双签（pending_verification）。
2. **专家 / 主理人**：在 `review_log` 生成四类 intake 事件并签字。
3. **主理人**：书面创建 `EngineeringReleaseApproval`（G6，满足 SoD），落 `release_approvals.jsonl`。
4. **发布执行人**：确认 `ci_green` 标志。
5. **回滚负责人**：确认 `rollback_ready` 标志。
6. 完成后重跑 `release_precheck('wind_pressure', return_report=True)` 复核 G1–G6 全绿，方可 `gray_release_ctl.py enable wind_pressure`。

---

*防编造声明：本文档所有阈值标识（E-TH-01/02/03）、版本号（3.2.5-H3-B）与配置哈希均为治理引用，非真实工程参数；真实数值、签名、授权均 pending_verification，由人工提供。*
