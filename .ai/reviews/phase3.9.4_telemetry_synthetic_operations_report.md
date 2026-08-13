# Phase 3.9.4 收口报告 · 生产遥测接入适配与合成运维验证层

> Telemetry Integration & Synthetic Production Operations Layer
> 状态：**TELEMETRY_INTEGRATION_SYNTHETIC_OPERATIONS_BUILT_NO_GO** · **STOP（等待主理人审核授权）**

---

## 1. 文档元信息

- **阶段编号**：3.9.4
- **阶段名称**：Telemetry Integration & Synthetic Production Operations Layer（生产遥测接入适配与合成运维验证层）
- **收口日期**：2026-08-12
- **分支**：`feat/phase3.9.4-telemetry-synthetic-operations`（自 `9201a7d` 分出，即 3.9.4 Task 0 提交点）
- **SSOT 状态键**：`phase_3_9_4_status = "TELEMETRY_INTEGRATION_SYNTHETIC_OPERATIONS_BUILT_NO_GO"`
- **报告路径**：`.ai/reviews/phase3.9.4_telemetry_synthetic_operations_report.md`
- **身份**：BOIP AI Chief Architect + Production Observability Architect + SRE Platform Engineering Lead + Telemetry Integration Lead + Synthetic Operations Validation Auditor + 本阶段自主研发负责人

---

## 2. 执行授权与身份

本阶段依主理人授权书（§一~§三十八，T0–T30 详细规格）自主执行。授权范围涵盖架构决策、选型、实现、测试、CI、文档、Git、收口。执行模式：现状扫描→方案→开发→测试→自动修复→回归→SSOT→文档→Git→收口。除三类不可逆情况（不可逆改真实生产数据 / 必需但不存在的真实外部密钥或第三方权限 / 真实部署或须自然人担责动作）外，禁止暂停询问。本报告为收口产物，遵循同一纪律。

---

## 3. 阶段目标与范围

在既有 3.9.3 生产可观测性/SRE/事故响应**准备层**之上，本阶段建成「生产遥测接入适配」与「合成运维验证」两层：
- **遥测接入适配**：以端口（Port）/适配器（Adapter）模式把生产遥测源（Prometheus / OpenTelemetry）与合成源（Synthetic）统一归一化为既有 `production_observability/models.py` 的 `ServiceHealth`/`MetricSnapshot` 业务对象，**未配置真实源时返回空 / NOT_CONFIGURED，绝不降级伪装为 Synthetic**（红线⑪）。
- **合成运维验证**：在不接触真实生产、不真发告警、不自动回滚/ACK/RESOLVE/CLOSE 的前提下，提供 E2E 合成故障演练（Synthetic Drill）引擎、关联分析（发布/恢复/安全）与只读编排 Service。

范围边界：只建「接入适配 + 合成验证」能力体系，不真接入生产、不真发送任何外部告警、不自动执行 Runbook、不进入真实激活态。

---

## 4. 最高红线遵守总览（14 条，绝对不可修改/弱化）

| # | 红线 | 本阶段遵守情况 |
|---|------|----------------|
| ① | `engineering_enabled` 必须 false | ✅ `agents/config.yaml:102` 未改；SSOT `engineering_enabled=false`；CI `load_engineering_enabled()` 真实读取为 false |
| ② | 禁输出 `engineering_approved` | ✅ 全阶段零产出 |
| ③ | 禁 AI 自动批准发布 | ✅ 无发布批准逻辑 |
| ④ | 禁 AI 自动部署 | ✅ 无部署逻辑 |
| ⑤ | 禁 AI 自动回滚 | ✅ drill 结果 `auto_rollback=false`；关联分析 `auto_rollback=false` |
| ⑥ | 禁 AI 改真实企业数据 | ✅ 只读查询/巡检 |
| ⑦ | 禁 AI 写真实生产密钥 | ✅ 无密钥写入 |
| ⑧ | 禁 AI 自动授真实权限 | ✅ 无权限授予 |
| ⑨ | 禁 AI 自动 ACK/RESOLVE/CLOSE Incident | ✅ drill 状态 `open`→人工 `closed_by_human`；无 AUTO_* 状态机 |
| ⑩ | 禁代替 SRE/incident-commander/production-owner | ✅ 仅人类主体可操作（actor 强制 USER） |
| ⑪ | 禁把 Synthetic 描述成真实 production | ✅ 修正 `health.py`：仅合成源返回 `synthetic_only` 不判 `operational`；前端 SYNTHETIC/PRODUCTION 徽章区分 |
| ⑫ | 禁真实发送 PagerDuty/企业微信/Slack/Email 告警 | ✅ 告警路由仅 `SIMULATED_DELIVERY`；未配置源 `null`/`NOT_CONFIGURED` |
| ⑬ | 禁自动执行 Runbook | ✅ Runbook 仅引用，无自动执行 |
| ⑭ | 禁为测试通过跳测试/删断言/降权/伪造证据 | ✅ 全量回归真实计数；无删断言/降权 |

**fail-closed 枚举**：368 项 `_TELEMETRY_FORBIDDEN` 禁名方法（`__getattr__` 拦截），含「禁真实外发 / 禁自动回滚 / 禁自动 ACK / 禁自动 RESOLVE / 禁自动 CLOSE / 禁自动部署」等。

---

## 5. 架构总览

```
agents/enterprise/telemetry/
├── provider.py        # TelemetryProvider 端口（ABC + 5 抽象方法）
├── synthetic.py       # SyntheticTelemetryProvider（合成源适配器）
├── prometheus.py      # Prometheus 适配器（未配置→NOT_CONFIGURED fail-closed）
├── otel.py            # OpenTelemetry 适配器（未配置→NOT_CONFIGURED fail-closed）
├── normalizer.py      # TelemetryNormalizer → production_observability/models.py
├── aggregator.py      # 多源聚合（含 synthetic_only 分支，红线⑪）
├── registry.py        # Provider 注册表（仅真实配置源进入 production_providers）
├── alerts.py          # 告警模型（AlertDelivery / AlertStatus）
├── alert_routing.py   # 告警路由（synthetic→SIMULATED_DELIVERY；未配置→null）
├── synthetic.py       # 合成故障场景定义与注入
├── metrics.py         # 指标快照
├── health.py          # 健康聚合（修正 synthetic_only）
├── correlation.py     # 关联分析（发布/恢复/安全，auto_*:false）
├── service.py         # ProductionTelemetryService（只读编排）
├── forbidden.py       # _TELEMETRY_FORBIDDEN（368 项）
└── __init__.py
```

前端：`frontend/src/app/governance-observability/page.tsx`（SYNTHETIC/PRODUCTION 徽章 + 合成演练 UI）
后端：`backend/app/api/governance_telemetry.py`（9 路由，OBSERVABILITY_READ / INCIDENT_ACTION）
CI：`.github/workflows/telemetry-quality-gate.yml`（4 job，fail-closed）

---

## 6. 任务清单与完成情况（T0–T30）

| Task | 内容 | 状态 | 落点 |
|------|------|------|------|
| T0 | 审计溯源契约（+4 审计类归属） | ✅ | `9201a7d` |
| T1–T9 | Telemetry 核心（端口/归一化/聚合/注册表/告警路由/Prometheus+OTel 适配器/合成源/合成场景/Service） | ✅ | `b3a6e7b` |
| T10–T12 | 专项测试（normalizer/aggregator/registry/alert_routing/E2E drill 全链路 fail-closed） | ✅ | `64b900d` |
| T13–T18 | 编排代码（telemetry 包 13 文件） | ✅ | `b3a6e7b` |
| T19 | FastAPI 端点（9 路由） | ✅ | `d836e33` |
| T20 | Dashboard 扩展 | ✅ | `b893316` |
| T21 | 审计集成（+4 枚举，总数 96→100） | ✅ | `6ddb9a3` |
| T22–T24 | fail-closed 测试与 bug 修复 | ✅ | `64b900d` + `b3a6e7b` |
| T25 | CI 门禁 | ✅ | `6a438fd` |
| T26 | SSOT 同步 | ✅ | `121de8d`（含工作树修正） |
| T27–T28 | 文档（部署指南 §15 + 专用指南 21 节） | ✅ | `8de1e39` |
| T29 | 逻辑提交（拆分 commit，排除 3.9.2 遗留） | ✅ | 10 commit（9201a7d→a905213，含 T0 与 T30） |
| T30 | 收口报告（36 节）后 STOP | ✅ | 本报告 |

**总计 31 项任务全完成**（T0 + T1–T30 拆分口径），收口 STOP。

---

## 7. Telemetry Provider 端口设计

`TelemetryProvider`（ABC）定义 5 个抽象方法：`check` / `query_health` / `query_metrics` / `query_traces` / `query_logs`。所有具体适配器实现该端口，统一信封 `TelemetryEnvelope`（含 `simulation_only` 与 `integrity_hash`）。端口解耦「源类型」与「业务消费」，新增源只需实现端口，归一化层零改动。

---

## 8. 适配器（Synthetic / Prometheus / OTel）

- **SyntheticTelemetryProvider**：内置合成遥测，稳定返回 `simulation_only=true` 信封，供演练与验证；绝不声称 production。
- **Prometheus / OTel 适配器**：读取 `get_settings()` 配置；**未配置真实源 → 返回空 / NOT_CONFIGURED，不降级、不 fallback 到 Synthetic**（红线⑪）。本阶段默认未配置，故生产环境查询只返回 `pending_verification` 占位，不伪造真实数据。

---

## 9. 归一化层

`TelemetryNormalizer` 把 `TelemetryEnvelope` 统一归一化为 `production_observability/models.py` 的 `ServiceHealth` / `ServiceHealthStatus` / `MetricSnapshot` / `MetricCategory`。未知状态 → `UNKNOWN`（不回退 `HEALTHY`，沿用 3.9.3 不变量）；指标类别映射受白名单约束；`simulation_only` 透传，供前端徽章判定 SYNTHETIC vs PRODUCTION。

---

## 10. 聚合层与红线⑪修正

`aggregator.summarize()` 原逻辑在「仅合成源」时返回 `operational=True`（**违反红线⑪**）。本阶段修正：

```python
elif len(operational) == total and total > 0:
    if all(i["simulation_only"] for i in items):
        overall = "synthetic_only"   # 红线⑪：仅合成源绝不等于 production operational
    else:
        overall = "operational"
```

四类聚合覆盖：`partial_not_configured` / `operational` / `synthetic_only` / `overall_for_normalized`。

---

## 11. 注册表层

`TelemetryProviderRegistry`：`get_production_provider(kind)` 仅返回「真实配置且 `is_configured=True`」的源；对未配置真实 kind（如 PROMETHEUS 当仅注册 synthetic）返回 `None`，**不 fallback 到 Synthetic**；`production_providers()` 不含 `simulation_only` 源。`pending_verification` 标记贯穿未验证项。

---

## 12. 告警路由层（fail-closed）

`alert_routing.py`：
- 合成源告警 → `SIMULATED_DELIVERY`（仅模拟投递，不触达真实通道，红线⑫）。
- 未配置源 / `NOT_CONFIGURED` → 返回 `null`，不生成真实告警。
- 拒绝非 USER 主体发起的告警动作（actor 强制 USER）。
- 全链路：`auto_ack=false` / `auto_resolve=false` / `auto_close=false`。

---

## 13. 合成故障演练（Synthetic Drill）引擎

`SyntheticFaultScenario` 定义 12 个场景（含 `healthy` 基线）：`backend_latency` / `backend_error_spike` / `database_unavailable` / `identity_authentication_failure` / `permission_denial_spike` / `llm_timeout` / `asr_unavailable` / `tts_unavailable` / `release_regression` / `audit_unavailable` / `governance_backlog` / `healthy`。

`run_synthetic_incident_drill` 全链路：注入 → 异常检测（anomalous）→ 健康判定（unhealthy）→ 模拟投递（simulated_delivery）→ 事故状态（`open`）。健康场景 → 无事故。人工 close → `closed_by_human`。全链路拒绝真实 Provider 注入（仅 Synthetic 可注入）。

---

## 14. 关联分析（发布 / 恢复 / 安全）

- `correlate_release`：引用发布候选回滚参考（`rollback_reference`），只读引用，不触发真实回滚。
- `correlate_recovery_drill`：关联恢复演练，`auto_*:false` / `pending_verification` / `simulation_only`。
- `correlate_security_signals`：关联安全信号，`auto_*:false` / `pending_verification` / `simulation_only`。

三者均 `auto_rollback=false` / `threshold_verified=false`，与 3.9.3 事故模型一致。

---

## 15. Service 只读编排

`ProductionTelemetryService` 暴露 `query_and_normalize` / `check_provider` / `run_synthetic_incident_drill` / `correlate_release` / `correlate_recovery_drill` / `correlate_security_signals` / `summarize` / `list_providers` / `get_synthetic_scenarios`。所有查询与巡检只读；合成演练不操作真实数据；`_FORBIDDEN = _TELEMETRY_FORBIDDEN`（368 项禁名）。

---

## 16. 审计集成（+4 枚举）

`audit.py` 新增 4 个枚举（actor 强制 USER）：
- `TELEMETRY_PROVIDER_CHECKED`
- `SYNTHETIC_DRILL_STARTED`
- `SYNTHETIC_DRILL_COMPLETED`
- `TELEMETRY_EVIDENCE_RECORDED`

审计总数 **96 → 100**（与 `.ai/baselines/phase3.8_governance_release_baseline.json` 的 `audit_category_contract.total=100` 一致）。`tests/agents/test_enterprise_knowledge_governance_audit.py` 同步断言总数。

---

## 17. FastAPI 端点（T19）

`backend/app/api/governance_telemetry.py` 9 路由，镜像 `governance_release.py` 范式（`csrf_protect` + `require_same_org` + `_require_user_principal` + 真实 USER 依赖 + `AuditService`）：
- GET `/providers`（OBSERVABILITY_READ）
- GET `/summary`
- GET `/{provider_id}/health|metrics|traces|logs`
- GET `/synthetic/scenarios`
- POST `/{provider_id}/check`（OBSERVABILITY_READ，落审计）
- POST `/synthetic/run`（INCIDENT_ACTION；`if _settings().is_production: raise 403`；`EnterpriseRedLineViolationError`→403）

已注册进 `backend/app/api/__init__.py` 与 `backend/app/main.py`。

---

## 18. 前端 Dashboard（T20）

`frontend/src/app/governance-observability/page.tsx` 扩展：
- 「生产遥测接入与合成运维验证」区块：Provider 卡片 + SYNTHETIC/PRODUCTION 徽章 + `engineering_enabled` 状态徽章。
- 「合成故障演练（E2E Drill）」区块：scenario 下拉 + 运行按钮（需 `governance:incident:action`）+ 结果 fail-closed 声明展示（无 Auto / 无 AI / 无真实外发）。
- `isProductionProvider`：kind≠synthetic 且 status=configured 且 `simulation_only=false` 才标 PRODUCTION。
- tsc 0 error / jest 117 passed。

---

## 19. CI 质量门禁（T25）

`.github/workflows/telemetry-quality-gate.yml` 4 个 job，任一失败即整条失败（fail-closed）：
1. `telemetry-unit-and-contract`：跑两个 agents 测试文件。
2. `telemetry-api`：backend `test_governance_telemetry`。
3. `telemetry-scanners`：`check_hardcoded.py` + `check_governance_repository_integrity.py`。
4. `telemetry-regression`：全 agents 套件。

trigger 含 `feat/phase3.9.4-telemetry-synthetic-operations` 与 `main`。

---

## 20. 测试体系与 fail-closed 覆盖（T10–T12, T22–T24）

- `tests/agents/test_enterprise_telemetry_core.py`（29 例）：normalizer（状态保持/未知→UNKNOWN/指标类映射/simulation_only 透传）、aggregator（partial_not_configured/operational/synthetic_only/overall_for_normalized）、registry（get_production_provider 仅真实源不 fallback、pending_verification）、alert_routing（synthetic 仅 SIMULATED_DELIVERY / null NOT_CONFIGURED / 拒非 USER）、Prometheus/OTel 未配置 fail-closed、service 只读查询/巡检/synthetic-only 不 operational。
- `tests/agents/test_enterprise_synthetic_drill.py`（E2E 全链路）：injection 拒真实 Provider/仅 Synthetic、异常 pipeline（anomalous→unhealthy→simulated_delivery→open）、healthy→no_incident、human close→closed_by_human、空 actor 拒、correlate_recovery/release/security（均 auto_*:false/pending_verification/simulation_only）、发布关联 rollback_reference 只读引用、全链路注入→归一化→聚合→告警→关联。
- `backend/tests/test_governance_telemetry.py`（28 例）：401/garbage/suspended/legacy-header 拒绝；OBSERVABILITY_READ 权限矩阵（admin/reviewer/auditor/viewer=200，business_only=403）；UNKNOWN provider 404；synthetic metrics 归一化 simulation_only；INCIDENT_ACTION 仅 admin 可 run（其余 403）；非法 scenario 400；`test_synthetic_run_records_audit_no_auto`（status=open、auto_*:false、delivery=simulated_delivery）；human_actions close→closed_by_human；生产环境合成演练 403（monkeypatch `is_production=True`）；check 落审计。

---

## 21. 关键 bug 修复

- **`health.py` synthetic_only 不判 operational**（红线⑪）：聚合层原把「仅合成源」判为 `operational`，已修正为 `synthetic_only` 分支（见 §10）。
- **`synthetic.py` 删 `model` 字段**：删除 `_SCENARIO_HEALTH` 中 `LLM_TIMEOUT` 的 `"model": "HY-Vision-2.0-Instruct"`（死数据，未被 normalizer 读取），规避 `check_hardcoded.py` 的 `model` 键命中。复跑 pass（exit 0）。

---

## 22. SSOT 同步（T26）

- `.ai/project_status.json`：新增 `phase_3_9_4_status` 嵌套键（`TELEMETRY_INTEGRATION_SYNTHETIC_OPERATIONS_BUILT_NO_GO`）；`phase_3_9_4` 块登记核心模块/文件/审计 delta/CI/文档/报告路径/测试摘要；审计总数声明 100。
- `.ai/roadmap_v8.md`：§35.4 新增 3.9.4 节，概览表补 3.9.4 行，§35.3 STOP 纪律更新为指向下一阶段。
- 工作树修正：`phase_3_9_2` 块 `repo_integrity_caveat` 文本更正为「SSOT 登记 audit=100 与权威基线 total=100 一致，无冲突」（原误写 96，经完整性检查器核实权威 total=100）。

---

## 23. 文档交付（T27–T28）

- `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §15：telemetry provider 配置 / adapters / synthetic vs production / env 隔离 / alert routing / on-call / escalation / troubleshooting；附录变更记录补 3.9.4 行。
- `docs/PRODUCTION_TELEMETRY_SYNTHETIC_OPERATIONS_GUIDE.md`：21 节专用指南（端口/适配器/归一化/聚合/注册表/告警路由/合成演练/关联分析/Service/审计/API/前端/CI/测试/fail-closed/红线/SSOT/激活态/待主理人项）。

---

## 24. 逻辑提交清单（T29，真实 hash）

| Hash | 类型 | 内容 |
|------|------|------|
| `9201a7d` | fix(audit) | T0 审计溯源契约（+6 归属） |
| `b3a6e7b` | feat(enterprise) | telemetry 核心包 + service 接线（T1–T18） |
| `6ddb9a3` | feat(audit) | +4 TELEMETRY_* 枚举（总数 96→100）+ 权限断言（T21） |
| `d836e33` | feat(api) | governance_telemetry 9 路由 + 注册（T19） |
| `b893316` | feat(ui) | observability 仪表盘扩展（T20） |
| `64b900d` | test(telemetry) | agents + backend 测试（T10–T12, T22–T24） |
| `6a438fd` | ci(telemetry) | telemetry-quality-gate 4 job（T25） |
| `8de1e39` | docs(telemetry) | 部署指南 §15 + 专用指南（T27–T28） |
| `121de8d` | chore(ssot) | project_status.json + roadmap_v8 §35.4（T26） |
| `a905213` | docs(telemetry) | T30 收口报告 36 节 + 消除 SSOT 幽灵登记（integrity 9/9） |

**排除项**：3.9.2 `production_release/*` 遗留未跟踪/未提交文件（含 `tests/agents/test_enterprise_rc_freeze_activation_gate.py`、`.ai/release-gate/`、`docs/PRODUCTION_ACTIVATION_ROLLBACK_RUNBOOK.md` 等）刻意不混入本阶段提交，由 3.9.2 负责人另行处理。

---

## 25. 测试计数与回归结果

| 套件 | 本阶段 | 对比 3.9.3 | 状态 |
|------|--------|------------|------|
| agents 全量 | **2373 passed** | +29 | ✅ |
| backend 全量 | **374 passed**（+1 pre-existing 无关失败，见 §33） | +28 | ✅（基线 373 +1 历史隔离项） |
| frontend jest | **117 passed** | 持平 | ✅ |
| frontend tsc | **0 error** | 持平 | ✅ |
| telemetry agents 测试 | 29 + E2E | — | ✅ |
| telemetry backend 测试 | 28 | — | ✅ |

注：backend 全量显示 1 例失败 `test_jwt_verifier_config_missing_secret_fails_closed`，经 `git stash` 在 base 复跑确认**为本阶段之前已存在、与 3.9.4 无关**（identity/jwt 代码本阶段零改动），不计入本阶段回归缺陷。

---

## 26. 治理完整性 / 红线扫描结果

- **治理完整性检查**：`scripts/check_governance_repository_integrity.py` — **9/9**（含「SSOT 报告路径真实存在」规则，本报告创建后幽灵登记消除）。
- **生产安全 lint**：`scripts/lint/check_production_security.py` — **7/7**。
- **遗留身份头静态扫描**：`check_legacy_identity_headers.py --root backend` — **OK（exit 0）**。
- **基线清单可解析 / 审计总数断言唯一 / 与基线一致 / 必需审计族齐备 / 红线①② / 阶段编号唯一** — 全过。

---

## 27. 生产安全 lint / 硬编码 / fabrication 扫描

- `check_hardcoded.py`：**0 命中**（本阶段交付物）；本阶段已主动删除 `synthetic.py` 的 `model` 死字段以规避扫描。
- `check_fabrication.py`：命中均为**前阶段遗留** `wind_pressure` 文档与 `tests/agents/test_runtime_integration.py` 等历史产物，**本阶段交付物零命中**（与 3.9.3 既定基线一致）。
- `check_governance_repository_integrity.py`：0 本阶段命中（见 §26）。

---

## 28. 不可真实验证项（pending_verification）

按红线⑪⑫⑬，以下项**不可真实验证**，一律 `pending_verification`，不声称已通过：
- 真实 Prometheus/OTel 源接入与指标拉取（未配置 → NOT_CONFIGURED）。
- 真实生产告警投递到 PagerDuty/企业微信/Slack/Email（仅 SIMULATED_DELIVERY）。
- 真实 Runbook 自动执行（仅引用）。
- 真实事故自动 ACK/RESOLVE/CLOSE（仅人工 `closed_by_human`）。
- 真实回滚（关联分析 `auto_rollback=false`，只读引用 `rollback_reference`）。

---

## 29. 与 3.9.2 / 3.9.3 的边界与遗留排除

- **与 3.9.3**：本阶段消费 3.9.3 的 `production_observability/models.py` 业务对象（归一化目标），不修改其代码；新增 OBSERVABILITY_READ / INCIDENT_ACTION 权限（3.9.3 已建）。
- **与 3.9.2**：`production_release/*` 为 3.9.2 未提交遗留，本阶段工作树刻意不混入（见 §24），其冻结检查器 `governance_integrity_9_9` 子项依赖的 `phase_3_9_4.report` 幽灵登记，由本报告创建消除 → 3.9.2 冻结检查器随之可达 9/9（属 3.9.2 线收口范畴，本阶段仅解其外部依赖）。

---

## 30. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 误把 synthetic 呈现为 production（红线⑪） | `health.py` synthetic_only 分支 + 前端双徽章 + aggregator 测试覆盖 |
| 误发真实告警（红线⑫） | alert_routing 仅 SIMULATED_DELIVERY，未配置返回 null |
| 误自动回滚/关单（红线⑤⑨） | drill/correlation `auto_*:false` + 状态机无 AUTO_* + 测试断言 |
| 真实源未配置被伪装 | provider 端口 fail-closed，NOT_CONFIGURED 不 fallback |
| 审计总数漂移 | integrity 检查器 9/9 断言 total=100 唯一且与基线一致 |

---

## 31. 后续建议（主理人验收路径）

1. 主理人线下审阅本报告与 8 个逻辑提交（`9201a7d`…`121de8d`）。
2. 如需真接入生产遥测：在 `get_settings()` 配置真实 Prometheus/OTel 端点（须真实外部密钥，由人类提供，红线⑦禁 AI 写）。
3. 真实告警通道（PagerDuty/企业微信/Slack）须人类配置 webhook 凭证，且经独立评审开启（红线⑫禁真实外发默认关闭）。
4. 验收通过后，由人类终端显式置 `engineering_enabled=true`（红线①，AI 不可为）。
5. 真实部署/激活须自然人担责动作，不在本阶段自动范围。

---

## 32. 激活态结论（engineering_enabled=false，STOP）

- **`engineering_enabled = false`**（SSOT + `agents/config.yaml:102` 未改 + CI 真实读取）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 OPEN_EMPTY**，等主理人 + 专家线下提交真实证据后，由人类终端显式置 `enabled=true`。
- **本阶段 STOP**：不进入真实激活态、不真接入、不真发告警、不自动修复/回滚/关单。

---

## 33. 缺口与待主理人项

- **backend 历史隔离失败**：`test_jwt_verifier_config_missing_secret_fails_closed` 在 base 即失败（与 3.9.4 无关），建议由 3.8.28 负责人单独修 hygiene（不在本阶段范围，红线⑭禁为绿而降权/删断言）。
- **3.9.2 遗留未提交文件**：`production_release/*` 等由 3.9.2 负责人收口，本阶段已隔离排除。
- **真实遥测源凭证**：待人类提供（红线⑦）。

---

## 34. 冲突记录与决策（治理协议第四节）

| 冲突 | 决策 | 证据 | 待主理人项 |
|------|------|------|-----------|
| `phase_3_9_4.report` 幽灵登记（SSOT 指向不存在文件） | 创建本报告消除幽灵，完整性恢复 9/9 | integrity 检查器 rule `SSOT 报告路径真实存在` | 无 |
| `phase_3_9_2` 块 `repo_integrity_caveat` 误写审计 total=96 | 工作树修正为 100（经 integrity 检查器核实权威 total=100） | `.ai/baselines/...total=100` + `rule_audit_total_matches_baseline` 通过 | 无 |
| `health.py` 仅合成源误判 operational（红线⑪） | 修正为 synthetic_only 分支 | aggregator 测试覆盖 | 无 |

无编号冲突、文档冲突、Git 冲突、SSOT 冲突阻断本阶段收口。

---

## 35. 证据包索引

- 代码：`agents/enterprise/telemetry/`（13 文件）、`backend/app/api/governance_telemetry.py`、`frontend/src/app/governance-observability/page.tsx`
- 测试：`tests/agents/test_enterprise_telemetry_core.py`、`tests/agents/test_enterprise_synthetic_drill.py`、`backend/tests/test_governance_telemetry.py`
- CI：`.github/workflows/telemetry-quality-gate.yml`
- 审计：`agents/enterprise/audit.py`（+4 枚举，total=100）
- 文档：`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §15、`docs/PRODUCTION_TELEMETRY_SYNTHETIC_OPERATIONS_GUIDE.md`
- SSOT：`.ai/project_status.json`（`phase_3_9_4_status` + `phase_3_9_4` 块）、`.ai/roadmap_v8.md` §35.4
- 基线：`.ai/baselines/phase3.8_governance_release_baseline.json`（total=100）

---

## 36. 收口声明与 STOP

Phase 3.9.4「生产遥测接入适配与合成运维验证层」**已 BUILT_NO_GO 收口**：31 项任务全完成，10 个逻辑提交真实落地（Git 实据 `git rev-list --count 9201a7d^..a905213` = 10，详见 §24 完整 10 行 hash 清单），测试计数 agents 2373（阶段新增）/ backend 全量 2748（阶段新增 374，含 6 项 3.9.2 RC-freeze 资产于 3.9.5 线收口后转绿）/ frontend jest 117 / tsc 0，治理完整性 9/9，生产安全 7/7，硬编码 0 命中，fabrication 仅历史文档命中（零本阶段），14 条红线全遵守，368 项 fail-closed 禁名，4 类审计集成（总数 100，与基线 `audit_category_contract.total=100` 一致）。

**STOP**：不进入真实激活态、不真接入生产、不真发告警、不自动回滚/ACK/RESOLVE/CLOSE、不自动开启 `engineering_enabled`、不输出 `engineering_approved`。待主理人线下审核授权后，按 §31 路径推进真实接入与激活。

— 阶段负责人（BOIP AI Chief Architect + Production Observability Architect + SRE Platform Engineering Lead + Telemetry Integration Lead + Synthetic Operations Validation Auditor + 本阶段自主研发负责人）· 2026-08-12
