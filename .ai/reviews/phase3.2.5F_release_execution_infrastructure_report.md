# BOIP Phase 3.2 Sprint 3.2.5-F 工程灰度发布执行基础设施 就绪评审

- 身份：BOIP AI 发布治理架构负责人
- 类型：执行基础设施实现（IMPL_DONE）
- 日期：2026-07-31
- 状态：代码落地，生产仍未放行（pending_verification）

---

## 1. 交付物总览

| 任务 | 交付 | 类型 |
| --- | --- | --- |
| 任务1 | `agents/engineering/release/approval.py` + 包 `__init__.py` | 代码 |
| 任务2 | `agents/engineering/release/gate.py`（`release_precheck`） | 代码 |
| 任务3 | `scripts/release/gray_release_ctl.py`（precheck/enable/disable/rollback/restore） | 代码 |
| 任务4 | `agents/engineering/release/audit.py`（`release_audit.jsonl` 写入） | 代码 |
| 任务5 | `tests/agents/test_release_execution.py`（25 用例） | 测试 |
| 输出 | 本评审 + SSOT/roadmap 更新 | 文档 |

新增 `agents/engineering/release/` 包四个模块：
- `approval.py`：`EngineeringReleaseApproval` 七字段授权记录（approval_id / interface / scope / authorized_by / effective_time / rollback_owner / approval_document_ref），**append-only**，仅引用字段。
- `gate.py`：`release_precheck()` 委托既有 `can_enable_engineering` 执行 G1-G6，返回 `(allowed, blocking_reasons)`，默认 `(False, reasons)`。
- `controller.py`：执行核心 `enable_release` / `disable_release` / `rollback_release` / `restore_release`，CLI 与测试共用。
- `audit.py`：`ReleaseAuditRecord`（approval_id / interface / operator / action / timestamp / result），**append-only**，仅引用，无真实工程数值。

---

## 2. 设计要点与不可变式

### 2.1 EngineeringReleaseApproval（G6 证据唯一可信源）
- 七字段契约与 3.2.5-E 设计一致；写入即 append-only，不修改/删除历史。
- `find_approval_record(approval_id)` 按标识查找；`is_approval_effective()` 判定 `effective_time` 是否生效（未来时间视为尚未授权）。
- SoD 在策略层约束：`authorized_by` / `rollback_owner` 须异于 3.2.4 双签主体（verified_by / expert_verified_by），由主理人签署时保证。

### 2.2 release_precheck（G1-G6）
- 直接复用 `can_enable_engineering`，避免门禁逻辑分叉；所有外部条件缺省 False → 默认拒绝。
- 不修改配置、不输出 approved、不翻转 `engineering_enabled`。

### 2.3 Gray Release CLI（默认关闭）
- 子命令：`precheck`（声明 `--authorized` 仅查 G1-G5）/ `enable` / `disable` / `rollback` / `restore`。
- `enable` 强制前置：**启用前快照** + **授权存在且生效** + **G1-G6 全过**；任一缺失 → 退出码非 0，绝不翻转灰度开关。
- 仅操作 `GrayReleaseConfig`（per-interface 开关 + default_enabled），**绝不**触碰 `config.yaml` / `verified.json` / `engineering_enabled`。

### 2.4 Release Audit Log
- `release_audit.jsonl` 每次操作 append-only 记录六字段，仅标识符/引用，无真实工程数值。
- 拒绝路径同样落审计（rejected 标记），保证可追溯。

---

## 3. 测试覆盖（任务5 七点）

`tests/agents/test_release_execution.py` 共 25 用例，逐点映射任务要求：

1. **无 approval 拒绝 enable**：`enable_release(approval_id="APR-MISSING")` → `REJECTED_NO_APPROVAL`，配置文件不创建。
2. **G1 失败拒绝**：授权有效但 `thresholds=None`（加载真实 draft 签字库）→ G1/G2 阻塞 → `REJECTED_GATE_BLOCKED`。
3. **G6 失败拒绝**：授权 `effective_time` 在未来 → `is_approval_effective=False` → `REJECTED_NOT_EFFECTIVE`（授权未生效即 G6 未满足）；另含门禁层 `authorization_present=False` 单测。
4. **snapshot 缺失拒绝**：`snapshot_dir` 为已存在文件导致 `mkdir` 失败 → `REJECTED_SNAPSHOT_FAILED`。
5. **rollback 恢复**：接口级 `close_interface` → `restore` 从快照重放；全局熔断 `close_global` → `restore` 恢复；无快照 `restore` → `REJECTED_NO_SNAPSHOT`。
6. **audit 写入**：`disable` / `rollback` 后审计记录含六字段、append-only 计数递增、无真实数值。
7. **engineering_enabled=false 保护**：即便授权+G1-G6 全过，`enable` 仅翻灰度开关；`load_engineering_enabled()` 恒为 False，全局闸门未变。

附加覆盖：`_load_thresholds` 三种形态（list / Mapping(thresholds) / 缺失损坏）、CLI 退出码（precheck 阻断/授权绿通、enable 拒绝/成功、disable/rollback/restore 零码）、approval 追加/查找/仅标识符、快照失败分支（disable/rollback）。

---

## 4. CI 与扫描结果

- 运行：`bash scripts/ci/local_ci.sh` → **8/8 PASS**
  - [1/8] Ruff：全过
  - [2/8] 后端 pytest：**460 passed**（原 435 + 新增 25），Total coverage **89.52%**（≥ 89.21% 达标，89.21%→89.52% 微升）
  - [3/8] 前端 Lint / [4/8] 前端 Jest / [5/8] Alembic / [6/8] Seed：全绿
  - [7/8] 防编造扫描：零命中
  - [8/8] 硬编码扫描：零命中
- 防编造规则遵守：业务词仅以 `wind_pressure` / `E-TH` 标识符出现；阈值注入均用合成占位（value=None、source_ref 计算哈希占位、signer 标识符）；真实数值一律未生成。

---

## 5. 风险评估

### 5.1 技术风险
- RT-F1 脚本绕过授权：CLI `enable` 在写入前强制校验 快照+授权+G1-G6，全局门 `engineering_enabled=false` 下 `is_interface_gray_allowed` 恒 False，无法绕过。缓解：硬默认关闭 + 双重闸门。
- RT-F2 快照缺失导致无法回滚：`enable`/`disable`/`rollback` 写盘前均先快照；`restore` 无快照即拒绝。缓解：快照前置 + 拒绝无快照 restore。
- RT-F3 审核链被篡改：审计仅 append-only，不修改 `review_log` / `approved_monitor`；回滚只翻灰度开关。缓解：不可变日志。
- RT-F4 配置写坏：灰度配置原子写（`tmp` + `replace`），写前回解析校验。缓解：原子替换。

### 5.2 工程风险
- RE-F1 授权伪造：`find_approval_record` 仅按标识查找，未对审批文档做密码学校验；真实放行依赖主理人书面签署 + SoD。待办：可选对 `approval_document_ref` 做哈希绑定。
- RE-F2 范围漂移：`enable` 绑定 `interface`，授权须 `interface` 匹配否则拒绝；不支持跨接口复用授权。缓解：接口级强绑定。
- RE-F3 `effective_time` 倒填：未来时间视为未生效；倒填过去时间当前放行，依赖主理人诚信。待办：可接入签署时间戳外部背书。
- RE-F4 `rollback_owner` 缺失：授权记录强制 `rollback_owner` 字段，缺省写入被模型约束拒绝。缓解：必填。

### 5.3 法律责任风险
- RL-F1 责任链不清：每次操作落 `release_audit.jsonl`（operator / action / result），结合 `EngineeringReleaseApproval`（authorized_by / rollback_owner）形成责任链。缓解：端到端可追溯。
- RL-F2 未授权启用：CLI 默认关闭，未获授权 + G1-G6 全过绝不开关。缓解：硬前置。
- RL-F3 审计缺口：拒绝路径同样审计（rejected 标记），无静默失败。缓解：全量审计。
- RL-F4 跨阶段混淆：3.2.5 真实闭环须主理人单独书面授权，不可与 3.2.4 双签路径混同。缓解：独立 G6 证据。

---

## 6. 红线守约确认

- 未开启 `engineering_enabled`（仍 False）。
- 未输出 `engineering_approved`。
- 未修改生产 `verified.json`（仍 schema_version1 占位态）。
- 未真实灰度放量（脚本默认关闭，`enable` 被前置硬性拒绝）。
- 全部 `pending_verification`；所有写盘路径在测试中均为临时路径，未污染仓库默认文件。

---

## 7. SSOT / Roadmap 更新

- `project_status.json`：`task_status.phase_3_1.phase_3_2` 新增 `"3.2.5-F"`（`_phase_status=SPRINT_3_2_5F_DONE`），并刷新 `_readiness_report` / `_summary` / `_blocking_for_code`。
- `roadmap_v2.md`：第 92 行 3.2 里程碑追加 `Sprint 3.2.5-F DONE`。

---

## 8. 开放决策与下一步

- 开放项：
  1. 真实放行须主理人书面签署 `EngineeringReleaseApproval`（G6，SoD 独立于 3.2.4 双签主体）并指定 `rollback_owner` —— 待主理人定。
  2. E-TH-01 至 E-TH-03 真实化（满足 G1/G2/G4 + 真实 review_log 链）—— 待人工真实数据调用。
  3. 首个真实放量范围（建议仅 `wind_pressure`）与 `rollout_pct` 初始比例 —— 待授权时填。
- 下一步：等待主理人书面签署 `EngineeringReleaseApproval`（G6）→ 人工真实化 E-TH-01 至 E-TH-03（满足 G1/G2/G4）→ 重跑 local_ci 确认 G3 绿 → 发布执行人依 `gray_release_ctl.py enable wind_pressure`（自动校验 快照+授权+G1-G6）置 `engineering_enabled=true` 并触发 Monitor 落盘 → 进入 per-interface 灰度放量（仅 `wind_pressure`）。

**本阶段已停止，未开启 engineering_enabled。**
