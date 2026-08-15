# 外部预生产执行与资格验证 —— 运维 Runbook（External Staging Execution Runbook）

**Phase**：3.9.11 External Staging Execution & Qualification Layer
**适用范围**：仅描述执行编排 / 契约模拟 / 故障恢复演练（contract-test）/ 证据采集 /
闸门评估。本层**不真实部署、不真实回滚、不触碰 Production**。
**禁止**：任何 Production 操作（部署 / 迁移 / 回滚 / 写 Secret / 权限授予 / 数据变更）。

---

## 1. 执行编排（Execution Orchestration）

- `ExecutionPlan`：10 步（preflight / deploy / runtime / isolation / e2e / failure /
  recovery / rollback / evidence / gate）；
- 每步状态仅 `PLAN_ONLY` / `CONTRACT_TEST_PASSED` / `PENDING_EXTERNAL_STAGING_RESOURCE`
  / `BLOCKED` / `NOT_STARTED`；**无** `EXECUTED` / `DEPLOYED_PRODUCTION` / `GO`；
- `is_real_execution` 恒 `False` —— 框架记录"计划/契约"，绝不宣称真实执行。

## 2. 适配器探针（Adapter Probe）

- `ExternalStagingExecutionAdapter`：单资源 fake adapter（诚实 `PENDING`）；
- `probe_all()`：8 资源全 `PENDING`，不伪造连通性；
- `contract_test()`：仅验证代码路径自洽，不连接真实资源；
- `assert_no_real_execution_claimed()`：断言无适配器宣称真实配置 / 验证。

## 3. 预检（Preflight）

- `run_preflight(...)`：7 项 block 检查（分支 / 非生产 / 凭据安全 / 资源诚实 PENDING /
  无禁止态 / 审计不漂移 / 仓库清洁）；
- 任一失败 → 不允许进入执行阶段。

## 4. 故障 / 恢复演练（Failure / Recovery Drill）

- `Failure Simulation` / `Recovery` 步为 `CONTRACT_TEST_PASSED`：仅验证演练代码路径
  自洽，**不触发真实故障、不真实恢复**；
- 真实故障演练须由主理人 + 四角色线下设计、在非 Production 环境受控执行。

## 5. 回滚（Rollback）

- `Rollback` 步为 `PLAN_ONLY`：记录回滚预案，**未真实执行回滚**；
- 真实回滚须明确 scope=external_staging，**绝不回滚 Production**。

## 6. 证据采集（Evidence Capture）

- `ExecutionEvidenceItem`：自动 SHA-256；evidence_type ∈ `plan_only` / `contract_test`
  / `pending`；scope 固定 `external_staging`；`contains_secret=False`；
- `ExecutionEvidenceChain`：13 条证据，`chain_hash()` 提供整链摘要，`none_contains_secret` 恒 `True`。

## 7. 闸门评估（Gate）

- `ExternalStagingExecutionGate.evaluate(...)`：fail-closed 裁决；
- 状态仅 4 态：`BLOCKED` / `PENDING_EXTERNAL_STAGING_RESOURCE` /
  `PENDING_HUMAN_VERIFICATION` / `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`；
- 禁 `APPROVED` / `PRODUCTION_READY` / `GO`。

## 8. 红线速查

- `engineering_enabled=false` 全程保持；
- 禁止 Production GO / Deploy / Migration / Rollback / Secret 写入 / 权限授予；
- 禁止 AI 替代人工确认 / 四角色 Production 签署；
- 禁止 skip / xfail / ignore 掩盖失败 / 删断言换绿 / 伪造结果。
