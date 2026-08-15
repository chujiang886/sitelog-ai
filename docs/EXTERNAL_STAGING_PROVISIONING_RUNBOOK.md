# 外部预生产环境 · 供给 Runbook（Provisioning Runbook）

> Phase 3.9.12 · 仅供**真人/运维**在离线授权后执行
> 配套：`.ai/staging/external_staging_human_input_table.json`(T20) / `docs/EXTERNAL_STAGING_TARGET_ARCHITECTURE.md`(T4)
> 工具：`infrastructure/staging/*.tf`(OpenTofu) / `scripts/validate_external_staging_provisioning.py`(T19)

## 前置条件（fail-closed 闸门）

本 Runbook **仅在以下全部满足后**由真人启动；任一不满足则不得执行 apply：

1. ✅ 8 资源真实输入已由对应责任角色在**人类终端**登记（见人工输入表 T20），状态统一 `PENDING → 已提供`。
2. ✅ 四角色（production-owner / release-manager / security-owner / auditor）线下提交证据并签署。
3. ✅ 主理人在人类终端将 `engineering_enabled` 置 `true`（**唯一 AI 不代执行之动作**）。
4. ✅ `python scripts/validate_external_staging_provisioning.py` 通过（算子包未被篡改、8 资源 PENDING、`engineering_enabled=false`、Operator Gate 3 态合法）。
5. ✅ `python scripts/generate_external_staging_provisioning_package.py` 重算哈希与已签署版本比对一致。
6. ✅ `tofu` 已安装（≥1.6），且 `provider` 凭据经环境变量（如 `TENCENTCLOUD_SECRET_ID`/`TENCENTCLOUD_SECRET_KEY`）或 secret_provider 注入——**不写入 `.tf` 明文**。

> ⚠️ 本 Runbook 的执行模式为 `HUMAN_AUTHORIZED_APPLY`（预留给真人）。AI 永不进入此模式、永不代执行。

## 步骤

### 步骤 0 — 进入 IaC 目录并校验占位
```bash
cd infrastructure/staging
grep -l "count            = 0" database.tf secret_provider.tf object_storage.tf deployment_target.tf
# 确认 4 个真实数据型模块均为 count=0 占位（AI 不代开真实资源）
```
> 若任一模块 `count != 0`，**立即中止**——说明被误改，回退到仓库冻结版本。

### 步骤 1 — 初始化与供应商选择
```bash
tofu init
# provider 默认 tencentcloud；若要 aws/alibabacloud，编辑 main.tf 取消对应 provider 注释
# 并删除 tencentcloud block，同时覆写 var.provider
tofu plan -var="provider=tencentcloud" -out=tfplan
```

### 步骤 2 — Dry-run 校验（不落真实资源）
```bash
tofu show tfplan          # 人工复核 plan：确认仅 staging 资源、无 production peering
python scripts/validate_external_staging_provisioning.py   # 算子包一致性
```
复核要点：
- 所有资源位于独立 VPC/子网（见 `network.tf`），**无** production peering。
- 存储桶 CORS 仅含 staging 子域；IdP 回调仅 staging 子域；证书 SAN 不含 production。
- 告警组 `forbid_prod_notify=true`，**不**路由到 production on-call。

### 步骤 3 — 取消占位（逐资源，由对应责任角色确认）
对每个真实数据型模块，将该资源的 `count = 0` 改为 `count = 1`（或具体实例数），**仅限真人操作**：
```hcl
# database.tf
count = 1   # 原 count = 0；真人确认后开通
```
> 严禁批量取消全部 8 资源 count；按依赖顺序（network → secret → database/storage/idp → telemetry/alert → domain → deployment）逐项 apply。

### 步骤 4 — 逐资源 apply（HUMAN_AUTHORIZED_APPLY）
```bash
tofu apply -var="provider=tencentcloud" tfplan
# 或分资源：tofu apply -target=tencentcloud_mysql_instance.ext_staging_db
```
应用后：
- 将生成的**资源引用**（非明文）回填到人工输入表与 `CredentialReference`（如 DB 连接串引用、IdP client_secret 引用）。
- **绝不**将密码/token/私钥写入 Git / Logs / Audit / Package。

### 步骤 5 — 验收与证据
```bash
tofu output            # 记录 resource references（非明文）
```
- 在独立 staging 环境运行冒烟测试（连接性/隔离/运行时），**不**触碰 production。
- 四角色复核证据，更新算子包 `human_pending` 清空、`pending_resources` 收敛。

### 步骤 6 — 收尾
- 锁定 state 文件访问；rotate 任何临时凭据。
- 更新 `docs/EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` 状态（仅人类终端）。

## 紧急中止
若步骤中检测到明文密钥、越权、production 联通或预算超限 → 立即 `BLOCKED`，停止并跳转到 Cleanup/Rollback Runbook。
