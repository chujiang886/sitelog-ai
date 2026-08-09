# BOIP Phase 3.2 Sprint 3.2.5-H3-A — Production Evidence Collection & Human Completion

**阶段**：3.2.5-H3-A（首次灰度发布前人工证据补齐）
**身份**：BOIP AI Release Governance 负责人
**生成时间**：2026-08-01（本地）
**性质**：纯治理证据收集与核验包（零代码改动），沿用 481 passed @ 90% 基线

---

## 0. 红线守约声明（最高优先级）

| 红线 | 状态 | 证据 |
|---|---|---|
| 1. 开启 engineering_enabled=true | ❌ 未开启 | `load_engineering_enabled()` = **False**（实测） |
| 2. 输出 engineering_approved | ❌ 未输出 | 本报告不含任何 `engineering_approved` 字段/判定 |
| 3. AI 生成真实工程参数 | ❌ 未生成 | E-TH-01/02/03 `value` 仍全为 `null` |
| 4. AI 生成专家签名 | ❌ 未生成 | `verified_by` / `expert_verified_by` 仍全为 `null` |
| 5. AI 自动创建 ReleaseApproval | ❌ 未创建 | `release_approvals.jsonl` 不存在（授权库 count=0） |

> **结论**：本阶段仅为"证据收集流程设计与当前证据核验"，所有真实证据（阈值数值、双签、授权、CI 确认、回滚确认）必须由人工/对应角色提供，AI 不代填、不代签、不代授权。

---

## 1. 任务1：E-TH 真实证据收集流程

### 1.1 证据检查项（七字段）
对 E-TH-01 / E-TH-02 / E-TH-03，每项必须齐备：

| 字段 | 含义 | 提供方 |
|---|---|---|
| value | 真实工程阈值数值 | 阈值提供方（基于规范） |
| unit | 单位 | 阈值提供方 |
| source_ref | 结构化规范/标准引用 | 阈值提供方 + 专家 |
| version | 规范版本 | 阈值提供方 |
| verified_by | 主理人签字 | 主理人 |
| expert_verified_by | 行业专家签字 | 行业专家 |
| threshold_status | 状态置 `verified`（经审核链后） | 系统自动（intake_verified） |

### 1.2 当前真实态（只读，未经改动）
数据源：生产 `agents/engineering/thresholds/verified.json`。

| 条目 | value | unit | source_ref | version | verified_by | expert_verified_by | threshold_status |
|---|---|---|---|---|---|---|---|
| E-TH-01 | `null` | `Pa` | 占位（待专家签字填入） | `null` | `null` | `null` | `null` |
| E-TH-02 | `null` | `pending_verification` | 占位 | `null` | `null` | `null` | `null` |
| E-TH-03 | `null` | `pending_verification` | 占位 | `null` | `null` | `null` | `null` |

### 1.3 判定
- 三项阈值 **value 全空、双签全空、source_ref 占位、threshold_status 非 verified**。
- **阈值证据 = 缺失**（0/3 项齐备）。
- 依据规则"缺一：保持 NO-GO" → **G1/G2 未过 → NO-GO**。

> 入口 `ThresholdIntakeWorkflow` 已具备六字段承载能力与四类 intake 审核事件，但真实数据尚未经该流程录入。

---

## 2. 任务2：审核链证据检查

### 2.1 必需审核事件（四类，缺一不可）
`review_log` 必须包含针对 wind_pressure 的完整链：
1. `intake_submit`（提交）
2. `intake_review_approve`（复核批准）
3. `intake_expert_recheck`（专家复核）
4. `intake_verified`（验证完成 → threshold_status=verified）

### 2.2 当前真实态
- 生产 `agents/engineering/review_log.jsonl` 体积 **352 B**（占位草案，无真实 intake 链）。
- `ProductionReadinessChecker` 实测 `G4_audit_chain=false`、`review_chain_intact=None`。

### 2.3 判定
- **审核链证据 = 缺失**（四类事件均无真实记录）。
- → **G4 未过 → NO-GO**。

---

## 3. 任务3：G6 授权证据检查

### 3.1 授权记录字段（七字段，须齐备）
`EngineeringReleaseApproval` 落盘于 `agents/engineering/release/release_approvals.jsonl`（append-only）：

| 字段 | 含义 |
|---|---|
| approval_id | 授权唯一标识 |
| interface | 授权接口（wind_pressure） |
| scope | 灰度范围 |
| authorized_by | 授权签署人（主理人，须异于 3.2.4 双签主体） |
| effective_time | 生效时间（ISO8601） |
| rollback_owner | 回滚责任人（须异于 authorized_by，SoD） |
| approval_document_ref | 书面授权文档引用 |

### 3.2 SoD 校验
- `authorized_by` ≠ `rollback_owner`
- 二者独立于 3.2.4 阈值双签主体（principal / expert）

### 3.3 当前真实态
- `release_approvals.jsonl` **不存在**（os error 2）→ 授权库 **count=0**。
- 真实态 `G6_authorization=false`、`approval_present=False`。

### 3.4 判定
- **授权证据 = 缺失**（0 条授权记录）。
- → **G6 未过 → NO-GO**。

---

## 4. 任务4：Release Evidence Bundle（发布证据包设计）

> 证据包 = 进入 H3 前须齐备的五类证据的集合。下列为**证据包结构设计**（含存放位置、提供角色、当前状态）。

| 证据类别 | 存放位置 | 提供角色 | 当前状态 |
|---|---|---|---|
| **Threshold Evidence**（阈值证据） | `agents/engineering/thresholds/verified.json`（经 ThresholdIntakeWorkflow 写入） | 阈值提供方 + 行业专家双签 | ❌ 缺失（E-TH value/双签全 null） |
| **Review Evidence**（审核证据） | `agents/engineering/review_log.jsonl`（四类 intake 事件） | 阈值提供方 / 专家 / 主理人 | ❌ 缺失（占位 352B，无真实链） |
| **Authorization Evidence**（授权证据） | `agents/engineering/release/release_approvals.jsonl`（EngineeringReleaseApproval） | 主理人（G6，SoD） | ❌ 缺失（文件不存在，count=0） |
| **CI Evidence**（CI 证据） | `scripts/ci/local_ci.sh` 运行产物（481 passed@90%） | CI 系统 / 发布执行人确认 `ci_green=true` | ⚠️ 代码基线绿（481@90%），但 `ci_green` 标识**未经人工确认** |
| **Rollback Evidence**（回滚证据） | `gray_release_ctl.py` 快照目录（enable 前置）+ rollback/restore 能力 | 回滚负责人确认 `rollback_ready=true` | ⚠️ 代码路径完整（snapshot/disable/rollback/restore 接线），但 `rollback_ready` 标识**未经人工确认** |

### 4.1 证据包完整性矩阵

| Gate | 依赖证据 | 证据齐备？ | Gate 结果 |
|---|---|---|---|
| G1 阈值治理 | Threshold Evidence | ❌ | false |
| G2 双签 | Threshold Evidence（双签位） | ❌ | false |
| G3 CI | CI Evidence（ci_green 确认） | ⚠️ 待确认 | false |
| G4 审核链 | Review Evidence | ❌ | false |
| G5 回滚 | Rollback Evidence（rollback_ready 确认） | ⚠️ 待确认 | false |
| G6 授权 | Authorization Evidence | ❌ | false |

---

## 5. 任务5：H3 准入判断（GO / NO-GO）

### 5.1 规则
> 只有 **G1–G6 全部通过**，才允许进入 **H3**（真实灰度放量执行）。
> 否则：保持 **NO-GO**。

### 5.2 当前判定

| 维度 | 结果 |
|---|---|
| G1–G6 全绿？ | ❌ 否（0/6 通过，仅 verified_integrity 通过） |
| 判定 | **NO-GO** |
| 是否可进入 H3 | ❌ 不可 |

### 5.3 补齐证据清单（进入 H3 前的硬性人工动作）
1. **阈值证据**：人工经 `ThresholdIntakeWorkflow` 录入 E-TH-01/02/03 六字段（value/unit/source_ref/version/verified_by/expert_verified_by）+ 结构化规范引用。
2. **审核证据**：`review_log` 写入完整四类 intake 事件（submit → review_approve → expert_recheck → verified），使 threshold_status=verified。
3. **授权证据**：主理人签署 `EngineeringReleaseApproval`（七字段，authorized_by≠rollback_owner，独立于双签主体），落盘授权库。
4. **CI 证据**：发布执行人确认 `ci_green=true`（481 passed@90% 基线保持）。
5. **回滚证据**：回滚负责人确认 `rollback_ready=true`（代码路径已齐备）。
6. **显式开启**：主理人置 `engineering_enabled=true`（全局双保险解除），并经 `gray_release_ctl.py enable wind_pressure` 触发快照 + 门禁复验。

> 上述 1–5 任一项缺失 → 证据包不完整 → 保持 NO-GO。

---

## 6. 最终审核结论

**3.2.5-H3-A Production Evidence Collection = DONE（证据收集流程设计完成，当前证据不完整 → NO-GO）**

- 五类证据中：**阈值 / 审核 / 授权 三类完全缺失**；**CI / 回滚 两类代码侧已具备但等待人工确认标志**。
- 真实态 G1–G6 全阻断，就绪度 0/6 = 0%。
- `engineering_enabled` = **False**（零翻转）。
- 红线 1–5 全部守约。
- **本阶段不进入 H3**，保持 NO-GO，等待人工补齐全部证据。

**后续动作**：交由主理人 / 行业专家 / 阈值提供方 / 发布执行人 / 回滚负责人线下分别补齐上述证据，完成后重跑 `release_precheck` 复核 G1–G6 全绿，方可进入 H3。

---

*本报告为纯治理证据收集与核验产物，未修改任何生产文件（verified.json / review_log.jsonl / 授权库均未被改动），未开启 engineering_enabled，未输出 engineering_approved。*
