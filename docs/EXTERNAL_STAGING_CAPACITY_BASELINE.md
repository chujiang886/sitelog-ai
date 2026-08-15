# 外部预生产环境 · 容量基线（Capacity Baseline）

> Phase 3.9.12 · 供给规划基准（**示意区间，非真实报价**）
> 配套：`docs/EXTERNAL_STAGING_COST_MODEL.md`(T6) / `docs/EXTERNAL_STAGING_TARGET_ARCHITECTURE.md`(T4)
> 护栏：详见 `StagingCostGuard`（T6），超 `cost_budget` 默认 ¥6000 阻断 apply。

## 三档容量基线（示意）

| 资源 | A · 最小可用 (minimum viable) | B · 推荐 (recommended) | C · 类生产 (production-like) |
|------|------------------------------|------------------------|------------------------------|
| database（托管 PG） | 1 核 2GiB / 20GB SSD / 1 实例 | 2 核 4GiB / 100GB SSD / 1 主 | 4 核 8GiB / 200GB SSD / 1 主 1 备 |
| secret_provider | 1 密钥后端实例 / 默认加密 | 1 实例 + 自动轮换 | 1 实例 + 轮换 + 审计日志 |
| identity_provider | 1 独立 tenant / 50 用户 | 1 tenant / 200 用户 | 1 tenant / 500 用户 + SSO |
| object_storage | 1 桶 / 50GB / 低频 | 1 桶 / 200GB / 标准 | 1 桶 / 500GB / 标准 + 版本 |
| telemetry | 15 天 retention / 基础指标 | 15 天 / 指标+日志 | 15–30 天 / 全量追踪 |
| alert_sandbox | 1 独立通知组 / 静默 | 1 组 + 路由 | 1 组 + 路由 + 值班轮换（禁 production） |
| domain_tls | 1 staging 子域 / 1 证书 | 1 子域 + 自动续期 | 1 子域 + 多 SAN(staging) + 监控 |
| deployment_target | 1 节点 / 2 vCPU | 2 节点 / 4 vCPU | 3 节点 / 8 vCPU + 自动扩缩 |

## 网络与隔离基线

| 维度 | 基线 |
|------|------|
| VPC | 独立 VPC（CIDR 与 production 不重叠） |
| 子网 | 1 公网（仅 bastion/ingress）+ 1 私网（数据层无公网，见 `network.tf`） |
| 安全组 | 默认拒绝入站；仅开放 staging 子域所需端口 |
| Peering | **无** production peering（红线） |
| 跨环境隔离 | fingerprint ≠ production；命中 denylist → BLOCKED |

## 容量校验（fail-closed）

- 任一资源超 C 档（类生产）须四角色额外评审，否则 `BLOCKED`。
- 总成本预估超 `cost_budget` → `StagingCostGuard` 阻断 apply。
- 容量基线仅为规划参考；真实规格由责任角色在人工输入表（T20）登记，AI 不预估真实配额。

## 基线用途

1. 为 Runbook（T21）提供逐项规格参考。
2. 为 `StagingCostGuard` 提供预算护栏锚点。
3. 为后续真实 provisioning 的「容量证据」提供对照基准（仍须真人提供真实值）。
