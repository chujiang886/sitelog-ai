# Phase 3.9.12 — Current Stack Inventory (T1)

> 生成时间：2026-08-15
> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 目的：清点当前 BOIP 技术栈与既有 External Staging 资产，为 T2 复用分析提供事实基线。

---

## 1. 仓库与目录结构

```text
BOIP/
├── agents/                         # Python 多智能体运行时（企业包根）
│   ├── external_staging_qualification/   # 3.9.10 资格认定 + 证据集成层（基础）
│   ├── external_staging_execution/       # 3.9.11 执行 + 资格验证层（复用 qualification）
│   ├── staging_runtime/                  # 运行时环境身份/资源模型
│   └── config_loader.py                 # load_engineering_enabled() 等
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── api/                   # FastAPI 路由（含 external_staging_execution.py）
│   │   └── ...
│   └── requirements.txt
├── frontend/                      # Next.js 14 前端
├── scripts/                       # 各类校验/生成脚本
├── docs/                          # 文档（ADR / 指南）
├── .ai/                           # 治理元数据（progress / reviews / staging / baselines / runbooks / packets）
├── .github/workflows/             # CI 门禁
└── tests/                         # 测试套件（agents / backend / frontend）
```

仓库根目录为本阶段所有 `git` 操作的权威 CWD。**无** `infrastructure/` `deploy/` `docker/` `k8s/` `terraform/` 目录（IaC 资产在 T17 首次创建）。

---

## 2. 后端技术栈

| 维度 | 现状（事实） |
|---|---|
| 语言/运行时 | Python 3.11（仓库 CI 使用 3.11；本机隔离运行时为 3.13.12 用于脚本/校验） |
| Web 框架 | FastAPI（路由在 `backend/app/api/`） |
| ORM | SQLAlchemy 2.x |
| 迁移 | Alembic |
| 测试 | pytest（agents/ 与 backend/ 双套）；前端 Jest |
| 身份/RBAC | `backend/app/identity/`（Bearer JWT / OIDC 适配器，默认拒绝） |
| 治理 | 审计账本（`.ai/baselines/audit_action_category_ledger.json`，canonical total=129）、SSOT `project_status.json` |
| 配置红线 | `agents.config_loader.load_engineering_enabled()` —— 全链路读取，恒为 `False` |

---

## 3. 前端技术栈

| 维度 | 现状 |
|---|---|
| 框架 | Next.js 14 + TypeScript |
| 样式 | Tailwind CSS |
| 状态 | Zustand |
| 测试 | Jest（jest.config.js，使用仓库自身 node_modules） |
| 既有看板 | 治理驾驶舱、激活就绪、变更控制、外部 Staging 执行 等只读看板（可复用范式） |

---

## 4. 智能体运行时（agents/ 包）

- `agents.external_staging_qualification`：3.9.10 资格层，提供 **复用基座**：
  - `models.py`：`ResourceType`（8 类）、`RESOURCE_TYPE_ORDER`、`ResourceQualificationStatus`、`GateStatus`（4 态）、`RuntimeHealthStatus`、`CredentialReference`、`ExternalStagingResource`、`ExternalStagingResourceRegistry`、`ExternalStagingEnvironmentIdentity`
  - `credential_scanner.py`：`assert_no_credential_leak` / `CredentialLeakError`（明文凭据扫描，fail-closed）
  - `config.py`：`load_external_staging_identity`、`fingerprint_collision_with_production`
  - `gate.py`：`GateCheck` / `GateResult`（闸门评估原语）
  - `adapters.py`：资源适配探针
- `agents.external_staging_execution`：3.9.11 执行层，**复用** qualification：
  - `models.py`：`ExecutionStepKind` / `ExecutionStepStatus` / `ExecutionStep` / `ExecutionPlan` / `build_default_execution_plan` / `assert_not_forbidden_step_state`
  - `adapters.py`：`AdapterProbeResult` / `ExternalStagingExecutionAdapter` / `probe_all` / `adapters_contract_test_all_pass`（**诚实 PENDING**，契约测试仅验代码路径）
  - `gate.py`：`ExternalStagingExecutionGate`（4 态 fail-closed 评估器）
  - `evidence.py`：`ExecutionEvidenceChain`（证据链 + `chain_hash()`）
  - `package.py`：`build_execution_package` / `package_hash`（确定性 SHA-256）
  - `security.py`：`ExternalStagingExecutionSecurityValidator`（请求动作默认拒绝）
  - `pipeline.py`：`ExecutionPipeline`
  - `config.py`：复用资格层身份加载器
  - `api_contract.py`：7 routes API 契约（机器可读，`no_execution_endpoint=True`）
- `agents.staging_runtime.environment`：`RuntimeEnvironment.EXTERNAL_STAGING`、`EnvironmentIdentity`、`EnvironmentResources`

---

## 5. 既有 External Staging 资产（3.9.10 + 3.9.11）

### 5.1 代码
- `agents/external_staging_qualification/*`（基座）
- `agents/external_staging_execution/*`（执行层）
- `backend/app/api/external_staging_execution.py`（7 只读路由 + 1 人工登记 POST）
- `backend/app/api/external_staging_qualification.py`
- `scripts/generate_external_staging_execution_package.py`
- `scripts/validate_external_staging_execution_package.py`
- `scripts/check_phase3911_branch_integrity.py`
- `tests/agents/test_external_staging_execution.py`（65+ fail-closed 用例）

### 5.2 文档/元数据
- `.ai/reviews/phase3.9.11_external_staging_execution_qualification_report.md`
- `.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_EXECUTION_CHECKLIST.md`
- `.ai/runbooks/staging/EXTERNAL_STAGING_EXECUTION_RUNBOOK.md`
- `docs/EXTERNAL_STAGING_EXECUTION_QUALIFICATION_GUIDE.md`
- `.ai/packets/external_staging_execution_human_packet.json`
- `.ai/staging/external_staging_execution_qualification_package.json`
- `.ai/baselines/external_staging_execution_api_contract.json`

### 5.3 CI 门禁
- `.github/workflows/external-staging-execution-qualification-gate.yml`（8 jobs：branch-integrity / tests / package / audit-ledger / api-contract / credential-safety / isolation / repo-clean）
- `.github/workflows/external-staging-qualification-gate.yml`

---

## 6. CI/CD 与工具

- GitHub Actions 工作流（见上）。通用 `ci.yml`、`baseline-freeze-gates.yml`、`docs-check.yml`。
- `scripts/` 含审计账本校验、分支完整性校验、包生成/校验等治理脚本。
- **IaC / 容器编排资产**：当前**不存在**（T17 将创建 `infrastructure/staging/`）。
- **Provider SDK 接入**：当前无真实云 SDK 依赖（Track B 资源 PENDING）。

---

## 7. 配置与密钥处理（红线相关）

- `engineering_enabled` 通过 `agents.config_loader.load_engineering_enabled()` 全局读取，全程 `False`。
- 任何凭据均以 `CredentialReference`（仅引用/provider/id/rotation 元数据）表达，绝不明文入 Git/Logs/Audit/Docs/Package。
- `credential_scanner.assert_no_credential_leak` 在闸门口与 CI 中强制扫描。

---

## 8. 本阶段（3.9.12）相对现状的「新增」范畴

| 范畴 | 是否复用既有 | 说明 |
|---|---|---|
| 8 资源 BOM（T5） | 复用 `ResourceType`/`RESOURCE_TYPE_ORDER` | 不重造枚举 |
| 各资源 Provisioning 计划文档（T7-T15） | 新增（文档） | 8× 计划书 |
| Provider 选择 ADR（T3） | 新增 | 决策记录 |
| 目标架构文档（T4） | 新增 | 架构说明 |
| 成本模型（T6） | 新增 | 三档成本 |
| IaC 模板（T17） | **全新** | `infrastructure/staging/` 首次创建 |
| Dry-run Guard（T18）/ Provisioning Validator（T19） | 复用 adapter/contract_test + package_hash 范式 | 新建模块但复用范式 |
| 人工输入表/Runbook（T20-T22） | 新增（文档） |  |
| Operator Readiness Package（T24-T26） | 复用 `package.py`/`evidence.py` 范式 | 新建但复用确定性哈希 |
| API/Dashboard（T28） | 复用 `external_staging_execution.py` 路由范式 | 新增路由 |
| API Contract SSOT（T29） | 复用 `api_contract.py` 范式 | 新建契约 |
| Cost Guard（T31） | 新增 | 成本护栏 |
| CI Gate（T33） | 复用 `*-gate.yml` 结构 | 新文件，改 phase/计数/分支 |
| SSOT/Phase Boundary（T34-T35） | 复用既有 SSOT 块结构 | 新增 3.9.12 块 |

---

## 9. 关键约束（来自 T0 核验）

- `engineering_enabled = False`（最高红线，全程不变）
- 8 资源真实输入统一 `PENDING_EXTERNAL_STAGING_RESOURCE`
- Operator Gate 仅 3 态：`BLOCKED` / `PENDING_HUMAN_INPUT` / `READY_FOR_HUMAN_PROVISIONING_REVIEW`（**禁 GO/APPROVED/PRODUCTION_READY**）
- 完成即 STOP，禁进 3.9.13
