# BOIP External Staging — Deployment Target Provisioning Plan (Phase 3.9.12, T15)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：production-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T8 Secret、T14 域名、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = deployment_target`（枚举值，复用 `ResourceType.DEPLOYMENT_TARGET`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实集群/镜像仓库/镜像 digest：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging 容器运行时（腾讯云 TKE / AWS ECS / 阿里 ACK）+ 镜像仓库（TCR/ACR/ECR），**不**与 production 集群/仓库共享。
- staging 专属命名空间/项目；镜像 digest 经真实 build/push 后登记（引用，不内嵌）。
- 应用经 staging 子域（T14）+ TLS 暴露；凭据经 secret_provider（T8）。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/deployment_target.tf`。
- 默认服务：腾讯云 TKE + TCR（`tencentcloud_tke` / `tencentcloud_tcr`）。
- 参数：集群规格、节点池、镜像仓库命名空间、ingress。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `deployment_target.tf`（集群、节点池、仓库命名空间、ingress 到 staging 子域）。
2. **VALIDATE**：校验集群标签 `env=staging`、ingress 域为 staging 子域（T14）；`assert_no_credential_leak`。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply；镜像经真实 CI build/push 后 digest 登记。

---

## 4. Track B 待输入（PENDING）

- 容器镜像仓库命名空间
- K8s/ECS 集群与节点池
- 镜像 digest 登记（待真实 build/push 后，引用形式）
- 部署凭据（经 secret_provider 引用）

---

## 5. 安全与隔离

- 独立集群/命名空间：staging 工作负载与 production 物理/逻辑隔离。
- 镜像仓库独立：staging tag 不得误推 production 仓库。
- ingress 仅 staging 子域；production 流量不可达。

---

## 6. 验证（ready 判定，非 verified）

- `deployment_target.tf` 通过 VALIDATE（标签/域名/无明文）。
- 部署清单占位齐全（含 staging 专属资源请求/限制）。
- 不宣称「应用已部署/已运行」——真实部署待 Track B 镜像到位后由真人执行。

---

## 7. 回滚/清理

- 见 T22：缩容/删除 staging 工作负载与命名空间 → `terraform/opentofu destroy`（仅 staging）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实部署凭据；不向 production 推送；不自动部署/回滚。
- 任何「已部署/已运行」状态 PENDING，不伪造。
