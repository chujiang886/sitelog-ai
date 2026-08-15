# 外部预生产环境 —— 运维 Runbook（External Staging Operations Runbook）

**Phase**：3.9.10 External Staging Qualification & Evidence Integration Layer
**适用范围**：仅描述 resource registration / probe / qualification / deployment to
external staging / validation / rollback staging / evidence capture。
**禁止**：任何 Production 操作（部署 / 迁移 / 回滚 / 写 Secret / 权限授予 / 数据变更）。

---

## 1. 资源登记（Resource Registration）

- 仅登记 **reference / metadata / credential reference**；
- 真人**不得**把 Secret 直接粘入 Markdown / JSON / Git / chat 派生源文件；
- 复用既有 Evidence Intake（若已存在），不造新 secret storage。

## 2. 探针（Connectivity Probe）

- 8 类探针（`ExternalStagingConnectivityProbe`）均为 read-only / non-destructive；
- 带超时控制；无 Production fallback；环境先验证（EXTERNAL_STAGING）；
- 真实资源缺失 → 返回 `PENDING_EXTERNAL_STAGING_RESOURCE`，不伪造连通性。

## 3. 资格验证（Qualification）

- `ExternalStagingQualifier` 对 8 资源做 Connectivity → Isolation → Qualification；
- 命中 Production Denylist → `BLOCKED`；
- 缺真实证据 → 不越级到 `QUALIFIED_EXTERNAL_STAGING`。

## 4. 部署到 External Staging（仅限 External Staging）

- `ExternalStagingDeploymentProvider.validate_target`：target 未证明非 Production → 拒绝；
- `build_plan` → `preflight` → `deploy_staging(execute=True)`（须资源明确授权 + 人工触发）；
- 记录 `ExternalStagingDeploymentEvidence`（release_id / commit / artifact hash /
  target / fingerprint / deployed_at / deployed_by / health / rollback_ref / hash）；
- **不得记录为 Production deployment**（`is_production_deployment=False`）。

## 5. 验证（Validation）

- `validate_deployment(evidence)`：仅确认 staging 部署健康，不触碰 Production。

## 6. 回滚（Rollback Staging）

- `rollback_staging(evidence)`：仅回滚 External Staging，scope=external_staging；
- 绝不回滚 Production。

## 7. 证据采集（Evidence Capture）

- `make_evidence(...)` 自动 SHA-256；scope 固定 external_staging；`contains_secret=False`；
- 证据链 `EvidenceChain.chain_hash()` 提供整链摘要。

## 8. 红线速查

- `engineering_enabled=false` 全程保持；
- 禁止 Production GO / Deploy / Migration / Rollback / Secret 写入 / 权限授予；
- 禁止 AI 替代人工确认 / 四角色 Production 签署。
