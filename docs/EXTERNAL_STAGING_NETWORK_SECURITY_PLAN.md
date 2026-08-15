# BOIP External Staging — Network & Security Plan (Phase 3.9.12, T7)

> 文档类型：跨资源网络安全计划（Track A）
> 责任角色：security-owner（主导）、production-owner（协同）
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T8 Secret 计划、T17 IaC、T21 Runbook

---

## 0. 状态声明（fail-closed）

- 网络安全边界状态：`pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实 VPC/子网/安全组/防火墙规则：**全部 PENDING**（Track B 真实网络配置）

---

## 1. 网络拓扑目标态

```text
Staging VPC (独立项目/账号, fingerprint≠production)
├── Public Subnet   → 仅 ALB/Ingress (staging 子域), 禁生产流量
├── Private Subnet  → app / deployment_target / idp 代理
├── Data Subnet     → database / object_storage / secret_provider (无公网)
└── Management     → 跳板/监控 (独立, 禁生产互联)
       ↓
Production VPC: 物理/逻辑隔离, 无 peering/无共享路由, denylist 命中即 BLOCKED
```

- **独立项目/账号**：staging 与 production 不得共享 VPC、路由表、安全组、IAM 主体。
- **无 peering**：staging ↔ production 之间禁止 VPC peering / 共享私网。
- **denylist**：staging 资源若 fingerprint 与 production 相同 → `BLOCKED`（复用 3.9.10 denylist）。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/network.tf`（VPC / 子网 / 路由 / 安全组 / NACL）。
- `variable "provider"` 默认 `tencent_cloud`；安全组规则以资源标签 `env=staging` 约束。
- 出网：仅允许到 provider API / 更新源 / 遥测端点；其余 default-deny。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `network.tf` plan（含 CIDR 规划、子网划分、安全组规则清单）。
2. **VALIDATE**：校验规则不开放 0.0.0.0/0 到数据子网；校验无 production CIDR 重叠。
3. **DRY_RUN**：`terraform/opentofu plan` 输出审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply（AI 不执行）。

---

## 4. Track B 待输入（PENDING）

- 真实云账号 + 独立项目/账号 ID
- CIDR 段（须与 production 不重叠，由真人规划）
- 防火墙/安全组审批策略
- 出网白名单（provider API 等）

---

## 5. 安全与隔离要点

- **最小权限**：staging IAM/角色仅含 staging 资源操作，禁 production 资源权限。
- **数据子网无公网**：database / storage / secret 仅私网可达。
- **默认拒绝**：入站 default-deny；仅 ALB/Ingress 暴露 staging 子域。
- **密钥不落盘明文**：所有凭据经 secret_provider（见 T8）。
- **审计**：网络变更入审计账本（3.9.12 允许最小类别 `provisioning_plan_generated`）。

---

## 6. 验证（ready 判定，非 verified）

- plan 通过 VALIDATE（无违规规则）；dry-run 无 error。
- 规则清单可读、可复盘。
- 不宣称「网络已连通/已隔离验证」——真实连通验证待 Track B 资源到位后由真人执行。

---

## 7. 回滚/清理

- 见 T22 `EXTERNAL_STAGING_CLEANUP_ROLLBACK_RUNBOOK.md`：`terraform/opentofu destroy`（staging 专属，禁 production）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实密钥；不创建 production 网络资源；不 peering 到 production。
- 任何「已隔离/已连通」状态 PENDING，不伪造。
