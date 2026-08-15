# ADR-PHASE-3.9.12 — External Staging Provider Selection

- **Status**: RECORDED (provisional; binding deferred to human owner with real credentials)
- **Phase**: 3.9.12 External Staging Provisioning & Operator Readiness
- **Date**: 2026-08-15
- **Supersedes / Related**: `PRODUCTION_DEPLOYMENT_GUIDE.md`（生产路径 A：Mac Docker Desktop → 腾讯云 TCR → Production Server）、`BOIP Human Remediation · 腾讯云 Deployment Skill Capability Audit`（B-1 路径 A 决策）

---

## 1. Context（背景）

Phase 3.9.11 已将「8 类外部预生产资源」推进到 `BUILT_NO_GO`，真实资源全部 `PENDING_EXTERNAL_STAGING_RESOURCE`（DB / Secret / IdP / Object Storage / Telemetry / Alert Sandbox / Domain-TLS / Deployment Target，8/8 未配置未验证）。

Phase 3.9.12 的目标是：把「0/8 真实资源」推进到「可被真人/运维按明确 Runbook 与 IaC/模板实际 Provision」的**就绪状态**（不实际 Provision，仅就绪）。为此必须先有**清晰的 Provider 选择决策**，使后续 IaC 模板（T16/T17）、8 资源 Provisioning 计划（T7-T15）、成本模型（T6）、Operator Package（T24-T26）有统一的供给方语义锚点。

约束（来自 3.9.12 总指令 + 治理红线）：
- `engineering_enabled = False`；AI **不**创建真实云账号、**不**写入真实密钥/Token、**不**执行真实 Provision / Production 动作。
- 8 资源真实输入统一 `PENDING_EXTERNAL_STAGING_RESOURCE`，本 ADR 仅做**决策记录**，不做真实绑定。
- 完成即 STOP，禁进 3.9.13。

---

## 2. Decision Drivers（决策驱动）

| # | 驱动 | 说明 |
|---|---|---|
| D1 | 生态一致性 | BOIP 已用腾讯混元 TokenHub（HY-Vision-2.0-Instruct）作为 track_a LLM；生产路径 A 已选定腾讯云 TCR。Staging 同生态可减少 staging→production 差异。 |
| D2 | 合规与数据驻留 | BOIP 为中国建筑开口设计平台（中文环境），CN 区域合规与数据驻留要求倾向国内云。 |
| D3 | IaC 成熟度 | 候选 Provider 需有成熟 Terraform/OpenTofu/Pulumi provider，支撑 T17 模板。 |
| D4 | 成本可预测 | 三档成本模型（minimum viable / recommended / production-like）需 Provider 有明确计费粒度。 |
| D5 | 运维可达性 | 真人/运维需能实际 Provision（控制台/CLI/API），不依赖 AI 代执行。 |
| D6 | 失败域隔离 | Staging 与 Production 必须结构隔离（fingerprint 不同、denylist 命中即 BLOCKED）。 |

---

## 3. Options Considered（候选方案）

| 选项 | 描述 | 利 | 弊 |
|---|---|---|---|
| O1 Tencent Cloud（腾讯云） | 国内云，TCR/COS/CAM/TKE/DNSPod/SSL 完整 | D1/D2 强契合；生产路径 A 已用 TCR；Terraform provider 成熟 | 真实账号/预算仍 PENDING（Track B） |
| O2 Alibaba Cloud（阿里云） | 国内云，ACR/OSS/RAM/ACK | D2 契合；IaC 成熟 | 与生产路径 A 不同生态，D1 弱 |
| O3 AWS | 国际云，RDS/Secrets Manager/Cognito/S3/CloudWatch/SNS/ACM/ECS | IaC 最成熟 | D2 弱（数据出境/合规成本高）；与生产路径 A 不同生态 |
| O4 Azure | 国际云 | IaC 成熟 | 同上 D2 弱 |
| O5 自托管 / 裸机 | 自有服务器 + Docker Compose | 成本可控、完全自控 | 运维负担重；缺托管 IdP/Secret/TLS 服务，与「8 资源」语义偏离 |
| O6 多云 / 供给方无关 | IaC 模板参数化，运行时选 Provider | 最大灵活 | 复杂度高；本阶段仅就绪、不实际 Provision，过度设计 |

---

## 4. Decision（决策）

**记录决策（RECORDED，非绑定）**：

> 将 **Tencent Cloud（腾讯云）** 记录为 External Staging 的**首选供给方（preferred primary provider）**，理由：D1/D2/D3/D6 最强契合，且与已定的生产路径 A（腾讯云 TCR）保持生态一致，利于 staging→production 结构对称与失败域隔离验证。

**同时明确以下边界（fail-closed）**：
1. 本决策是**记录性**的（ADR + SSOT `provider_decision` 字段 + 审计类别 `provider decision recorded`），**不是真实绑定**。
2. 真实账号开通、AccessKey/SecretKey、预算批准、域名/证书、IdP tenant 等 **Track B 输入全部仍 `PENDING_EXTERNAL_STAGING_RESOURCE`**，须由主理人在人类终端、四角色真实签署后提供。
3. IaC 模板（T16/T17）**采用供给方无关（provider-agnostic）参数化写法**，以 `provider` 变量驱动；默认变量值指向腾讯云，但允许在真人 provisioning 时覆写为阿里云/AWS（O2/O3），不锁定代码。
4. AI 不调用任何云 SDK/API、不创建资源、不写密钥；所有 provisioning 步骤以 Runbook + IaC plan/dry-run 形式**就绪**，真实 apply 由真人持真实凭据执行（`StagingProvisioningExecutionMode.HUMAN_AUTHORIZED_APPLY`）。

---

## 5. Consequences（后果）

**正面**
- 8 资源计划（T7-T15）、成本模型（T6）、IaC（T17）有统一供给方语义锚点。
- 与生产路径 A 生态一致，staging→production parity 易验证。
- 决策可审计、可回溯（ADR + SSOT + 审计类别）。

**负面 / 约束**
- 真实绑定仍 PENDING，8 资源在 3.9.12 收口时仍为 `PENDING_EXTERNAL_STAGING_RESOURCE`（不伪造 verified）。
- 若主理人最终选择 O2/O3，IaC 需补充对应 provider 变量集（已在 T17 预留扩展点）。

**风险与缓解**
- R1（Provider 锁定过强）：以 provider-agnostic 模板 + 默认变量缓解。
- R2（AI 误执行真实 Provision）：`StagingProvisioningExecutionMode` 禁 AUTO/PRODUCTION；CI 与 API 均不含 execution 端点（复用 3.9.11 红线）。
- R3（Secret 泄漏）：复用 `credential_scanner.assert_no_credential_leak`，IaC/包/文档均不存明文。

---

## 6. Decision Record Mechanism（决策记录机制）

| 载体 | 位置 | 内容 |
|---|---|---|
| 本 ADR | `docs/adr/ADR-PHASE-3.9.12-EXTERNAL-STAGING-PROVIDER.md` | 完整决策与理由 |
| SSOT | `.ai/project_status.json` → `phase_3_9_12_external_staging_provisioning_status.provider_decision` | 摘要：`preferred=tencent_cloud; status=recorded_pending_human_binding` |
| 审计 | `provisioning_plan_generated` / `provider_decision_recorded`（3.9.12 允许的最小新增类别之一） | 决策动作留痕 |
| IaC | `infrastructure/staging/*.tf` / `*.yaml` 的 `variable "provider"` 默认 `tencent_cloud` | 代码层锚点 |

---

## 7. 后续（不在本 ADR 内完成）

- T16：IaC 策略 ADR（明确 Terraform/OpenTofu/Pulumi/CLI/Compose 选用与 provider-agnostic 写法）。
- T17：IaC 模板（参数化 `provider`，默认腾讯云）。
- T7-T15：8 资源 Provisioning 计划，按本 ADR 供给方语义编写。
- 真实绑定：主理人持真实凭据 + 四角色签署后，在真人 provisioning 时覆写 `provider` 变量并 `HUMAN_AUTHORIZED_APPLY`。
