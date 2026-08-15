# Phase 3.9.13 — Starting Baseline Validation（起始基线校验）

- **生成时间**：2026-08-15
- **校验人**：BOIP Autonomous Engineering Lead（fail-closed 治理纪律）
- **目的**：在进入 Phase 3.9.13「External Staging Provisioning Execution & Resource Registration」任何写操作前，以真实 Git 为唯一事实源核验 3.9.12 合法收口态，作为本阶段 base commit 与 SSOT 锚点。

## 一、分支完整性（Branch Integrity Guard）

| 项 | 期望值 | 实测 | 结论 |
| --- | --- | --- | --- |
| 3.9.12 final branch | `feat/phase3.9.12-external-staging-provisioning-operator-readiness` | 同左 | ✅ |
| 3.9.12 final HEAD | `82657acdaeda30aefc38d8af9b1863aa54cddd14` | `82657acdaeda30aefc38d8af9b1863aa54cddd14` | ✅ |
| 工作树 clean（`--porcelain`） | 空 | 空 | ✅ |
| 工作树 clean（`--untracked-files=all`） | 空 | 空 | ✅ |
| 沙箱漂移检测 | 无 | 检出：会话启动时曾被静默 reset 至 `feat/phase3.9.10-production-remediation-engineering@cb61858`，已 `git checkout -f` 恢复至 3.9.12 tip | ⚠️ 已纠正 |

## 二、Operator Package（确定性算子包，3.9.12 交付）

| 项 | 值 |
| --- | --- |
| 路径 | `.ai/staging/external_staging_provisioning_operator_package.json` |
| package_hash | `65cc30600c8086d2417244a4c16efd8b2338af1b936538713898cf90de756e01` |
| contains_real_secret | `false` |
| production_activation_prohibited | `true` |
| any_real_provisioning | `false` |
| 默认 Provider | `tencentcloud`（provider-agnostic OpenTofu） |

> 本阶段（3.9.13）的 Execution Package 必须复用同一确定性哈希范式（`_canonical_json` + SHA-256），且 `contains_real_secret=false` / `production_activation_prohibited=true` 不得被改写。

## 三、Provider ADR

- **ADR-001（LLM Provider 统一决策）**：仅确立配置/文档单一事实源，不修改 `agents/` 运行时代码；与真实 External Staging 供给无关。
- **供给 Provider 决策**：provider-agnostic OpenTofu 模板，默认首选 `tencentcloud`（记录于 `agents/external_staging_provisioning/bom.py::_PROVIDER_SERVICE`）。真实账号/密钥为 Track B 真人输入，统一 `pending_external_staging_resource`。

## 四、IaC ADR（infrastructure/staging/）

| 文件 | 角色 | 备注 |
| --- | --- | --- |
| `main.tf` / `versions.tf` / `variables.tf` / `network.tf` | 骨架 | provider-agnostic |
| `database.tf` / `object_storage.tf` / `secret_provider.tf` / `deployment_target.tf` | **count=0 skeleton** | 按 §八 判定为 intentional skeleton（占位，待真实资源） |
| `identity_provider.tf` / `telemetry.tf` / `alert_sandbox.tf` / `domain_tls.tf` | 资源模板 | 含占位变量 |
| `README.md` | 说明 | — |

> §八 IaC Executable Readiness 审计将逐模块判定：intentional skeleton / disabled / incomplete / missing / placeholder，fail-closed。

## 五、8 Resource BOM（全部 PENDING）

源：`.ai/staging/external_staging_resource_bom.json` + `agents/external_staging_provisioning/bom.py`

| # | resource_id | type | owner_role | iac_module | status |
| --- | --- | --- | --- | --- | --- |
| 1 | ext-staging-database | DATABASE | production-owner | database.tf | pending_external_staging_resource |
| 2 | ext-staging-secret_provider | SECRET_PROVIDER | security-owner | secret_provider.tf | pending_external_staging_resource |
| 3 | ext-staging-identity_provider | IDENTITY_PROVIDER | security-owner | identity_provider.tf | pending_external_staging_resource |
| 4 | ext-staging-object_storage | OBJECT_STORAGE | production-owner | object_storage.tf | pending_external_staging_resource |
| 5 | ext-staging-telemetry | TELEMETRY | release-manager | telemetry.tf | pending_external_staging_resource |
| 6 | ext-staging-alert_sandbox | ALERT_SANDBOX | release-manager | alert_sandbox.tf | pending_external_staging_resource |
| 7 | ext-staging-domain_tls | DOMAIN_TLS | production-owner | domain_tls.tf | pending_external_staging_resource |
| 8 | ext-staging-deployment_target | DEPLOYMENT_TARGET | production-owner | deployment_target.tf | pending_external_staging_resource |

**结论**：8/8 PENDING（0 配置 / 0 供给 / 0 注册 / 0 连通 / 0 隔离 / 0 合格）。真实资源未提供前，本阶段绝不伪造 8/8。

## 六、Gate 状态（不变量）

- **Operator Gate（3.9.12，独立 3 态）**：`BLOCKED` / `PENDING_HUMAN_INPUT` / `READY_FOR_HUMAN_PROVISIONING_REVIEW`（禁 GO/APPROVED/PRODUCTION_READY）。
- **Execution Gate（3.9.11，4 态）**：`BLOCKED` / `PENDING_EXTERNAL_STAGING_RESOURCE` / `PENDING_HUMAN_VERIFICATION` / `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`。
- **3.9.13 Apply Gate（新增，双钥匙）**：状态 `BLOCKED` / `PLAN_ONLY` / `PENDING_HUMAN_AUTHORIZATION` / `AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY`（禁 GO/APPROVED/PRODUCTION_READY）。缺 Machine Safety Key 或 Human Authorization Key 任一 → 禁止 apply。

## 七、审计账本

- 账本文件：`.ai/baselines/audit_action_category_ledger.json`
- total = **129**（last released baseline 3.9.8 冻结；3.9.9→3.9.12 增量已在历史基线中，本阶段 audit 自包含、机械 fold-in 禁止，仍维持 129 基线）
- 校验脚本：`scripts/audit_category_ledger_validator.py`

## 八、engineering_enabled 红线

- `agents/config.yaml:102` → `engineering_enabled: false`
- `agents/config_loader.py:135` → `def load_engineering_enabled(...)`（测试用 monkeypatch 返回 False，不碰磁盘）
- **本阶段全程保持 `false`**；任何写操作不得打开。

## 九、Production Handoff 隔离

- 旧 WIP「Production Handoff & Human Activation Ceremony」隔离于 `foreign/phase3.9.12-isolation-deployment-remediation`（commit `7c388f9`）。
- 不吸收、不删除、不重写；3.9.13 不进入 Production Handoff。

## 十、Phase 3.9.13 Canonical 锚点

| 项 | 值 |
| --- | --- |
| canonical phase id | `phase_3_9_13_external_staging_provisioning_execution` |
| expected branch | `feat/phase3.9.13-external-staging-provisioning-execution-registration` |
| base commit | `82657acdaeda30aefc38d8af9b1863aa54cddd14` |
| start commit（本 baseline 文档 commit） | 见本分支首个 chore commit |
| 开发中 SSOT key | `phase_3_9_13_status`（status=`WIP_BUILT_NO_GO`） |
| 终态 | `EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO` |
| 真实资源目标 | 0/8 → 渐进；**禁止伪造 8/8**（无真实凭据/授权时维持 0/8 Pending） |
| STOP 纪律 | 收口后 STOP，不进 3.9.14、禁 Production 动作 |

## 十一、基线校验结论

✅ 3.9.12 合法收口态全部核验通过；工作树 clean；Operator Package 安全标志正确；8 资源全 PENDING；审计 129 冻结；`engineering_enabled=false` 守约；Production Handoff 已隔离。

➡️ **允许进入 3.9.13 主体工程**：从 base commit `82657ac` 起，按 T0–T53 渐进构建「Provisioning Execution & Resource Registration」框架，双钥匙 Apply Gate + 逐资源状态机 + 递归凭据深扫 + IaC 就绪审计 + Partial Progress Aggregator（0/8），真实资源保持 Pending，不伪造。
