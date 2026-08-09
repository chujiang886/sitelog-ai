# BOIP Phase 3.2 Sprint 3.2.5-H2-B — Production Human Authorization Gate Report

> 身份：BOIP AI Release Governance 负责人
> 日期：2026-08-01
> 阶段性质：真实人工授权闸门（纯治理检查 + 文档产出，零代码改动，沿用 481 passed@90% 基线）
> 最高红线：不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动生成真实工程参数/专家签名、不自动创建 `ReleaseApproval`；全部真实数据须人工提供。

---

## 0. 总结论（Gate Decision）

**NO-GO — 禁止进入 H3。**

真实生产态下 G1–G6 **全部阻断**（就绪度 0/6 = 0%）。无任何真实人工授权数据已进入系统：
`verified.json` 仍 `schema_version=1`、E-TH-01/02/03 全 `value=null`、双签位 `null`；
`release_approvals.jsonl` 不存在（G6 授权记录 count=0）；
`engineering_enabled` 仍 `false`（零翻转）。

本阶段仅检查授权入口是否齐备，**未**触发任何真实录入 / 授权 / 开关翻转。

---

## 1. 任务1：真实阈值输入接口最终检查

目标：确认 `ThresholdIntakeWorkflow` 能为 E-TH-01/02/03 接收并承载全部六字段。

**核验对象**：`agents/engineering/threshold_intake.py`

| 要求字段 | 接口支持位置 | 结论 |
|---|---|---|
| `value` | `IntakeRequest.value` → 草稿态写入 `entry["value"]` | ✅ |
| `unit` | `IntakeRequest.unit` → `entry["unit"]` | ✅ |
| `source_ref` | `IntakeRequest.source_ref`（含 C1–C6 校验，不通过即拒） | ✅ |
| `version` | `IntakeRequest.version`（缺省 1.0.0） | ✅ |
| `verified_by` | `review()` 步骤写入 `entry["verified_by"] / verified_at`（主理人核准） | ✅ |
| `expert_verified_by` | `expert_recheck()` 步骤写入 `entry["expert_verified_by"] / expert_verified_at`（专家复核） | ✅ |

**授权范围（红线）**：`DEFAULT_ALLOWED_IDS = {E-TH-01, E-TH-02, E-TH-03}`，越权（D-TH / E-TH-04~06）一律拒绝。

**审核链事件（满足 G4 `required_audit_events`）**：
`submit()` → `intake_submit` · `review()` → `intake_review_approve` · `expert_recheck()` → `intake_expert_recheck` · `finalize_verified()` → `intake_verified`。四类必需事件齐备，逻辑链正确。

**SoD 强制**：`expert_recheck()` 要求 `expert_verified_by != verified_by`，否则 `REASON_SOD_CONFLICT` 拒绝。

**接口结论**：阈值输入入口齐备，可在人工提供真实数据后承接 E-TH-01/02/03 六字段 + 双签 + 审核链。**当前真实态未调用**（仍为占位 draft）。

---

## 2. 任务2：G6 授权入口检查

目标：确认 `EngineeringReleaseApproval` 入口承载七字段并满足 SoD。

**核验对象**：`agents/engineering/release/approval.py`

| 要求字段 | 类型/语义 | 结论 |
|---|---|---|
| `approval_id` | 授权唯一标识（标识符） | ✅ |
| `interface` | 适用接口（首个 `wind_pressure`） | ✅ |
| `scope` | 灰度范围（标签/标识符） | ✅ |
| `authorized_by` | 授权签署人（须异于 3.2.4 双签主体，SoD） | ✅ |
| `effective_time` | 授权生效时间（ISO8601；未来时间视为未生效） | ✅ |
| `rollback_owner` | 回滚责任人（须异于 `authorized_by`，SoD） | ✅ |
| `approval_document_ref` | 书面授权文档引用 | ✅ |

**不变量（红线）**：append-only（仅追加，不修改/删除）；仅记录引用/标识符，**绝不**写入任何真实工程数值；不读写 `verified.json`、不翻转 `engineering_enabled`、不输出 `engineering_approved`。

**接口结论**：G6 授权入口齐备且 SoD 双重隔离（`authorized_by≠rollback_owner`，且与 3.2.4 双签主体独立）。**当前真实态无授权记录**（库不存在，count=0）。

---

## 3. 任务3：Final Human Authorization Gate Report（真实态）

> 以下为对**生产真实态**的只读核验结果（来源：`release_precheck(interface='wind_pressure', return_report=True)` 既定行为 + 生产文件直读）。

### 3.1 G1–G6 真实态

| 门禁 | 含义 | 真实态 | 阻断原因 |
|---|---|---|---|
| **G1** 治理/授权范围 | 阈值在授权范围且已真实化 | ❌ FAIL | E-TH-01/02/03 `value=null`、未真实化（draft） |
| **G2** 双签 + SoD | 主理人核准 + 专家复核 | ❌ FAIL | `verified_by=null`、`expert_verified_by=null` |
| **G3** CI 绿 | 测试套件全绿 | ❌ FAIL | 真实放量前未显式确认 `ci_green`（默认 False） |
| **G4** 审核链 | 四类 intake 事件齐备 | ❌ FAIL | `review_log` 缺失 `intake_submit/review_approve/expert_recheck/verified` |
| **G5** 回滚就绪 | 快照 + 回滚路径就绪 | ❌ FAIL | 回滚就绪未显式确认（默认 False） |
| **G6** 授权 | `EngineeringReleaseApproval` 在场且生效 | ❌ FAIL | `release_approvals.jsonl` 不存在，count=0 |

**就绪度（readiness score）**：`0/6 = 0%（NO-GO）`

### 3.2 Blocking Reasons（聚合）

1. E-TH-01/02/03 仍 `value=null`、未真实化（G1 阻断源）。
2. 双签位全 `null`，未经过 `ThresholdIntakeWorkflow` 主理人核准与专家复核（G2 阻断源）。
3. CI 未显式确认绿（G3 阻断源）。
4. `review_log` 无四类必需 intake 事件（G4 阻断源）。
5. 回滚就绪未确认（G5 阻断源）。
6. 无主理人书面 `EngineeringReleaseApproval` 授权记录（G6 阻断源）。

### 3.3 旁路 / 完整性

- `verified_integrity`（绕过检测）：✅ PASS（生产 `verified.json` 无绕过 `ThresholdIntakeWorkflow` 直接填实条目）。
- `engineering_enabled`：✅ `false`（零翻转，双保险：全局开关 + `release_precheck` 默认拒绝 + `manual_modified_thresholds` 拦截）。

---

## 4. 任务4：Release 责任确认表

| 角色 | 职责边界 | SoD 约束 |
|---|---|---|
| **阈值提供方** | 经 `ThresholdIntakeWorkflow.submit()` 人工提供 E-TH-01/02/03 的 `value/unit/source_ref/version` 真实数据；对数值来源真实性负责 | ≠ 主理人、≠ 专家、≠ 发布执行人 |
| **专家** | 经 `expert_recheck()` 复核签字（`expert_verified_by`），确认规范适用性；对专业技术结论负责 | ≠ 主理人（双签 SoD），≠ 阈值提供方 |
| **主理人** | 经 `review()` 核准（`verified_by`）→ 经 G6 书面签署 `EngineeringReleaseApproval`（`authorized_by`）；对放量决策负责 | ≠ 专家（双签 SoD），≠ `rollback_owner`（G6 SoD） |
| **发布执行人** | 在 G1–G6 全绿后，按 `gray_release_ctl.py enable wind_pressure` 执行灰度开启；不自行决定放量 | ≠ 主理人、≠ 回滚负责人 |
| **回滚负责人（rollback_owner）** | 持有回滚路径，任一 G 失败/异常时执行 `rollback`/`restore`；对回滚时效与完整性负责 | ≠ `authorized_by`（G6 SoD） |

**责任边界红线**：任一角色不得兼任冲突角色；AI 不替代任何角色签署或决策。

---

## 5. 任务5：进入条件判断（H3 准入）

```
                 G1 ─┐
                     │ 全部 = ✅
                 G2 ─┤
                     │
                 G3 ─┤
                     ├─► 全部通过 ─► 允许进入 H3（真实灰度放量执行）
                 G4 ─┤
                     │
                 G5 ─┤
                     │ 任一 = ❌
                 G6 ─┘
                       │
                       └─► 保持 NO-GO（禁止 enable wind_pressure）
```

**判定规则（硬约束）**：
- **当且仅当 G1–G6 全绿**，方可进入 H3（真实灰度放量执行阶段）。
- **任一 G 未绿** → 系统保持 `pending_verification`，禁止 `gray_release_ctl.py enable wind_pressure`，禁止翻转 `engineering_enabled`。
- 本规则由三层代码不变量强制保证：`can_enable_engineering` 委托门禁 + `release_precheck` 默认拒绝 + 全局 `engineering_enabled=false` 双保险 + `manual_modified_thresholds` 拦截绕过。

---

## 6. 红线守约确认

| 红线 | 本阶段状态 |
|---|---|
| 不自动开启 `engineering_enabled` | ✅ 仍 `false`（零翻转） |
| 不输出 `engineering_approved` | ✅ 未输出 |
| 不自动生成真实工程参数 | ✅ E-TH 仍 `value=null` |
| 不自动生成专家签名 | ✅ 双签位仍 `null` |
| 不自动创建 `ReleaseApproval` | ✅ 授权库不存在，count=0 |
| 全部真实信息人工提供 | ✅ 仍为 `pending_verification` |

---

## 7. 后续人工动作（解锁 H3 前置）

1. 阈值提供方经 `ThresholdIntakeWorkflow` 真实化 E-TH-01/02/03（六字段 + `source_ref` C1–C6 通过）。
2. 主理人 `review()` 核准 + 专家 `expert_recheck()` 复核（双签 SoD）。
3. 主理人 `finalize_verified()` 转正（写入四类 intake 事件，满足 G4）。
4. 重跑 `bash scripts/ci/local_ci.sh` 确认 CI 绿（G3）。
5. 确认回滚快照/路径就绪（G5）。
6. 主理人书面签署 `EngineeringReleaseApproval`（`authorized_by`≠`rollback_owner`，G6），且 `effective_time` 已生效。
7. 人工显式置 `engineering_enabled=true`（经 G6 授权）→ `gray_release_ctl.py enable wind_pressure` 进入 H3。

**按指令完成后停止**：未达成上述任一前置，系统保持 NO-GO。
