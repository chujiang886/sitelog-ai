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
