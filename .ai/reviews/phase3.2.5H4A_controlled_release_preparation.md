# 3.2.5-H4-A Controlled First Gray Release Preparation（pending_verification）

**阶段**：3.2.5-H4-A（首次受控灰度发布准备）（pending_verification）
**角色**：BOIP AI Release Governance 负责人
**日期**：2026-08-01
**前置**：H3-A（Production Evidence Collection）/ H3-B（Evidence Completion & Release Freeze）均 DONE

---

## 0. 红线守约声明

| 红线 | 状态 | 证据 |
|---|---|---|
| 1. 未开启 `engineering_enabled=true` | ✅ 守约 | 全程未触碰 `agents/config.yaml`；`load_engineering_enabled()` 仍 `False` |
| 2. 未输出 `engineering_approved` | ✅ 守约 | 全文无任何 approved 输出 |
| 3. 未生成真实工程参数 | ✅ 守约 | E-TH-01/02/03 `value` 仍 `null`（H3-B 冻结态） |
| 4. 未生成专家签名 | ✅ 守约 | `verified_by` / `expert_verified_by` 全 `null` |
| 5. 未自动创建 `ReleaseApproval` | ✅ 守约 | `release_approvals.jsonl` 不存在（count=0） |

> 本阶段为**纯治理设计**（Runbook + Gate/Monitor/Rollback/风险），零代码改动、零生产写入。所有符号均引用既有实现（见 H3-B 报告与 `agents/engineering/release/`）。

---

## 1. 任务2：Final Release Gate 流程（release_precheck → G1-G6 → Final Decision）

**目标**：定义首次灰度放行的唯一决策流程。

### 1.1 执行
调用 `release_precheck(interface="wind_pressure", return_report=True)`（见 `agents/engineering/release/gate.py`）：
- 内部委托 `ProductionReadinessChecker.run()`；
- `ProductionReadinessChecker` 再委托 `can_enable_engineering()`（`agents/engineering/gate/enable_gate.py`）作为 G1-G6 唯一事实来源；
- 同时派生子检查：`check_e_th_realization`（E-TH 真实化）、`check_review_log_chain`（审核链）、`manual_modified_thresholds`（绕过检测）、`load_approval_records`（授权在场）。

### 1.2 验证 G1-G6
返回 `ProductionReadinessReport`，逐项 `gate_status`：

| Gate | 含义 | 当前真实态 |
|---|---|---|
| G1 `G1_threshold_governance` | 阈值治理完备（status=verified + 结构化引用完整 + 双签齐全） | ❌ false（E-TH 仍 draft / value=null） |
| G2 `G2_dual_sign` | 双签齐全（`mgmt_signed` AND `expert_signed`） | ❌ false |
| G3 `G3_ci` | CI 全绿（人工确认 `ci_green`） | ❌ false（`ci_green` 未置位） |
| G4 `G4_audit_chain` | 审核链完整（四类 intake 事件 + 链无断裂） | ❌ false（四类事件全缺） |
| G5 `G5_rollback` | 回滚就绪（人工确认 `rollback_ready`） | ❌ false（`rollback_ready` 未置位） |
| G6 `G6_authorization` | 主理人书面授权到位且生效（SoD） | ❌ false（授权库不存在） |
| `verified_integrity` | 无绕过直接改 `verified.json` | ✅ true |

### 1.3 输出 Final Release Decision
- `report.allowed = all(gate_status[G1..G6])`（`verified_integrity` 不计入放行判定）；
- `allowed == True` → **GO**；否则 → **NO-GO**；
- `readiness = 通过门数 / 6` → 当前 `0/6 = 0%`；
- 阻断原因由 `report.blocking_reasons` 逐条列出（G1-G6 前缀 + 绕过标记）。

> 决策不可被任何执行步骤绕过：`enable_release` 在翻转开关前会**再次**调用 `release_precheck` 并强制 `allowed=True`。

---

## 2. 任务3：Monitor 方案（release_audit / approved_monitor / review_log → rollback）

**目标**：首次灰度期间对三类 append-only 监控源实时值守，异常即触发回滚。

### 2.1 监控数据来源（真实模块，仅引用无数值）

| 监控源 | 模块 | 落盘文件 | 记录内容 |
|---|---|---|---|
| `release_audit` | `agents/engineering/release/audit.py` | `release_audit.jsonl` | 每次 precheck/enable/disable/rollback/restore 的 `approval_id/interface/operator/action/timestamp/result` |
| `approved_monitor` | `agents/engineering/approved_monitor.py` | `approved_monitor.jsonl` | 每次 `engineering_approved` 出现的 `interface/threshold_version/sign_off_id/review_log_ref/error/timestamp`（**本阶段不触发**） |
| `review_log` | `agents/engineering/review_log.py` | `review_log.jsonl` | 四类 intake 审核事件链（`event_id/threshold_id/action/signer_role/signer/timestamp/source_ref/prev_event_id`） |

### 2.2 异常指标（触发 rollback）

| 异常指标 | 检测方式 | 触发动作 |
|---|---|---|
| 审核链断裂 | `review_log` 出现 `prev_event_id` 不匹配 / 缺四类事件之一 | 触发 `rollback --global` |
| 未授权 approved | `approved_monitor` 出现记录但无对应生效 `ReleaseApproval` | 触发 `rollback --interface wind_pressure` |
| 灰度开关被非授权翻转 | `release_audit` 出现 `enable` 成功但 `approval_id` 不匹配/未生效 | 触发 `rollback --global` |
| 监控源损坏/不可读 | 读取抛异常或行格式损坏 | 触发 `rollback --interface wind_pressure`（保守降级） |
| 快照缺失且需回滚 | `restore` 时 `_latest_snapshot() is None` | 拒绝 restore，保持当前态并人工介入 |

### 2.3 值守规则
- 监控值守**只读**三类日志，无权翻转开关；
- 异常 → 告警回滚负责人 → 由回滚负责人执行 Runbook 的 Rollback 步骤（满足 SoD）；
- 所有监控记录仅含标识符，不承载任何真实工程数值（红线 3）。

---

## 3. 任务4：Rollback 演练方案（snapshot / disable / rollback / restore）

**目标**：确认回滚四路径链路闭合，可在异常时安全恢复 `pending_verification`。

### 3.1 四路径（见 `controller.py` / `rollback.py`）

| 路径 | 命令 | 行为 | 不变量 |
|---|---|---|---|
| `snapshot` | 自动（`enable` 前置） | 写 `gray_release.*.snapshot.json`（当前开关快照） | 快照失败 → `enable` 拒绝 |
| `disable` | `gray_release_ctl.py disable --interface wind_pressure` | 接口 `enabled=False`，恢复 `pending_verification` | 仅翻开关，不改 `verified.json` |
| `rollback` | `gray_release_ctl.py rollback [--interface wind_pressure \| --global]` | 接口关闭或全局熔断（`default_enabled=False`）；回滚前自动快照 | 仅翻开关，不触碰 `review_log`/`approvals` |
| `restore` | `gray_release_ctl.py restore` | 从最近快照恢复灰度配置（回滚的回滚） | 无快照 → `REJECTED_NO_SNAPSHOT` 拒绝 |

### 3.2 演练流程（不落生产、可沙箱验证）
1. **预置**：确保 `gray_release.json` 默认态（全 `enabled=False`）；
2. **snapshot**：`enable` 成功前置会自动生成快照（验证 `_write_snapshot` 可写）；
3. **disable**：`disable --interface wind_pressure` → 确认开关落 `false`、审计追加；
4. **rollback**：`rollback --global` → 确认所有接口 `enabled=False`；
5. **restore**：`restore` → 确认从最近快照恢复至前置态；
6. **断言**：全程 `engineering_enabled` 不变（`False`）、`verified.json` 不变、`engineering_approved` 不出现。

> 演练须使用**专用临时路径**（`--config` / `--audit-path` / `--snapshot-dir`），避免污染仓库默认 `gray_release.json`（见 `gray_release_ctl.py` 安全契约）。

---

## 4. 任务5：发布风险评估（技术 / 工程 / 责任）

### 4.1 技术风险
| 风险 | 等级 | 缓解 |
|---|---|---|
| 快照/恢复文件落盘失败（权限/磁盘） | 中 | `enable` 前置快照失败即拒绝；`restore` 无快照拒绝并告警 |
| 灰度配置写竞争（并发 enable/rollback） | 低 | `_write_config` 原子写（tmp → replace） |
| 监控告警延迟导致窗口期误放量 | 中 | 保守降级：监控源损坏即触发接口级 rollback |
| CI 基线引用滞后（H3-A 481@90%） | 低 | `ci_green` 须人工确认，不自动置位 |

### 4.2 工程风险
| 风险 | 等级 | 缓解 |
|---|---|---|
| 灰度放开后 `engineering_enabled` 仍 `false` → 结果恒 `pending`（无真实计算） | 低（预期） | 属安全默认；真实计算须主理人显式置 `engineering_enabled=true`（仍须 G6） |
| 误开 `engineering_enabled` 致真实参数流出 | 高 | 三重拦截：`config_loader` 校验 + `can_enable_engineering` 委托 + `manual_modified_thresholds` 防绕过；本阶段绝不开启 |
| 阈值未真实化即放行 | 高 | G1/G2 门禁硬阻断；`verified.json` value 仍 null → `allowed=False` |

### 4.3 责任风险
| 风险 | 等级 | 缓解 |
|---|---|---|
| SoD 违例（`authorized_by == rollback_owner`） | 高 | G6 校验 `authorized_by ≠ rollback_owner`；责任矩阵显式分离 |
| 授权缺失/未生效即放行 | 高 | `enable_release` 强制 `find_approval_record` + `is_approval_effective` |
| 审核链不完整（缺四类 intake 事件） | 中 | G4 增强：`required_audit_events_present` 全类齐备才过 |
| 审计不可追溯 | 低 | 全部发布动作 append-only 落 `release_audit.jsonl`，仅引用标识符 |

---

## 5. 当前真实态与 GO / NO-GO

| Gate | 状态 | 阻塞原因 |
|---|---|---|
| G1 阈值治理 | ❌ false | 阈值真实数值未提供（value=null） |
| G2 双签 | ❌ false | 双签位 null |
| G3 CI | ❌ false | `ci_green` 未置位 |
| G4 审核链 | ❌ false | 四类 intake 事件缺失 |
| G5 回滚 | ❌ false | `rollback_ready` 未置位 |
| G6 授权 | ❌ false | `EngineeringReleaseApproval` 不存在 |
| verified_integrity | ✅ true | 无绕过 |

- **就绪度**：`0/6 = 0%`
- **结论**：**NO-GO**（与 H3-B 冻结态一致）
- **Runbook 状态**：已建立（`.ai/tasks/phase3.2.5H4A_release_runbook.md`），等待各角色线下补齐五类证据后，按 Runbook 进入真实执行。

---

## 6. 后续人工动作（待各角色线下补齐）

1. **阈值提供方 + 专家**：经 `ThresholdIntakeWorkflow` 真实化 E-TH-01/02/03 并双签（G1/G2）；
2. **专家 / 主理人**：在 `review_log` 生成四类 intake 事件并签字（G4）；
3. **主理人**：书面创建 `EngineeringReleaseApproval`（G6，满足 SoD），落 `release_approvals.jsonl`；
4. **发布执行人**：确认 `ci_green` 标志（G3）；
5. **回滚负责人**：确认 `rollback_ready` 标志（G5）；
6. 重跑 `release_precheck('wind_pressure', return_report=True)` 复核 G1-G6 全绿 → **GO** → 按 Runbook 的 Enable 步骤执行 `gray_release_ctl.py enable wind_pressure`。

---

*防编造声明：本文档所有阈值标识（E-TH-01/02/03）、版本号（3.2.5-H4-A）、配置/证据哈希均为治理引用，非真实工程参数；真实数值、签名、授权均 `pending_verification`，由人工经正式流程提供。*
