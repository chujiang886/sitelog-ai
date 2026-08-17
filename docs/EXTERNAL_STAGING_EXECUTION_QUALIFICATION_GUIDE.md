# 外部预生产执行与资格验证 —— 治理指南
## External Staging Execution & Qualification Layer

**Phase**：3.9.11
**性质**：真实外部预生产环境执行编排与资格验证层（**不是** Production 激活）。
**终端态**：`EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`
**最高红线**：`engineering_enabled=false` 全程保持；禁止真实 Production GO / 部署 /
回滚 / 密钥写入 / 权限授予 / 数据变更。

---

## 1. Architecture

```
agents/external_staging_execution/
├── models.py            # 执行计划 / 步状态（禁 real-execution）/ 终端态常量
├── config.py            # 复用 qualification 身份 + 指纹
├── adapters.py          # 单资源 fake adapter（诚实 PENDING）+ 契约测试
├── preflight.py         # 7 项 block 预检（分支/非生产/凭据/资源/禁止态/审计/仓库）
├── evidence.py          # ExecutionEvidenceItem + ExecutionEvidenceChain（SHA-256）
├── pipeline.py          # ExecutionPipeline（10 步计划 + 13 证据链）
├── gate.py              # ExternalStagingExecutionGate（BLOCKED/PENDING_*/READY_*）
├── package.py           # 机器可读包 + 确定性 SHA-256
├── security.py          # 执行安全校验（allowed/forbidden actions，fail-closed）
├── api_contract.py      # 7 路由 API 契约（无执行端点）
└── __init__.py          # 公共 API
```

复用 `agents/external_staging_qualification/`（3.9.10 资格层）契约与
`agents/staging_runtime/` 原语（RuntimeEnvironment.EXTERNAL_STAGING 等），**不重造第二套**。

## 2. Execution Plan (10 steps)

| # | 步 | 类型 | 真实执行？ |
|---|----|------|-----------|
| 1 | Preflight | plan | 否 |
| 2 | Deploy | plan-only | 否 |
| 3 | Runtime | pending | 否 |
| 4 | Isolation | pending | 否 |
| 5 | E2E | pending | 否 |
| 6 | Failure Sim | contract-test | 否 |
| 7 | Recovery | contract-test | 否 |
| 8 | Rollback | plan-only | 否 |
| 9 | Evidence | plan/contract/pending | 否 |
| 10 | Gate | pending | 否 |

步状态枚举 `ExecutionStepStatus`：NOT_STARTED / PLAN_ONLY / CONTRACT_TEST_PASSED /
PENDING_EXTERNAL_STAGING_RESOURCE / BLOCKED / FAILED；**无** EXECUTED / DEPLOYED_PRODUCTION / GO。
`is_real_execution` 恒 `False`。

## 3. 8 Resources（诚实 PENDING）

复用 3.9.10 资格层 8 资源登记簿（Database / Secret Provider / Identity Provider /
Object Storage / Telemetry / Alert Sandbox / Domain + TLS / Deployment Target），
全部 `verified=False`、`qualification_status=pending_external_staging_resource`。
适配器探针均返回 `PENDING`，不伪造连通性 / 验证。

## 4. Evidence Chain (13 items)

1 preflight + 1 deploy + 8 资源 + 1 failure + 1 recovery + 1 rollback。
全部 evidence_type ∈ {plan_only, contract_test, pending}，scope=external_staging，
`contains_secret=False`，`none_contains_secret` 恒 `True`。

## 5. Gate（4 态，fail-closed）

- `BLOCKED`（任一 block 级检查失败）
- `PENDING_EXTERNAL_STAGING_RESOURCE`（资源待决）
- `PENDING_HUMAN_VERIFICATION`（等待人工验证）
- `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`（可提交人工评审，非 GO）

**禁止** `APPROVED` / `PRODUCTION_READY` / `GO`。

## 6. API Contract（7 routes, no execution endpoint）

| Method | Path | Action |
|--------|------|--------|
| GET | /api/external-staging-execution/status | read |
| GET | /api/external-staging-execution/plan | read |
| GET | /api/external-staging-execution/gate | read |
| GET | /api/external-staging-execution/evidence | read |
| GET | /api/external-staging-execution/package | read |
| GET | /api/external-staging-execution/resources | read |
| POST | /api/external-staging-execution/human-record | human_record |

`forbidden_actions` = execute / deploy / activate / rollback_execute / production_write / secret_write。
`no_execution_endpoint=True`。

## 7. Security

`ExternalStagingExecutionSecurityValidator.validate_request(scope, actor, action, is_production_action)`：
- allowed scopes = {external_staging}；allowed actions = {read, human_record}；
- forbidden actions 默认拒绝；未知动作 fail-closed 拒绝。

## 8. 红线速查

- `engineering_enabled=false`；不输出 `engineering_approved`；
- 不真实部署 / 迁移 / 回滚 / 写 Secret / 改权限 / 改数据；
- 不把 Staging 说成 Production；不自动关 Incident / 不 skip 掩盖失败 / 不删断言换绿 / 不伪造结果；
- 终端态恒为 `EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`。

## 9. Phase 3.9.14 扩展：External Staging Runtime Deployment & End-to-End Qualification（运行时部署与端到端资格）

Phase 3.9.14 在 3.9.13（供给执行与资源登记）之上，补完「运行时部署可运行路径」与「External Staging E2E 资格可运行路径」两层，**不重造 staging runtime 核心**（复用 `agents/staging_runtime/` 成熟 fail-closed 基础层）。本阶段焦点严格限定在三条剩余主线：

1. **IaC 可执行性（IaC Executability）**：`agents/external_staging_runtime/iac_executor.py` 包裹 OpenTofu/Terraform 工具链，真实运行 `validate` / `fmt -check` / `plan -out`（plan-only，从不 `apply`），判定 9 个 `infrastructure/staging/*.tf` 模块在离线（无 provider 下载）条件下「工具链可用 + HCL 语法有效 + 全 count=0 骨架」三要件成立 → `iac_executable=True`。GitHub 限流导致的 provider 下载失败属 Track B 环境限制，非代码缺陷。
2. **Runtime Deployment 可运行路径**：`runtime_manifest` / `qualification` / `runtime_health` / `e2e_harness` / `failure_recovery` 五层在「resource-less（8/8 Pending）」下结构性不可达 Production，全部 `PLAN_ONLY` / `FORBIDDEN_PRODUCTION_ACTIONS`；13 项运行时资格校验 `code_verified=13/13`、`runtime_executed=0`。
3. **External Staging E2E 资格可运行路径**：`EndToEndQualificationHarness.build_plan()` 产出 6 步 `PLAN_ONLY_STRUCTURAL_OK` 计划，`terminal_state=PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO`；`FailureRecoveryRollbackPlan` 的 `production_rollback_forbidden=True`，仅 3 项本地安全步骤（local_snapshot / local_manifest_record / local_health_check）允许。

### 9.1 收口态（Closure Terminal State）

- `PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO`
- `engineering_enabled=false` 全程；`is_production=False`；`real_apply_allowed=False`；`real_execution_allowed=False`。
- 8 真实 External Staging 资源 `PENDING(8/8)`（AI 不代开）；9 跨环境隔离 `NOT VERIFIED`；13 运行时资格 `code_verified=13/13 / runtime_executed=0`；E2E 计划 `PLAN_ONLY`；Failure-Recovery `production_rollback_forbidden=True`。
- 确定性执行包 SHA-256（见 `build_machine_package()#package_hash`，剔除 `generated_at` 时间戳保证确定性）= `d632d6610e20c48ec72a2a7a04dbd17aee8c76ccdb436541960147fc5d4b9839`；`contains_real_secret=False` / `production_activation_prohibited=True` / `real_resources_provisioned=0`。
- 双钥匙：`MachineSafetyKey`（机器生成，`engineering_enabled=false`）+ `HumanAuthorizationKey`（须 `actor_kind=USER`，AI 不得 mint）；Apply Gate 独立 4 态（`PENDING_HUMAN_AUTHORIZATION` / `AUTHORIZED_AWAITING_APPLY` / `BLOCKED` / `DENIED`），`is_go_or_approved` 恒 False。
- 审计账本权威值 `total=129`（本阶段引入 0 新企业类目）。

### 9.2 交付物清单（Deliverables）

- `agents/external_staging_runtime/`：复用 `agents/staging_runtime/` 基础层 + 新增 `machine_package.py` / `api_contract.py` / `credential_deep_scanner.py` / `readonly_api.py` / `dashboard.py` / `self_audit.py`。
- `scripts/check_phase3914_branch_integrity.py`：Branch Integrity Guard（仅安全 git 操作，exit 0=PASS）。
- `.github/workflows/external-staging-runtime-e2e-qualification-gate.yml`：6 job CI 闸门（branch-integrity-gate / runtime-e2e-tests / package-deterministic-validate / api-contract-validate / credential-safety / repo-clean）。
- `backend/app/api/external_staging_runtime_e2e.py`：7 只读 GET 端点（/status /isolation /qualification /health /e2e /change-control /evidence）。
- `.ai/reviews/phase3.9.14_human_checklist.md`：六节 A-F 人类清单（A 节 AI 收口证据 / B-F 节 Track B 真人待办）。
- `.ai/runbooks/external_staging_runtime_e2e_qualification_runbook.md` + 本 §9 + `.ai/progress/phase3.9.14_test_matrix.md`。

### 9.3 禁止项（Forbidden）

- 禁 AI mint `HumanAuthorizationKey`（须 `actor_kind=USER`）；禁置 `engineering_enabled=true`；禁伪造真实 External Staging 证据（local/synthetic/dry-run 不得冒充 External real evidence）。
- 禁进 3.9.15；禁进 Production Handoff；禁向主理人提普通工程决策（AI 自主按授权完成 Track A）。
