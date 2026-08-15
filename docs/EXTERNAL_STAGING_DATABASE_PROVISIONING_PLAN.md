# BOIP External Staging — Database Provisioning Plan (Phase 3.9.12, T9)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：production-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T8 Secret、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = database`（枚举值，复用 `ResourceType.DATABASE`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实 PG 实例/账号/密码：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging 托管 PostgreSQL（推荐档 B：主备；最小档 A：单节点），**不**与 production 库共享实例/数据。
- 数据库账号凭据经 secret_provider（T8）以 `CredentialReference` 引用，不存明文。
- 备份/保留策略就位；与生产库网络隔离（数据子网无公网，见 T7）。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/database.tf`。
- 默认服务：腾讯云 CDB for PostgreSQL（`tencentcloud_cdb`）。
- 支持档位参数：`instance_class`（A/B/C）、`replica`（B/C）。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `database.tf`（实例规格、子网、备份策略、账号占位）。
2. **VALIDATE**：校验实例在 staging 数据子网、无公网；`assert_no_credential_leak` 确认无明文密码。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply；DB 密码经 secret_provider 注入（AI 不碰明文）。

---

## 4. Track B 待输入（PENDING）

- 云账号 + 项目/VPC/子网（见 T7）
- PostgreSQL 版本与实例规格（按档位 A/B/C）
- 数据库账号与凭据轮换策略（仅引用）
- 备份保留期

---

## 5. 安全与隔离

- 数据子网无公网（T7）；仅 app / deployment_target 经私网访问。
- 凭据引用化（T8）；AI 不生成/读取真实 DB 密码。
- 与生产库物理隔离：独立实例、独立账号体系、独立备份。

---

## 6. 验证（ready 判定，非 verified）

- `database.tf` 通过 VALIDATE（子网/规格/无明文）。
- 连接信息占位齐全（host/port/dbname 待真实 provisioning 后填，且以引用表达）。
- 不宣称「数据库已连通/已验证」——真实连通待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：先吊销账号与备份引用，再 `terraform/opentofu destroy`（仅 staging 实例）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实 DB 密码；不连接 production 库；不执行真实 migration（migration 待 Track B + 真人）。
- 任何「已配置/已验证」状态 PENDING，不伪造。
