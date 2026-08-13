# Phase 3.9.4-R1 最终证据一致性与质量基线收口报告

> 阶段定位：Phase 3.9.4「生产遥测接入适配与合成运维验证层」的**证据质量收口层**（非功能新增）。
> 身份：BOIP AI Chief Architect + Release Evidence Auditor + Repository Integrity Lead + Quality Baseline Owner + 本阶段自主研发负责人。
> 收口目标：把 3.9.4 已交付内容整理为「事实唯一、测试全绿、Git 清晰、SSOT 一致、报告无矛盾」的可审核基线。

---

## 1. 授权范围与边界

本阶段**不新增功能**、**不接入生产**、**不真发告警**、**不自动回滚/ACK/RESOLVE/CLOSE**、**不代替人肉责任**、**不修改 `engineering_enabled`**。
仅做：证据一致性核对、测试基线修复、Git 历史对账、SSOT 对齐、报告重建、质量校验器落地。

## 2. 身份与权限边界

- 可写：测试修复、溯源台账、校验器脚本、报告与 SSOT 文本更正、阶段收口文档。
- 不可写：生产代码部署、真实凭据、外部告警、任何会翻转 `engineering_enabled=false` 的逻辑。
- 所有审计记录/签署强制 `USER` 主体；AI 主体一律 403（既有治理代码保证）。

## 3. 四大已知问题回顾（收口前）

- **问题 A**：backend 基线 `test_jwt_verifier_config_missing_secret_fails_closed` 历史失败 1 例。
- **问题 B**：`AuditActionCategory` 溯源叙事混乱（曾被写 "83→88(+5)→95(+7)→96(+1)→100(+4)"）。
- **问题 C**：Git commit 数量不一致（报告称 8、列出 9 hash、实际含 T0 共 10）。
- **问题 D**：3.9.2 `production_release/*` 等遗留未跟踪/未提交资产长期停留工作树。

## 4. 红线遵守总览（12 条，全遵守）

未开启 `engineering_enabled`；未输出 `engineering_approved`；未自动评级/确认/禁用/弃用/修改/生成 Agent 或真实工程参数；未真部署/改生产数据/写密钥/真外发告警；未自动 ACK-RESOLVE-CLOSE；未自动 Runbook；未 AI 代真人责任；未为绿删安全断言；未用 skip/xfail/ignore 掩盖；未伪造数字；未机械删除历史资产清工作树。

## 5. 执行纪律

- 创建分支 `fix/phase3.9.4-final-evidence-quality-closure`（基座 commit `e0cae50`）。
- 禁止 `git reset --hard`；提交一律**精确路径**，禁止 `git add -A`。
- 实际集成拓扑演变见 §18。

## 6. R1（问题 A）：JWT 缺失-secret fail-closed 根因与修复

**根因（实证）**：测试 `test_jwt_verifier_config_missing_secret_fails_closed` 仅 monkeypatch
`app.core.config.get_settings`，但 `decode_access_token` → `_get_jwt_secret` 实际通过
`security.py` 顶层的 `from app.core.config import get_settings` 绑定引用 `app.core.security.get_settings`。
monkeypatch 只改写 config 模块属性，改不到 security 模块已绑定的同名引用，故真实 secret 仍被读到、
token 验签通过，使"缺失 secret 必须 fail-closed"这一关键断言**从未真正执行**（历史误报为通过 / 实际
`DID NOT RAISE`）。产品代码本身是 fail-closed 正确的（`_get_jwt_secret` 在 `jwt_secret` 为空时抛
`AuthConfigError`），问题纯粹在测试桩命名空间不匹配。

**修复（红线合规：未删测试、未降 fail-closed、未 skip）**：同时 patch 两个命名空间
`app.core.config.get_settings` 与 `app.core.security.get_settings`。该修复已由 3.9.5 线 commit
`e7952e9 test(security): strengthen JWT missing-secret fail-closed coverage (T13)` 落地，与本研究独立推导的
双命名空间修正**逐字一致**。复跑 ≥2 次稳定通过，backend 全量回归 0 failed。

## 7. R2/R3（问题 B）：AuditActionCategory 溯源台账（Git 实证）

以 Git 为唯一事实源，逐阶段边界 commit 提取 `AuditActionCategory` 成员实计数：

| 阶段 | 边界 commit | 累计 | 增量 | 新增成员（实名单） |
|------|-------------|------|------|--------------------|
| 3.8.27 | `4aa23fb` | 69 | 基线 | （历史确立） |
| 3.8.30 | `382afd4` | 72 | +3 | GOVERNANCE_REPLAY/TIMELINE/TRACE |
| 3.9.0 | `a538e1e` | 75 | +3 | DEPLOYMENT_MANIFEST/PRODUCTION_READINESS_CHECK/ROLLBACK_PLAN |
| 3.9.1 | `66f9b57` | 79 | +4 | DEPLOYMENT_SIMULATION/RECOVERY_VALIDATION/ROLLBACK_DRILL/STAGING_VALIDATION |
| 3.9.2 | `ea57245` | 83 | +4 | RELEASE_CANDIDATE_CREATED/GATE_EVALUATED/MANIFEST_GENERATED/SIGNOFF_RECORDED |
| 3.9.3 | `8c7c9c5` | 96 | **+13** | ACTIVATION_EVIDENCE_BUNDLE_GENERATED/ALERT_CANDIDATE_CREATED/CONTROLLED_ACTIVATION_GATE_EVALUATED/HUMAN_ACTIVATION_APPROVAL_RECORDED/INCIDENT_CREATED/HUMAN_ACKNOWLEDGED/HUMAN_CLOSED/HUMAN_RESOLVED/OBSERVABILITY_HEALTH_CHECK/POSTMORTEM_DRAFT_CREATED/RC_FREEZE_CHECK_PASSED/GENERATED/VERIFIED |
| 3.9.4 | `6ddb9a3` | 100 | +4 | SYNTHETIC_DRILL_COMPLETED/STARTED/TELEMETRY_EVIDENCE_RECORDED/TELEMETRY_PROVIDER_CHECKED |

**纠正旧叙事**："83→88(+5)→95(+7)→96(+1)→100(+4)" 全部不成立。真实增量链 +3/+3/+4/+4/**+13**/+4，
终点 **100**，与基线 `audit_category_contract.total=100` 一致。所有 100 成员均可归因于已登记阶段，无 orphan/ghost。
权威台账：`.ai/AUDIT_ACTION_CATEGORY_LEDGER.md`。

## 8. R4：Audit 测试契约稳定化 + Validator

- 总数断言唯一守护者仍为 `tests/agents/test_enterprise_knowledge_governance_audit.py`（`assert len(members)==100`），
  完整性检查器规则 4 禁止其他文件硬编码总数。
- 新增 `scripts/audit_category_ledger_validator.py`：实导入枚举断言总数==100，并核对 `union(各阶段集合)==实际成员`，
  检测 orphan（无归属）/ ghost（幽灵）。**R2 进一步将其重构为读取机器可读 JSON Ledger**
  （`.ai/baselines/audit_action_category_ledger.json`，由 `scripts/build_audit_category_ledger.py` 从 Git 真实边界
  commit 重建），并新增 0 duplicate-ownership、每阶段 commit 存在、从 commit 实际提取 introduced==ledger 共 **7 项**
  fail-closed 校验（详见 Phase 3.9.4-R2 收口报告 §7）。CI 可挂接。实跑通过：total=100，0 orphan / 0 ghost / 0 dup。

## 9. R5（问题 D）：3.9.2 遗留资产归属

3.9.2 `production_release/*` 等遗留未提交资产已由 **Phase 3.9.5 发布线对账**收口并提交于
`feat/phase3.9.5-release-line-reconciliation`，关键 commit：
`e0cae50`(RC freeze core) / `d82cade`(controlled activation gate) / `e7952e9`(JWT fix) /
`49c8c63`(CI release gate + rollback runbook) / `833ee8d`(3.9.5 closure) / `4983e7b`(RC freeze closure report)。
原本因工作树 WIP 未完成而失败的 6 项 `production_release` 测试（SHA256 manifest 返回 `<missing>`）在 WIP 提交后
**转绿（50 passed）**。资产现已**归属明确、已提交、不再"来源不明"**。

## 10. R6（问题 C）：Git 历史对账

- **3.9.4 逻辑提交 = 10**（Git 实据 `git rev-list --count 9201a7d^..a905213` = 10）：
  `9201a7d`(T0) / `b3a6e7b`(T1–18) / `6ddb9a3`(T21) / `d836e33`(T19) / `b893316`(T20) /
  `64b900d`(T10–12,T22–24) / `6a438fd`(T25) / `8de1e39`(T27–28) / `121de8d`(T26) / `a905213`(T30)。
- 原报告误写 "8 commit" 并漏列 `a905213`，已更正（见 §13）。
- 3.9.5 对账提交链（6 个）独立于 3.9.4，见 §9。

## 11. R7：仓库清洁度

工作树无"来源不明"资产。本阶段交付物（台账、校验器、报告更正）已随 R2 提交于
`feat/phase3.9.4-r2-definitive-baseline-freeze`（见 §21 / R2 收口报告 commit 清单）；临时取证脚本已清理。

## 12. R8：SSOT 一致性对齐

- 基线 `audit_category_contract.total=100` 与 `project_status.json` `audit_total:100` 一致；完整性检查器规则 5 通过。
- 更正 `project_status.json` `phase_3_9_2.audit_delta_this_layer` 中 `HUMAN_ACTIVATION_APPROVAL_RECORDED`
  的误归属：该成员由 **3.9.3** commit `8c7c9c5` 引入，非 3.9.4 T0（`9201a7d` 仅做溯源契约归属修正，不新增枚举）。
  同步更正 3.9.2 `audit_delta_this_layer` 为 +4（RELEASE_* 由 `ea57245` 引入，79→83）。

## 13. R9：重建 Phase 3.9.4 收口报告（修正）

`.ai/reviews/phase3.9.4_telemetry_synthetic_operations_report.md` 已更正：
- 逻辑提交清单（§24）补列 `a905213`（T30），共 **10** 行 hash；
- T29 行 "8 commit" → "10 commit（含 T0 与 T30）"；
- 收口声明（§36）"8 个逻辑提交" → "10 个逻辑提交"，并澄清 backend 计数为阶段新增 374 / 全量 2748。

## 14. R10：全量回归测试矩阵

| 套件 | 命令（实测 CWD / 解释） | 结果 |
|------|------|------|
| backend 全量（FastAPI） | `backend/.venv/bin/python -m pytest backend/tests -q`（仓库根执行） | **374 passed, 0 failed** |
| agents 全量 | `backend/.venv/bin/python -m pytest tests/agents -q`（仓库根执行；JWT 修复后复跑 2 次稳定） | **2373 passed, 0 failed** |
| frontend jest | `node node_modules/.bin/jest --config frontend/jest.config.js`（BOIP 根；用 BOIP 自身提升的 node_modules，勿加 NODE_PATH 覆盖） | **117 passed, 7 suites** |
| frontend tsc | `npx tsc --noEmit`（frontend/） | **0 error** |
| 治理完整性 | `check_governance_repository_integrity.py` | 9/9 ✓ |
| 生产安全 lint | `check_production_security.py` | 7/7 ✓ |
| 硬编码扫描 | `check_hardcoded.py` | 0 命中 ✓ |
| fabrication 扫描 | `check_fabrication.py` | 仅历史 wind_pressure 测试夹具命中（非本阶段） |
| 遗留身份头扫描 | `check_legacy_identity_headers.py --root .` | OK ✓ |
| Audit 溯源校验 | `audit_category_ledger_validator.py` | total=100，无 orphan/ghost ✓ |

## 15. 静态门禁汇总

完整性 9/9、生产安全 7/7、硬编码 0、遗留身份头 OK、Audit 校验 PASS。fabrication 仅历史 `风压/WindPressure`
测试夹具命中（既有，非 3.9.4 引入），不阻塞收口。

## 16. 激活态确认

`engineering_enabled=false`（`agents/config.yaml:102`，未改）；无 `engineering_approved` 输出；
ESW 窗口维持 OPEN_EMPTY，等待主理人 + 专家线下提交真实证据后由人肉终端显式置 enabled=true。

## 17. 遗留 / 已知项

- fabrication 扫描的历史 `风压` 测试夹具来源标注，建议后续单独 hygiene（非本阶段范围）。
- 3.9.2 RC-freeze / controlled-activation 资产已转 3.9.5 线，其阶段归属以 `feat/phase3.9.5-*` 为准。

## 18. 分支拓扑说明

- R1 意图分支为 `fix/phase3.9.4-final-evidence-quality-closure`（基座 `e0cae50`），但实际提交落点见下。
- 环境在收口过程中将 3.9.2 遗留收口落在 `feat/phase3.9.5-release-line-reconciliation`（HEAD `4983e7b`），
  该线以 `e0cae50` 为基座并叠加 3.9.2 RC 冻结/激活闸门对账与 JWT 修复（`e7952e9`）。
- 本阶段（R1）证据质量交付物（台账/校验器/报告更正/SSOT 更正）与其 CWD 修复，最终于 **Phase 3.9.4-R2**
  提交于 `feat/phase3.9.4-r2-definitive-baseline-freeze`（自 3.9.5 HEAD `4983e7b` 分出），commit：
  `3043eb4`(CWD fix) / `e709176`(Audit JSON Ledger + build/validator) / `ab1f7cd`(SSOT/doc 更正)；
  R2 其余交付物（阶段边界台账、CI 三道门禁、R2 报告）随后追加。分支演化已如实记录，未做 `reset --hard`、未做 `git add -A`。

## 19. 收口条件核对

- [x] agents / backend / frontend / tsc 全绿（见 §14）
- [x] telemetry / synthetic E2E 校验（既有 3.9.4 测试 + 校验器）
- [x] 治理完整性 9/9、生产安全 7/7
- [x] Audit 溯源完全解释（台账 + 校验器）
- [x] 3.9.2 遗留已归属/提交（3.9.5 线）
- [x] Git 数量无矛盾（10 个 3.9.4 提交，清单完整）
- [x] SSOT 全一致（total=100，误归属已更正）
- [x] 工作树无来源不明资产
- [x] `engineering_enabled=false`

## 20. 停止条件（STOP）

满足全部收口条件。本阶段 STOP：**不进入 Phase 3.9.5 新功能**、不真接入生产、不真发告警、不自动回滚/ACK/
RESOLVE/CLOSE、不自动开启 `engineering_enabled`、不输出 `engineering_approved`。待主理人线下审核授权后，
按既定路径推进真实接入与激活。

## 21. 签署与交付物清单

交付物（已提交于 `feat/phase3.9.4-r2-definitive-baseline-freeze`）：
- `.ai/AUDIT_ACTION_CATEGORY_LEDGER.md`（R3 权威溯源台账，R2 由 JSON 渲染）
- `.ai/baselines/audit_action_category_ledger.json`（R2 机器可读 SSOT，由 `build_audit_category_ledger.py` 从 Git 重建）
- `scripts/audit_category_ledger_validator.py`（R4 校验器，R2 重构为读 JSON、7 项校验）
- `scripts/build_audit_category_ledger.py`（R2 新增，Git → JSON Ledger 构建器）
- `.ai/reviews/phase3.9.4_telemetry_synthetic_operations_report.md`（R9 更正）
- `.ai/project_status.json`（R8 SSOT 更正）
- 本报告 `.ai/reviews/phase3.9.4_r1_final_evidence_quality_closure_report.md`

问题 A 修复 commit：`e7952e9`（位于 3.9.5 线）。
问题 B/C/D 解决见 §7/§10/§9。

**问题 D 收口补遗（CWD 失败修复，已提交 `3043eb4`）**：
`test_production_release_gate_evidence.py` 中 `_ROOT = os.path.abspath(".")` 改为 `_ROOT = str(REPO_ROOT)`
（`REPO_ROOT = Path(__file__).resolve().parents[2]`），使测试自读 `forbidden.py` 计算预期 SHA-256 的步骤与 CWD 无关。
配合 `ProductionReleaseService(root_dir=...)` → `_evidence_svc` / `_package_builder` 链路（`service.py` 新增 `root_dir` 形参并透传），
从 `backend/` CWD 复跑由 1 failed → **50 passed**。已提交路径：
- `agents/enterprise/production_release/service.py`
- `tests/agents/test_enterprise_production_release.py`
- `tests/agents/test_production_release_gate_evidence.py`

— 阶段负责人（BOIP AI Chief Architect + Release Evidence Auditor + Repository Integrity Lead + Quality Baseline Owner + 本阶段自主研发负责人）· 2026-08-13
