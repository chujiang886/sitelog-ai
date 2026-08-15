# ADR-PHASE-3.9.12 — External Staging IaC Strategy

- **Status**: RECORDED
- **Phase**: 3.9.12 External Staging Provisioning & Operator Readiness
- **Date**: 2026-08-15
- **Related**: T3 Provider ADR、T4 目标架构、T17 IaC 模板、T18 Dry-run Guard、T19 Validator、T31 StagingCostGuard

---

## 1. Context

Phase 3.9.12 需把 0/8 真实资源推进到「可被真人按明确 Runbook 与 IaC/模板实际 Provision 的就绪状态」。IaC 是这一就绪态的核心载体。约束：

- AI **不**执行真实 apply；IaC 仅生成 `plan` / `validate` / `dry-run` 就绪物。
- 必须 `plan`/`dry-run`/`destroy` 不碰 Production（fail-closed）。
- `engineering_enabled = false`；模板中**绝不**出现真实密钥/Token/私钥。

---

## 2. Decision

**采用 OpenTofu（Terraform 开源兼容，HCL 语法）为主 IaC 引擎**，辅以 shell/CLI 包装脚本实现 provider-agnostic 参数化。

| 维度 | 决策 |
|---|---|
| 引擎 | OpenTofu ≥ 1.6（Terraform 兼容，规避 BSL 许可风险） |
| 语言 | HCL（`.tf`） |
| 默认 Provider | `tencentcloud`（与 T3 ADR 首选一致） |
| 供给方无关 | `variable "provider"` 驱动；默认 `tencentcloud`，支持覆写为 `aws` / `alibabacloud`（并提供对应 provider block 注释/alt 模块） |
| 状态管理 | 本地/远端 staging 专属 backend（**独立**于 production state，禁止共享） |
| 执行模式 | `StagingProvisioningExecutionMode`：PLAN / VALIDATE / DRY_RUN / HUMAN_AUTHORIZED_APPLY（禁 AUTO/PRODUCTION） |
| 成本护栏 | `variable "cost_budget"` 供 StagingCostGuard（T31）读取，超限 BLOCKED |

---

## 3. Provider-Agnostic 落地方式

`variables.tf` 暴露 `provider` 变量；`main.tf` 按 `provider` 选择 provider block（默认 tencentcloud，附 aws/alibabacloud 注释模板）。各资源 `.tf` 文件：
- 以 `tencentcloud_*` 资源为主实现（真实可用默认路径）；
- 顶部注释给出对应 `aws_*` / `alicloud_*` 资源映射，便于真人覆写 provider 时替换；
- 资源命名/标签统一 `env=staging`、`phase=3.9.12`，禁止 production 标签。

---

## 4. 目录结构（T17）

```text
infrastructure/staging/
├── versions.tf            # terraform + required_providers (tencentcloud/aws/alibabacloud)
├── variables.tf           # provider / region / environment / cost_budget / tags
├── main.tf                # provider block (variable-driven)
├── network.tf             # VPC/子网/安全组 (T7)
├── secret_provider.tf     # 密钥后端 (T8)
├── database.tf            # 托管 PG (T9)
├── identity_provider.tf   # OIDC/SSO (T10)
├── object_storage.tf      # COS/S3/OSS (T11)
├── telemetry.tf           # 日志/指标 (T12)
├── alert_sandbox.tf       # 告警沙箱 (T13)
├── domain_tls.tf          # 子域+证书 (T14)
├── deployment_target.tf   # TKE/ECS + TCR (T15)
└── README.md              # 用法: plan/dry-run/apply(真人)/destroy
```

---

## 5. Consequences

**正面**
- 真实可执行的 IaC（非伪代码），真人持凭据即可 apply。
- provider-agnostic 预留扩展点，符合 T3 ADR。
- state 与 production 隔离，destroy 不波及 production。
- 与 Dry-run Guard / Validator / Cost Guard / CI 闸门集成（T18/T19/T31/T33）。

**约束**
- 真实 apply 需真人 + 真实凭据 + 四角色签署（`HUMAN_AUTHORIZED_APPLY`）。
- AI 不运行 `tofu apply`；模板静态校验（T19）不依赖真实 provider 连通。
- 默认写 tencentcloud 实现；覆写 provider 时需真人补充对应资源块（ADR 已给映射）。

---

## 6. 验证（ready 判定）

- `tofu fmt -check` / `tofu validate`（若环境具备）通过；否则由 T19 静态校验（HCL 解析 + 禁明文 + 变量齐备）兜底。
- `tofu plan` 输出可生成（dry-run 就绪），不实际变更。
- 不宣称「资源已创建」——真实创建待 Track B + 真人 apply。
