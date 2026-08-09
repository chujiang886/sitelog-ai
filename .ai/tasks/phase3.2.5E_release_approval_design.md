# BOIP Phase 3.2 Sprint 3.2.5-E 工程灰度授权与执行准备（Engineering Gray Release Authorization & Execution Preparation）

- **阶段**：Phase 3.2 Sprint 3.2.5-E
- **身份**：BOIP AI 工程发布治理负责人（Engineering Release Governance Lead）
- **性质**：首次工程灰度发布的**责任与执行体系设计**——**非开启 `engineering_enabled`、非输出 `engineering_approved`、非修改生产 `verified.json`、非真实灰度放量**，全部 `pending_verification`。
- **日期**：2026-07-31

---

## 0. 摘要

本设计文档为 `wind_pressure` 首次工程灰度的**授权与执行体系**建立规范骨架，覆盖：

1. **发布授权记录（EngineeringReleaseApproval）**——把"谁、何时、对什么范围、授权了什么、谁负责回滚、依据哪份书面授权"固化为可审计单条记录；
2. **首次灰度执行流程**——Pre-check → Authorization → Enable → Monitor → Rollback 五步，每步明确责任人；
3. **人工确认清单**——首次 `wind_pressure` 灰度放行前，G1-G6 / 责任 / 风险 / 回滚四类确认；
4. **灰度执行脚本设计**——未来 `enable` / `disable` / `rollback` 三指令，**默认关闭**（不显式授权即拒绝）。

> 红线重申：本设计阶段不开启 `engineering_enabled`、不输出 `engineering_approved`、不修改生产 `verified.json`、不真实放量；所有"真实激活"动作仅在主理人书面授权（G6）并经 G1-G6 全绿后由人工执行。本文仅为体系设计，零代码改动。

---

## 1. 任务1：Release Approval Record 设计（EngineeringReleaseApproval）

### 1.1 设计目标

把"首次工程灰度放行"这一高责任动作固化为一条**不可篡改的授权记录**，使责任边界、范围、生效时间、回滚责任人、授权依据全部可被事后溯源。该记录与主理人 G6 书面授权一一对应，是 `can_enable_engineering` 中 `authorization_present` 注入项的**唯一可信来源**。

### 1.2 字段定义

| 字段 | 类型 | 含义 | 来源 / 约束 |
|------|------|------|-------------|
| `approval_id` | string | 授权记录唯一标识 | 格式 `GR-<YYYYMMDD>-<interface>`，如 `GR-20260731-wind_pressure`；确定性、全局唯一 |
| `interface` | string | 被授权放行的接口标识 | 本次仅 `wind_pressure`（灰度白名单唯一项） |
| `scope` | object | 放行范围 | 含 `threshold_ids`（本次 `E-TH-01`、`E-TH-02`、`E-TH-03`）、`rollout_pct`（放量比例，占位待授权时填）、`allowed_project_tags`（允许的项目标签）；**不写真实工程数值** |
| `authorized_by` | string | 授权主体（主理人）标识 | 独立于 3.2.4 双签主体（SoD）；仅标识符，不写姓名原文 |
| `effective_time` | string | 授权生效时间（UTC ISO8601） | 由主理人签署时写入；未签署则为 null |
| `rollback_owner` | string | 回滚责任人（角色/标识） | 明确指定，且与 `authorized_by` 可不同（职责分离）；本次建议 = 工程治理负责人角色 |
| `approval_document_ref` | string | 书面授权文档引用 | 指向主理人签署的书面授权文件 + `review_log_ref`（审核链锚点）+ 未来 `approved_monitor` 记录锚点，形成三锚溯源 |

### 1.3 不变量（红线）

- **仅引用**：`scope` 中只含标识符与配置布尔/百分比占位，**绝不写入真实风压 / 壁厚 / 楼层等业务数值**；
- **SoD 约束**：`authorized_by`（G6 主理人授权）不得与 3.2.4 双签主体（`verified_by` / `expert_verified_by`）为同一人；`rollback_owner` 与 `authorized_by` 亦应分离；
- **append-only**：授权记录一旦签署不可修改，仅可追加"撤销/回滚"新记录；
- **未授权即无效**：无对应 `EngineeringReleaseApproval` 且 `authorization_present=False` 时，`can_enable_engineering` 恒返回 `(False, [G6_authorization_missing])`。

### 1.4 与既有监控/审核链的衔接

- `approval_document_ref` 同时指向 `review_log`（四步双签链：`intake_submit→review_approve→expert_recheck→intake_verified`）与未来的 `approved_monitor`（每次 `engineering_approved` 落盘引用）；
- 证据链：`EngineeringReleaseApproval` → `review_log`（阈值真实化与双签）→ `approved_monitor`（工程放行落盘），三者通过 `sign_off_id` / `review_log_ref` 互锚，责任可追溯。

---

## 2. 任务2：首次灰度执行流程设计（Pre-check → Authorization → Enable → Monitor → Rollback）

流程五步，每步标注**责任人**、**动作**、**闸门/不变量**。

| 步骤 | 责任人 | 动作 | 闸门 / 不变量 |
|------|--------|------|---------------|
| **① Pre-check（前置检查）** | 工程治理负责人（Release Gatekeeper） | 运行 `can_enable_engineering()`，逐项核验 G1（阈值治理）G2（双签）G3（CI 绿）G4（审核链）G5（回滚就绪）G6（书面授权）；输出预检报告 | 任一门禁未过 → 中止，禁止进入下一步；所有默认值取"不满足"，默认 `(False, reasons)` |
| **② Authorization（授权）** | 主理人（Principal / Project Admin） | 签署 `EngineeringReleaseApproval`（写入 `approval_id`/`scope`/`authorized_by`/`effective_time`/`rollback_owner`/`approval_document_ref`），注入 `authorization_present=True` | 须独立于 3.2.4 双签主体（SoD）；授权记录 append-only；未签署则 G6 缺 |
| **③ Enable（开启灰度）** | 发布执行人（Release Operator） | 先 `RollbackHandler.snapshot()` 保存开关态；再置全局 `orchestrator.engineering_enabled=true`（经 `config_loader` 校验）并置 `GrayReleaseEntry(interface="wind_pressure", enabled=True, rollout_pct>0)` | 双重保险：全局 `engineering_enabled=false` 时 `is_interface_gray_allowed` 恒 False（不可绕过）；未授权/未预检通过则 `config_loader` 拦截 |
| **④ Monitor（监控）** | 自动化 Monitor + 审核链监督 | 每次 `engineering_approved` 出现 → `append_approved_record`（仅引用字段）；审核链监督定期回放 `approved_monitor.jsonl` + `review_log` 比对一致性 | 仅记录引用/标识符，绝不写真实数值；append-only 不可篡改 |
| **⑤ Rollback（回滚）** | 回滚负责人（rollback_owner，命名于授权记录） | 异常时 `RollbackHandler.close_interface("wind_pressure")` 或 `close_global()`（熔断）；必要时 `restore()` 从快照恢复 | 回滚**仅翻转灰度开关**，不触碰历史 `review_log`；恢复语义 = 结果回落 `pending_verification` |

**流程不变量**：
- 顺序不可跳：`Authorization` 须在 `Enable` 之前，`Pre-check` 须在 `Authorization` 之前；
- `Enable` 前置快照：任何开关态变更前必须 `snapshot()`，保证"回滚的回滚"可行；
- 责任可溯：每步操作主体写入 `review_log`（signer_role / signer / sign_off_id）。

---

## 3. 任务3：人工确认清单（首次 `wind_pressure` 灰度 Checklist）

> 本清单为**人工放行前逐项签字确认表**。每一项须由对应责任人显式确认（✔）后方可进入下一步。本文仅给出模板，未执行真实确认。

### 3.1 G1-G6 门禁确认

| 门禁 | 确认项 | 责任人 | 确认 |
|------|--------|--------|------|
| G1 阈值治理 | E-TH-01 / E-TH-02 / E-TH-03 已真实化（`threshold_status=verified` + 结构化 `source_ref` 完整） | 工程治理负责人 | ☐ |
| G2 双签 | 三阈值主理人签 + 专家签齐全，SoD（`verified_by ≠ expert_verified_by`） | 工程治理负责人 | ☐ |
| G3 CI 全绿 | 发布前重跑 `bash scripts/ci/local_ci.sh` 8/8 全绿、覆盖率达标 | 发布执行人 | ☐ |
| G4 审核链 | `review_log` 四步链 `_chain_intact` 无断裂/无损坏行 | 审核链监督 | ☐ |
| G5 回滚就绪 | `RollbackHandler` 可用、`snapshot()` 已就绪 | 回滚负责人 | ☐ |
| G6 书面授权 | 主理人签署 `EngineeringReleaseApproval`，`authorization_present=True` 且 SoD 独立 | 主理人 | ☐ |

### 3.2 责任确认

| 角色 | 职责边界 | 确认 |
|------|----------|------|
| 阈值提供方（人工） | 提供真实 `value`/`unit`/`source_ref`，对数值真实性负责 | ☐ |
| 主理人（Principal） | 核准放行、签署 G6 授权，对"是否放行"决策负责 | ☐ |
| 专家签署人（Expert） | 对规范符合性双签，对专业判断负责 | ☐ |
| 发布执行人（Operator） | 按授权执行 Enable/Disable，对操作正确性负责 | ☐ |
| 回滚负责人（rollback_owner） | 异常时执行回滚，对回滚时效负责 | ☐ |

### 3.3 风险确认

| 风险类别 | 关键风险 | 责任人知悉 |
|----------|----------|------------|
| 技术 | 灰度开关与全局闸门不一致误判；CI 基线漂移 | ☐ |
| 工程 | 阈值转真 ≠ 工程批准；范围误扩大至 D-TH / E-TH-04 至 E-TH-06 | ☐ |
| 责任 | 授权主体混淆（SoD 违反）；未经授权擅自开启 | ☐ |

### 3.4 回滚确认

| 确认项 | 说明 | 确认 |
|--------|------|------|
| 接口关闭可用 | `close_interface("wind_pressure")` 验证结果回落 `pending_verification` | ☐ |
| 全局熔断可用 | `close_global()` 验证全部接口回落 pending | ☐ |
| 快照恢复可用 | `restore()` 从 snapshot 恢复原态，且不触碰 `review_log` | ☐ |
| 回滚责任人就位 | `rollback_owner` 已在授权记录中指定且知悉 | ☐ |

---

## 4. 任务4：灰度执行脚本设计（enable / disable / rollback，默认关闭）

### 4.1 脚本定位

- 路径（未来）：`scripts/release/gray_release_ctl.py`
- 角色：把 §2 的 `Enable` / `Rollback` 步骤外显为可审计 CLI，强制"先快照、后变更、按授权"。
- **默认关闭原则（Hard Default-Closed）**：脚本所有变更操作缺省拒绝；未携带有效授权与预检通过证据时，任何 `enable` / `disable` 变更一律拒绝执行，绝不静默放行。

### 4.2 子命令设计

| 子命令 | 作用 | 默认行为 / 保护 |
|--------|------|----------------|
| `precheck` | 运行 `can_enable_engineering()` 打印 G1-G6 状态 | 只读，不改动 |
| `enable <interface>` | 置该接口 `GrayReleaseEntry.enabled=True` + 全局 `engineering_enabled=True`（经校验） | **前置**：`snapshot()` + 校验 `authorization_present` + G1-G6 全绿；缺一则拒绝 |
| `disable <interface>` | `close_interface`：置该接口 `enabled=False`（回落 pending） | 需 `rollback_owner` 授权；不触碰 `review_log` |
| `rollback --global` | `close_global()` 熔断 | 需 `rollback_owner` 授权；全局回落 pending |
| `restore` | `restore()` 从快照恢复 | 优先显式 snapshot，否则自动快照；不触碰 `review_log` |

### 4.3 关键不变量（脚本层）

1. **先快照后变更**：`enable` / `disable` / `rollback` 任意变更前必须 `RollbackHandler.snapshot()`；
2. **授权门禁硬校验**：`enable` 仅在 `can_enable_engineering()` 返回 `(True, [])` 且存在有效 `EngineeringReleaseApproval` 时执行；否则以非零退出码拒绝；
3. **全局闸门不可绕过**：即便灰度条目 `enabled=True`，若全局 `engineering_enabled=false`，`is_interface_gray_allowed` 仍恒 False（脚本不做任何绕过）；
4. **默认关闭**：脚本进程即便异常退出，配置落盘前状态仍为 `enabled=False`（原子写入 + 失败回滚）；不存在"默认可放"的代码路径；
5. **仅引用落盘**：脚本触发的 `append_approved_record` / `review_log` 事件只写引用/标识符，绝不写真实工程数值；
6. **回滚不变量**：`disable` / `rollback` / `restore` 仅翻转灰度开关，不修改历史 `review_log`。

### 4.4 调用示例（伪命令，非真实执行）

```
# 仅预检（只读）
python scripts/release/gray_release_ctl.py precheck

# 授权后开启（须 EngineeringReleaseApproval 存在 + G1-G6 全绿）
python scripts/release/gray_release_ctl.py enable wind_pressure --approval GR-20260731-wind_pressure

# 异常回滚（接口级）
python scripts/release/gray_release_ctl.py disable wind_pressure --by rollback_owner

# 全局熔断
python scripts/release/gray_release_ctl.py rollback --global --by rollback_owner

# 从快照恢复
python scripts/release/gray_release_ctl.py restore
```

> 上述命令为设计示意；本阶段未实现、未执行、未触碰任何生产配置。

---

## 5. 红线守约声明

- 未开启 `engineering_enabled`（仍为 false）；
- 未输出 `engineering_approved`；
- 未修改生产 `verified.json`（仍为 schema_version 1 占位态）；
- 未真实灰度放量（仅 `wind_pressure` 设计，未激活）；
- 全部 `pending_verification`。

**本设计为体系骨架文档，零代码改动，待主理人书面授权（G6）并经 G1-G6 全绿后，由人工依本设计执行真实放行。**
