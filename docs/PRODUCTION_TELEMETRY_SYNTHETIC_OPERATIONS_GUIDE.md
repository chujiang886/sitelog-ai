# BOIP 生产遥测接入适配与合成运维验证治理指南（Phase 3.9.4）

> 文档版本：Phase 3.9.4 收口版（2026-08-12）
> 状态：**BUILT_NO_GO**（已收口，等待主理人审核授权后精路径 commit）
> 配套：`.ai/reviews/phase3.9.4_telemetry_synthetic_operations_report.md`、`.ai/roadmap_v8.md` §35.4、`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §15

本指南说明「生产遥测接入适配与合成运维验证层」的设计意图、fail-closed 不变量、人工动作入口与收口纪律。它**只建适配层与合成演练，不真接入生产遥测源、不真发送告警、不自动回滚/关单、不替代 SRE**。

---

## 1. 概述与定位

Phase 3.9.4 是 3.9.x 生产发布前准备链的最后一环，承接 3.9.3（生产可观测性、SRE 与事故响应准备层）。它的目标不是「接入真实生产监控」，而是把「遥测接入」本身抽象成可替换、可验证、fail-closed 的适配层，并用**合成故障演练**验证事故响应链路在不接触真实生产数据的前提下能否正确跑通。

- 做：端口抽象（`TelemetryProvider`）+ 适配器（Synthetic / Prometheus / OpenTelemetry）+ 归一化 + 聚合 + 注册表 + 告警路由 + 合成故障演练编排 + API/前端只读展示 + 人工合成演练入口。
- 不做：不真接入真实遥测源；不真发送告警；不自动 ACK/RESOLVE/CLOSE/回滚；不自动执行 Runbook；不替代 SRE / incident-commander / production-owner。

---

## 2. 身份与权限边界

- 全部端点复用 3.9.3 已落地的权限词表（前后端逐字一致）：
  - `governance:observability:read`（OBSERVABILITY_READ）
  - `governance:incident:action`（INCIDENT_ACTION，仅 admin 可调用合成演练）
- 真实 USER 主体强制：任何写入/演练动作的 `actor_kind != "user"` 一律 403 或抛 `EnterpriseRedLineViolationError`。
- 组织隔离：`require_same_org` 默认拒绝跨组织访问。
- CSRF：所有非 GET 端点经 `csrf_protect` 依赖保护。

---

## 3. 十四项最高红线（fail-closed，AI 不可破）

1. `engineering_enabled` 必须 `false`（agents/config.yaml:102，本阶段未触碰）。
2. 禁输出 `engineering_approved`。
3. 禁 AI 自动批准发布。
4. 禁 AI 自动执行部署。
5. 禁 AI 自动回滚。
6. 禁 AI 改真实企业数据。
7. 禁 AI 写真实生产密钥。
8. 禁 AI 自动授真实权限。
9. 禁 AI 自动 ACK/RESOLVE/CLOSE Incident。
10. 禁代替 SRE / incident-commander / production-owner。
11. 禁把 Synthetic Telemetry 描述成真实 production。
12. 禁真实发送 PagerDuty / 企业微信 / Slack / Email 告警。
13. 禁自动执行 Runbook。
14. 禁为测试通过跳测试 / 删断言 / 降权 / 伪造证据。

不可真实验证项一律标 `pending_verification`，绝不编造真实外部数据。

---

## 4. 架构总览

```
TelemetryProvider (端口 ABC)
   ├─ SyntheticTelemetryProvider      （默认，演练用，绝不冒充真实源）
   ├─ PrometheusTelemetryProvider     （未配置真实源 → NOT_CONFIGURED，fail-closed）
   └─ OpenTelemetryTelemetryProvider  （未配置真实源 → NOT_CONFIGURED，fail-closed）
        │
        ▼
TelemetryNormalizer  → 统一为 production_observability/models.py 的 ServiceHealth / MetricSnapshot 等
TelemetryAggregator  → 多源聚合（仅合成源 → synthetic_only，不判 operational）
TelemetryProviderRegistry → 只返回真实已配置源；真实源缺失 → pending_verification
TelemetryAlertRouter → 合成源仅 SIMULATED_DELIVERY；未配置源 → NOT_CONFIGURED；禁真实外发
SyntheticFaultInjection + SyntheticFaultScenario → 合成故障注入与演练
ProductionTelemetryService → 编排入口（只读查询 / 巡检 / 合成演练 / 关联）
```

---

## 5. TelemetryProvider 端口契约

`agents/enterprise/telemetry/provider.py` 定义抽象基类 `TelemetryProvider`，强制子类实现：

- `provider_id` / `is_configured` / `provider_health`
- `query_health(...)` / `query_metrics(...)` / `query_logs(...)` / `query_traces(...)`
- `check(...)`（连通性与配置校验）

契约要点：

- `is_configured() == False` 时，所有 query 返回空 / `NOT_CONFIGURED`，**绝不抛「假装成功」的假数据**。
- 端口不绑定任何具体传输协议；Prometheus / OTel 适配器各自实现，便于后续真实接入时最小改动。

---

## 6. 适配器：Synthetic（默认）

`SyntheticTelemetryProvider` 是系统默认且唯一「开箱即用」的源：

- 通过 `set_scenario(SyntheticFaultScenario)` 切换健康/故障画像。
- 所有返回均带 `simulation_only=true` 与 `integrity_hash`，前端/API 显式标注「合成」。
- 它**只用于演练与开发验证**，不得被注册表当作真实生产源返回（见 §12）。

---

## 7. 适配器：Prometheus（未配置 fail-closed）

- 仅在 `PROMETHEUS_*` 真实连接参数齐全且连通校验通过时才 `is_configured=True`。
- 缺配置 / 连通失败 → `NOT_CONFIGURED`，所有 query 返回空，**不降级为 Synthetic**（红线⑪）。
- 真实接入由主理人在人类终端线下配置，当前 `pending_verification`。

---

## 8. 适配器：OpenTelemetry（未配置 fail-closed）

- 与 Prometheus 同构：`OTEL_*` 参数齐全且校验通过才 `is_configured=True`。
- 缺配置 / 失败 → `NOT_CONFIGURED`，空返回，不降级为 Synthetic。
- 真实接入 `pending_verification`。

---

## 9. TelemetryEnvelope 统一信封

所有 provider 返回经信封封装，含：

- `simulation_only`：合成标志（真实源恒 `false`）。
- `integrity_hash`：内容完整性哈希，防篡改 / 防伪造证据。
- `provider_kind` / `status` / `source` 元信息。

未配置真实源时信封为空 / `NOT_CONFIGURED`，绝不伪装。

---

## 10. TelemetryNormalizer 归一化（复用 production_observability 模型）

- 把信封统一归一化为 `production_observability/models.py` 的：
  - `ServiceHealth` / `ServiceHealthStatus`（HEALTHY / DEGRADED / UNHEALTHY / UNKNOWN）
  - `MetricSnapshot` / `MetricCategory`
- 归一化只做结构映射，不改 `simulation_only` 语义；未知状态→`UNKNOWN`，**绝不回退 HEALTHY**。
- 复用既有业务对象，避免遥测层与可观测性层模型漂移。

---

## 11. TelemetryAggregator 聚合（synthetic_only 不判 operational）

- 多源聚合产出整体健康结论：
  - 全部 operational 且**非全合成** → `operational`
  - 含未配置源 → `partial_not_configured`
  - 仅合成源 → **`synthetic_only`**（**红线⑪：合成源绝不等价于 production operational**）
- 该分支是 3.9.4 修复的真实 bug（原实现在仅合成源时误判 `operational`），已在 `health.py` 更正。

---

## 12. TelemetryProviderRegistry 注册表（真实源不 fallback）

- `get_production_provider(kind)` 仅返回**真实且已配置**的源。
- 合成源**不 fallback** 顶替真实源；即便 synthetic 已注册也不作为 `production_providers()` 的真实候选。
- 真实源缺失 → `pending_verification=True`，由主理人线下补齐。

---

## 13. TelemetryAlertRouter 告警路由（仅模拟投递 / 不真实外发）

`AlertDeliveryStatus` 两态：

- `SIMULATED_DELIVERY = "simulated_delivery"`：合成源演练用，**仅模拟投递**，不触真实通道。
- `NOT_CONFIGURED = "not_configured"`：路由目标未配置（fail-closed），绝不静默丢弃也不外发。

- `NullAlertRoutingProvider`：未配置路由目标 → 返回 `NOT_CONFIGURED`。
- `SyntheticAlertRoutingProvider`：演练用，仅返回 `SIMULATED_DELIVERY`。
- **红线⑫**：绝对禁止真实发送 PagerDuty / 企业微信 / Slack / Email。

---

## 14. SyntheticFaultScenario 合成故障场景

`SyntheticFaultScenario`（models.py）目录（阈值仅用于 test fixture，禁止写成真实生产阈值）：

| 场景 | 含义 |
|------|------|
| `backend_latency` | 后端延迟升高 |
| `backend_error_spike` | 后端错误率突增 |
| `database_unavailable` | 数据库不可用 |
| `identity_authentication_failure` | 身份认证失败 |
| `permission_denial_spike` | 权限拒绝突增 |
| `llm_timeout` | 大模型推理超时 |
| `asr_unavailable` | 语音识别不可用 |
| `tts_unavailable` | 语音合成不可用 |
| `release_regression` | 发布回归 |
| `audit_unavailable` | 审计服务不可用 |
| `governance_backlog` | 治理积压 |
| `healthy` | 基线健康（无故障） |

`SyntheticFaultInjection.inject(...)` 将场景转化为异常健康画像 → 归一化 → 聚合 → 告警路由 → 关联，全链路验证。

---

## 15. ProductionTelemetryService 编排入口

`agents/enterprise/telemetry/service.py` 的 `ProductionTelemetryService` 暴露：

- `list_providers()` / `get_synthetic_scenarios()`：只读列举。
- `check_provider(id)`：连通性巡检（OBSERVABILITY_READ，落审计 `TELEMETRY_PROVIDER_CHECKED`）。
- `query_and_normalize(...)`：只读查询 + 归一化。
- `summarize()`：聚合健康摘要（含 `synthetic_only` 分支）。
- `run_synthetic_incident_drill(...)`：合成演练（INCIDENT_ACTION，USER 强制，生产环境 403）。
- `correlate_release` / `correlate_recovery_drill` / `correlate_security_signals`：关联发布/恢复/安全信号，均 `auto_*: false` + `pending_verification` + `simulation_only`。

服务构造即接 `AuditService(org_id)` 与 `identity=None`，`safety_invariants_ok()` 守护 `engineering_enabled=False`。

---

## 16. 合成 Incident 演练全链路

`run_synthetic_incident_drill` 标准管线（fail-closed）：

1. **injection**：`SyntheticFaultInjection.inject` 将场景转为异常健康画像；**真实 Provider 一律拒绝注入**（仅 Synthetic 可注入）。
2. **normalize**：异常 → `UNHEALTHY`/`DEGRADED` 归一化（不改 `simulation_only`）。
3. **aggregate**：整体结论随源而定；若仅合成源 → `synthetic_only`。
4. **alert**：`TelemetryAlertRouter` → `SIMULATED_DELIVERY`（仅模拟，不真实外发）。
5. **incident**：生成 `status=open` 的合成 Incident，`auto_rollback/auto_resolve/auto_close/auto_acknowledge` 全 `False`。
6. **correlate**：关联发布/恢复/安全信号，仅只读引用 + `pending_verification`。
7. **human close**：仅真实 USER 的 `close` 动作后 → `closed_by_human`；AI 主体 403。

返回值显式声明 `delivery=simulated_delivery`、`auto_rollback=False` 等，杜绝「看起来自动处理了」的误导。

---

## 17. API：governance_telemetry.py（9 路由 + 生产环境 403）

`backend/app/api/governance_telemetry.py` 注册于 `app.include_router`，前缀 `/governance/telemetry`：

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/providers` | OBSERVABILITY_READ | 列举 providers |
| GET | `/summary` | OBSERVABILITY_READ | 聚合摘要 |
| GET | `/{provider_id}/health` | OBSERVABILITY_READ | 健康 |
| GET | `/{provider_id}/metrics` | OBSERVABILITY_READ | 指标 |
| GET | `/{provider_id}/traces` | OBSERVABILITY_READ | 链路 |
| GET | `/{provider_id}/logs` | OBSERVABILITY_READ | 日志 |
| GET | `/synthetic/scenarios` | OBSERVABILITY_READ | 合成场景目录 |
| POST | `/{provider_id}/check` | OBSERVABILITY_READ | 巡检（落审计） |
| POST | `/synthetic/run` | INCIDENT_ACTION（仅 admin） | 合成演练；`is_production=True` → 403 |

所有非 GET 经 `csrf_protect`；`actor_kind != "user"` → 403；`EnterpriseRedLineViolationError` → 403。

---

## 18. 前端：governance-observability 页扩展

`frontend/src/app/governance-observability/page.tsx` 在 3.9.3 只读看板基础上扩展「生产遥测接入与合成运维验证」区块：

- Provider 卡片 + **SYNTHETIC / PRODUCTION 徽章**：`isProductionProvider = kind != synthetic && status == configured && simulation_only == false` 才显示 PRODUCTION；其余一律 SYNTHETIC。
- `engineering_enabled` 状态徽章（恒 false 显示）。
- 「合成故障演练（E2E Drill）」区块：scenario 下拉 + 运行按钮（需 `governance:incident:action`）+ 结果 fail-closed 声明展示（`auto_*=false`、`delivery=simulated_delivery`、`status=open`），**无 Auto Fix / Rollback / Resolve / Close / AI Approve 按钮**。

tsc 0 error / jest 117 passed。

---

## 19. 审计集成（+4 枚举，actor 强制 USER）

`agents/enterprise/audit.py` 新增 4 类（actor_kind 恒 USER，归属经 Task 0 正式确权）：

- `TELEMETRY_PROVIDER_CHECKED`
- `SYNTHETIC_DRILL_STARTED`
- `SYNTHETIC_DRILL_COMPLETED`
- `TELEMETRY_EVIDENCE_RECORDED`

审计总数 **96 → 100**，与 `.ai/baselines/phase3.8_governance_release_baseline.json` 的 `audit_category_contract.total = 100` 一致；治理仓库完整性检查器 9/9 通过。

---

## 20. 测试与 CI 门禁（telemetry-quality-gate.yml 4 job）

- `tests/agents/test_enterprise_telemetry_core.py`（29 例）：normalizer / aggregator / registry / alert_routing / Prometheus+OTel 未配置 fail-closed / service 只读。
- `tests/agents/test_enterprise_synthetic_drill.py`：E2E drill 全链路 + 注入拒真实源 / healthy→无 incident / human close→closed_by_human / 关联 `auto_*=false` / `synthetic_only` 不 operational。
- `backend/tests/test_governance_telemetry.py`（28 例）：401/legacy-header 拒绝、权限矩阵、UNKNOWN→404、synthetic 归一化、INCIDENT_ACTION 仅 admin、非法 scenario→400、生产环境合成演练 403、check 落审计。

CI `.github/workflows/telemetry-quality-gate.yml` 4 个 job（unit-and-contract / api / scanners / regression），任一失败整条失败（fail-closed）：

- 全 agents 套件 **2373 passed / 0 failed**（零回归）。
- backend 374 run / 373 passed（1 例 `test_jwt_verifier_config_missing_secret_fails_closed` 为 3.8.28 身份代码既有失败，与 3.9.4 无关，已验证在 9201a7d 基线上同样失败）。
- frontend jest 117 passed；tsc 0 error。
- 治理完整性 9/9；生产安全 7/7；身份头 0 命中；硬编码 0 命中（telemetry 交付物）；防编造扫描仅命中历史 `wind_pressure` 文档（零本阶段交付物）。

---

## 21. SSOT / 收口状态 / STOP 纪律

- **SSOT**：`.ai/project_status.json` 已登记 `phase_3_9_4_status`（`BUILT_NO_GO`）+ `phase_3_9_4` 嵌套块；`engineering_enabled=false` 零翻转；`.ai/roadmap_v8.md` §35.4 同步。
- **收口状态**：🟢 **BUILT_NO_GO**（2026-08-12）。
- **STOP**：不进入 Phase 3.9.5+ 的「真接入 / 真外发」阶段——不真接入生产遥测源（Prometheus/OpenTelemetry/Loki 等需主理人线下配置）、不真发送告警、不自动修复/回滚/关单/执行 Runbook、不自动开启 `engineering_enabled`，不输出 `engineering_approved`。
- 本阶段产物待主理人审核授权后精路径 commit（telemetry 包 + 测试 + API/前端 + 审计 + SSOT + 部署指南 §15 + 本指南 + 36 节收口报告）。
- 真实遥测接入、真实告警外发、真实事故指挥/回滚/恢复执行只能源于主理人 / SRE / incident-commander 在人类终端的线下决策。

---

> 附录：本层 `forbidden.py` 含 **102** 项禁名（`send_real_pagerduty_alert` / `send_real_wechat_alert` / `auto_rollback_incident` / `auto_resolve_incident` / `auto_close_incident` / `execute_runbook` / `act_as_sre` / `fabricate_telemetry_evidence` 等），结构级调用即抛；与 3.8.29/3.9.2/3.9.3 的 fail-closed 禁名共同构成 AI 不可破的红线网。
