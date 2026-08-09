# Sprint 3.2.5-B 工程灰度发布基础设施实现报告

**身份**：BOIP AI 工程治理架构负责人
**性质**：灰度发布基础能力落地（Gray Release Infrastructure）——**非开启 `engineering_enabled`、非填真实阈值、非输出真实 `engineering_approved`**，全部 `pending_verification`。
**完成时间**：2026-07-31

---

## 1. 修改文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `agents/engineering/gate/__init__.py` | 新增 | 导出 `can_enable_engineering` 与六项门禁常量 G1~G6 |
| `agents/engineering/gate/enable_gate.py` | 新增 | `can_enable_engineering()` 六项门禁判定，默认拒绝 |
| `agents/engineering/gray_release.py` | 新增 | `GrayReleaseEntry` / `GrayReleaseConfig` schema + `load_gray_release_config` / `is_interface_gray_allowed` |
| `agents/engineering/approved_monitor.py` | 新增 | `ApprovedRecord` + `append_approved_record` / `load_approved_records`（append-only） |
| `agents/engineering/rollback.py` | 新增 | `RollbackHandler`：接口级关闭 / 全局熔断 / snapshot / restore |
| `tests/agents/test_gray_release.py` | 新增 | 14 用例，覆盖任务 7 要点 + 门禁正向分支 |

**零既有代码改动**：`threshold_loader.py` / `validation.py` / `review_log.py` / `config_loader.py` 调用方式零破坏，仅新增独立模块。

---

## 2. 架构影响

新增"灰度发布基础设施"层，作为 `engineering_enabled` 全局闸门之上的 per-interface 收窄层：

- **Enable Gate（`gate/`）**：`can_enable_engineering()` 是"是否**允许**开启 `engineering_enabled`"的纯判定函数，检查 G1 阈值治理 / G2 双签 / G3 CI / G4 审核链 / G5 回滚就绪 / G6 主理人书面授权；**所有外部条件默认不满足 → 默认返回 `(False, reasons)`**，绝不自行翻转开关、绝不输出 `approved`。
- **Gray Release（`gray_release.py`）**：per-interface 白名单（interface / enabled / allowed_project_tags / rollout_pct，默认 `enabled=false`）。`is_interface_gray_allowed` **双重保险**——全局 `orchestrator.engineering_enabled=false` 时恒 `False`（禁止绕过全局闸门）。
- **Approved Monitor（`approved_monitor.py`）**：每次 approved 写 `approved_monitor.jsonl`（append-only），字段仅引用/标识符（schema_version / interface / threshold_version / sign_off_id / review_log_ref / error / timestamp），**绝不记录真实工程数值**。
- **Rollback（`rollback.py`）**：接口级关闭 + 全局熔断 + `snapshot`/`restore`；仅翻转灰度配置开关，**不修改任何历史 `review_log`**，恢复语义为结果回落 `pending_verification`。

依赖关系：gate → `threshold_loader.governance_status` / `is_fully_verified` + `review_log.read_log`；gray_release → `config_loader.load_engineering_enabled`；rollback → `gray_release.GrayReleaseConfig`。全部复用既有只读 API，无新写入点。

---

## 3. 测试结果

`bash scripts/ci/local_ci.sh` → **8/8 PASS**

- **Backend：402 passed @ 88.75%**（≥88.57% 达标；较 3.2.4-A 基线 388→402 净增 14 用例，覆盖率 88.57%→88.75% 微升）
- Frontend：29 passed @ 93.15%
- Alembic 双向 upgrade/downgrade 通过；Seed 通过
- **防编造扫描 0 命中；硬编码扫描 0 命中**

`tests/agents/test_gray_release.py` 14 用例覆盖：
1. gate 默认拒绝（`can_enable_engineering()` 无注入 → `(False, reasons)`）
2. missing verified 拒绝（G1 + G2 阻塞）
3. enabled=false 保护（全局 false 时灰度恒 False）
4. gray allowlist（标签命中放行 / 未命中 / 缺标签 / rollout_pct=0 拒绝）
5. monitor 写入（append + 回放 + 仅引用字段 + 损坏行跳过）
6. rollback 恢复 pending（接口级关闭 / 全局熔断 / 自动快照 restore）
7. 不可绕过 engineering_enabled（门禁允许 ≠ 激活；全局 false 恒拒绝；条目未启也拒绝）
8. 门禁正向分支（G1~G6 全绿内存注入 → `(True, [])`，逻辑验证不真实激活）
9. 审核链断裂 → G4 阻塞

---

## 4. 风险

- **未真实激活**：本基础设施为"能力就绪"层；真实开启须先 Sprint 3.2.4 实施（`verified.json` 真实化 + 真实双签）+ 主理人书面授权（G6），再 Sprint 3.2.5 实施（`engineering_enabled` 开启灰度，须授权）。当前 G1/G2/G6 门禁未满足，默认拒绝。
- **配置落盘未提交真实值**：`gray_release.json` / `approved_monitor.jsonl` 为运行时生成物；本阶段未写入任何真实工程数值、未修改 `verified.json`。
- **监控落点开放项（沿用 3.2.5-A）**：`approved_monitor.jsonl` 独立专表 vs 复用 `review_log action=engineering_approved`，待主理人定夺。
- **回滚不变量**：`rollback` 仅翻转灰度开关，不触碰 `review_log`（append-only 不可篡改）；"恢复 pending_verification" 指相关接口不再被放行、结果回落 pending，不重写已落盘审核记录。

---

## 5. 安全检查（红线守约）

| 红线 | 状态 |
|---|---|
| ① 未开启 `engineering_enabled=true` | ✅ 仍 false（`config_loader.load_engineering_enabled()` 默认 False，门禁不翻转） |
| ② 未修改 `verified.json` 真实 value | ✅ 全部 `pending_verification`，仅内存夹具验证逻辑分支 |
| ③ 未设置 `verified=true` | ✅ 真实文件全 false；测试中双签仅内存构造不落盘 |
| ④ 未输出真实 `engineering_approved` | ✅ 仅 `can_enable_engineering` 正向分支逻辑验证，不落盘、不改 config |
| ⑤ 未填真实专家姓名 / 规范数值 | ✅ signer 仅 `principal-001`/`expert-001` 标识符；阈值仅以 E-TH/D-TH 标识符引用，值仍 null |
| ⑥ 防编造 / 硬编码扫描 | ✅ 0 命中（测试初版 5 处 `wind_pressure`+数字共现，已补 `pending_verification` 标记，复扫 0 命中） |

**结论**：灰度发布基础设施已落地且 CI 8/8 全绿，红线全程守约。**未进入 3.2.4 实施（verified.json 真实化）/ 未进入 3.2.5 实施（enabled 开启灰度）**——二者须单独书面授权，不可与 A/B 系列混同。
