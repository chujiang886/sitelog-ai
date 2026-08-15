# 外部预生产环境 · 清理与回滚 Runbook（Cleanup / Rollback Runbook）

> Phase 3.9.12 · 仅供**真人/运维**执行
> 配套：`docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md`(T21) / `docs/EXTERNAL_STAGING_NETWORK_SECURITY_PLAN.md`(T7)
> 工具：`infrastructure/staging/*.tf`(OpenTofu)

## 触发条件

以下任一发生时，启动本 Runbook（fail-closed 优先于继续供给）：

1. 供给过程中检测到**明文密钥/凭据**落入 IaC / Logs / Git / Audit。
2. staging 与 production 发生**非预期联通**（peering/共享子网/共享 IdP tenant）。
3. 成本预算（`cost_budget`，默认 ¥6000 示意）**超限**。
4. 任一 `count != 0` 模块被 AI 或非授权方误改。
5. 人工输入缺失/伪造，Operator Gate 落入 `BLOCKED`。
6. 主理人或四角色**撤销**授权（`engineering_enabled` 回退 `false`）。

## 回滚等级

| 等级 | 范围 | 动作 | 数据影响 |
|------|------|------|---------|
| L0 | 计划层 | 删除 `tfplan`，保留 state 不变 | 无 |
| L1 | 单资源 | `tofu destroy -target=<resource>`（按依赖逆序） | 仅该资源 |
| L2 | 全 staging | `tofu destroy`（先确认无 production 资源在 state） | 全 staging |
| L3 | 凭据泄露 | 立即在 secret_provider **rotate** 全部相关凭据 + L2 | 凭据失效 |

## 步骤

### 步骤 A — 冻结与评估
```bash
cd infrastructure/staging
tofu state list            # 列出当前 state 中的资源
# 确认 state 中无任何 production 资源（fingerprint 校验）
```

### 步骤 B — L1 单资源回滚（按依赖逆序）
```bash
# 依赖逆序：deployment → domain → alert/telemetry → idp/storage/database → secret → network
tofu destroy -target=tencentcloud_kubernetes_cluster.ext_staging_cluster -auto-approve=false
tofu destroy -target=tencentcloud_cos_bucket.ext_staging_bucket -auto-approve=false
# ... 逐项确认（禁止 -auto-approve 批量误删）
```

### 步骤 C — L2 全 staging 清理
```bash
tofu destroy -auto-approve=false
# 人工复核销毁清单，确认仅 staging 资源（独立 VPC/子网/子域/SAN）
```
> 销毁前**必须**确认：无 production peering、证书 SAN 不含 production、告警组未路由 production。

### 步骤 D — L3 凭据处置（如泄露）
- 在 secret_provider 控制台 rotate 所有相关凭据引用。
- 更新人工输入表（T20）对应条目状态为 `revoked`，**不**回填明文。
- 运行凭据扫描：`python -c "from agents.external_staging_provisioning.dry_run_guard import IacDryRunGuard; IacDryRunGuard().evaluate()"` 确认 IaC 无泄漏。

### 步骤 E — 恢复占位（回到 AI 就绪态）
将已开通资源的 `count` 重新置 `0`（恢复 AI 不代开真实资源的冻结态）：
```hcl
# database.tf
count = 0   # 恢复占位，回到 pending_external_staging_resource
```

### 步骤 F — 证据与通知
- 记录销毁/回滚日志（不含明文），四角色复核。
- 若因告警误发 production → 额外确认 `alert_sandbox.tf` 的 `forbid_prod_notify=true` 未被改。

## 护栏（fail-closed）

- **禁止** `tofu destroy` 不带 `-auto-approve=false`（防止批量误删 production）。
- **禁止** 在 state 含 production 资源时执行任何 destroy。
- **禁止** AI 自动执行本 Runbook 的任意 destroy/rotate（require_human_actor）。
- 回滚后 `engineering_enabled` 维持调用方设定；若因违规触发，回退 `false`。
