# Phase 3.9.12 — Infrastructure & Code Reuse Analysis (T2)

> 生成时间：2026-08-15
> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 目的：明确「复用既有（不重造第二套）」与「本阶段新增」的边界，落实治理复用纪律。

---

## 0. 复用纪律（最高优先）

1. **枚举不手抄**：`ResourceType` 8 类成员一律从 `EnumClass.__members__` 程序化派生。
2. **状态机不重造**：`GateStatus` / `ResourceQualificationStatus` 的状态常量直接复用，不新定义等价枚举（除非本阶段 3 态 Operator Gate 确需独立枚举——见 §2.3）。
3. **范式复用**：确定性哈希、契约测试、凭据扫描、闸门评估、身份加载等范式 100% 复用既有实现。
4. **禁伪造**：任何真实执行/验证态一律回落 PENDING，复用 `_FORBIDDEN_STATES` / `_FORBIDDEN_STEP_STATES` 断言。

---

## 1. 复用清单（来自 3.9.10 qualification + 3.9.11 execution）

| # | 既有资产（精确路径/符号） | 3.9.12 复用位置 | 复用方式 |
|---|---|---|---|
| R1 | `agents/external_staging_qualification/models.py` :: `ResourceType`（8 类）、`RESOURCE_TYPE_ORDER` | T5 BOM、T7-T15 八资源计划、T17 IaC 变量命名 | **直接导入**，枚举成员程序化派生 |
| R2 | `...models.py` :: `ExternalStagingResource` / `ExternalStagingResourceRegistry` / `build_default()` | T5 资源登记表、T20 人工输入表字段 | 复用数据结构 |
| R3 | `...models.py` :: `ResourceQualificationStatus`（含 `is_verified`/`is_pending`）、`_FORBIDDEN_STATES` | T19 Validator、T18 Dry-run Guard | 复用状态语义与禁态断言 |
| R4 | `...models.py` :: `GateStatus`（4 态：BLOCKED / PENDING_EXTERNAL_STAGING_RESOURCE / PENDING_HUMAN_VERIFICATION / READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW） | 参考范式（3.9.12 用独立 3 态枚举，见 §2.3） | 范式参考，不混用 |
| R5 | `...models.py` :: `CredentialReference`（仅引用，无明文）、`ExternalStagingEnvironmentIdentity`（production=False） | T8 Secret 管理计划、T17 IaC 输出、T24 Operator Package | 复用引用模型 |
| R6 | `...credential_scanner.py` :: `assert_no_credential_leak` / `scan_mapping` / `CredentialLeakError` | T17 IaC 模板扫描、T19 Validator、T27 Package Validator、CI credential-safety | **直接复用**，fail-closed |
| R7 | `...config.py` :: `load_external_staging_identity` / `fingerprint_collision_with_production` | T4 目标架构、T17 IaC 环境指纹、T19 校验 | 复用身份加载 |
| R8 | `...gate.py` :: `GateCheck` / `GateResult` | T18 Dry-run Guard、T19 Validator、T23 Operator Gate | 复用评估原语 |
| R9 | `agents/external_staging_execution/models.py` :: `ExecutionStepKind` / `ExecutionStepStatus` / `ExecutionPlan` / `build_default_execution_plan` / `assert_not_forbidden_step_state` | T17 IaC plan 结构、T21 Provisioning Runbook 步骤模型 | 复用计划模型 |
| R10 | `agents/external_staging_execution/adapters.py` :: `AdapterProbeResult` / `ExternalStagingExecutionAdapter` / `probe_all` / `adapters_contract_test_all_pass` / `assert_no_real_execution_claimed` | T18 Dry-run Guard（契约测试范式）、T19 各资源 provisioning 探测 | **范式复用**：诚实 PENDING + 契约自洽 |
| R11 | `agents/external_staging_execution/gate.py` :: `ExternalStagingExecutionGate.evaluate()`（block/pending/info 分级裁决） | T23 Operator Gate 评估器 | 复用分级裁决逻辑 |
| R12 | `agents/external_staging_execution/evidence.py` :: `ExecutionEvidenceChain`（`chain_hash()`） | T24 Operator Package 证据链 | 直接复用 |
| R13 | `agents/external_staging_execution/package.py` :: `build_execution_package` / `package_hash` / `_canonical_json` / `_strip_non_fact` | T25 Operator Readiness Package（确定性 SHA-256） | **直接复用**确定性哈希算法 |
| R14 | `agents/external_staging_execution/security.py` :: `ExternalStagingExecutionSecurityValidator` | T28 API 写端点动作默认拒绝 | 复用安全校验 |
| R15 | `backend/app/api/external_staging_execution.py`（7 只读路由 + human-record POST 范式） | T28 新增 provisioning 只读路由 + human-input POST | 复用路由结构与红线约定 |
| R16 | `scripts/validate_external_staging_execution_package.py`（phase/terminal_state/secret/engineering_enabled/gate/pending_resources 断言 + 重算 hash） | T27 `validate_external_staging_operator_readiness_package.py` | **范式复用**校验脚本 |
| R17 | `.github/workflows/external-staging-execution-qualification-gate.yml`（8 jobs 结构） | T33 `external-staging-provisioning-readiness-gate.yml` | **复制结构**，改 phase/审计计数/分支/新 job |
| R18 | `agents/staging_runtime/environment.py` :: `RuntimeEnvironment.EXTERNAL_STAGING` | T4/T17 环境常量 | 复用环境标识 |
| R19 | `agents/config_loader.load_engineering_enabled()` | 全阶段红线读取 | 复用 |

---

## 2. 本阶段新增（不重造既有，但范畴全新）

### 2.1 全新文件/模块（T17、T19、T25、T27、T28、T33）
- `infrastructure/staging/**`：IaC 模板（Terraform/OpenTofu/Pulumi/CLI/Compose 之一或组合）—— **仓库首次引入 IaC 资产**。
- `agents/external_staging_provisioning/`：**新包**（Track A 必须完成部分），含：
  - `models.py`：`ProvisioningStepStatus`（含独立 3 态 Operator Gate 枚举，见 §2.3）、`ProvisioningPlan`、`StagingProvisioningExecutionMode`（仅 PLAN/VALIDATE/DRY_RUN/HUMAN_AUTHORIZED_APPLY，禁 AUTO/PRODUCTION）
  - `bom.py`：8 资源 BOM（复用 R1 `ResourceType`）
  - `dry_run_guard.py`：复用 R10 契约测试范式
  - `validator.py`：复用 R3/R6/R8 断言
  - `package.py`：复用 R13 确定性哈希
  - `gate.py`：Operator Gate（3 态）
  - `api_contract.py`：复用 R15 范式
- `scripts/validate_external_staging_operator_readiness_package.py`：复用 R16 范式。
- `.github/workflows/external-staging-provisioning-readiness-gate.yml`：复用 R17 结构。

### 2.2 全新文档（T3-T15、T20-T23、T34-T43）
- ADR：`docs/adr/ADR-PHASE-3.9.12-EXTERNAL-STAGING-PROVIDER.md`、`ADR-PHASE-3.9.12-IAC-STRATEGY.md`
- 架构/计划：`docs/EXTERNAL_STAGING_TARGET_ARCHITECTURE.md` + 8 份资源 Provisioning 计划（T7-T15）+ `EXTERNAL_STAGING_COST_MODEL.md` + `EXTERNAL_STAGING_RESOURCE_BOM.md`
- Runbook：`.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_INPUT_SHEET.md`、`EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md`、`EXTERNAL_STAGING_CLEANUP_ROLLBACK_RUNBOOK.md`
- SSOT/收口：T34-T35 SSOT 块 + Phase Boundary 行 + T43 46 节收口报告

### 2.3 Operator Gate 3 态枚举（必须独立于 4 态 `GateStatus`）
因 3.9.12 终态语义与 3.9.10/3.9.11 不同，Operator Gate **仅 3 态**（明确禁 GO/APPROVED/PRODUCTION_READY）：
- `BLOCKED`
- `PENDING_HUMAN_INPUT`
- `READY_FOR_HUMAN_PROVISIONING_REVIEW`

> 注意：3 态枚举**不复用** R4 的 `GateStatus`（那是 4 态且含 `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`）。3.9.12 的 `READY_FOR_HUMAN_PROVISIONING_REVIEW` 是「待真人 provisioning 评审」而非「已就绪可 GO」。语义必须严格区分。

---

## 3. 禁止项（复用纪律的硬边界）

- ❌ 不重新定义 `ResourceType` 8 类（必导入 R1）。
- ❌ 不新造等价 `GateStatus` 4 态（3.9.12 用独立 3 态，§2.3）。
- ❌ 不绕过 `assert_no_credential_leak` / `_FORBIDDEN_STATES` / `_FORBIDDEN_STEP_STATES`。
- ❌ 不在 IaC 模板/包/文档中硬编码真实 Secret（复用 R5/R6）。
- ❌ 不把 `engineering_enabled` 翻转为 True（复用 R19 全程守约）。
- ❌ 不吸收 Production Handoff WIP（3.9.10-A 隔离）。
- ❌ 不进入 3.9.13（完成即 STOP）。

---

## 4. 复用对账结论

| 维度 | 复用比例 | 说明 |
|---|---|---|
| 数据模型 | ~80% | 8 资源/凭据引用/身份/状态机全复用 |
| 安全范式 | 100% | 凭据扫描/禁态断言/动作默认拒绝全复用 |
| 确定性产物 | 100% | Package SHA-256 算法/证据链哈希全复用 |
| 评估范式 | 100% | GateCheck/GateResult/分级裁决全复用 |
| IaC 资产 | 0%（全新） | 仓库首次引入 |
| 文档/ADR/Runbook | 0%（全新） | 8 资源计划 + 成本 + BOM + 架构 |
| Operator Gate 语义 | 新定义（3 态） | 独立于既有 4 态 |

**结论**：3.9.12 严格建立在 3.9.10/3.9.11 基座之上，Track A 全部软件工程复用既有范式与数据结构，仅 IaC 资产、8 资源 Provisioning 文档、独立 3 态 Operator Gate、成本/BOM 模型为本阶段新增。无任何「重造第二套」。
