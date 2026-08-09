# Phase 3.8.4 收口报告 —— Enterprise Analytics & Operation Intelligence Layer（企业运营分析与智能洞察层）

- **日期**：2026-08-04
- **身份**：BOIP AI Chief Architect
- **状态**：🟢 `ENTERPRISE_ANALYTICS_INTELLIGENCE_BUILT_NO_GO`
- **前置已达**：Phase 3.7 ✅ / 3.8.0 ✅ / 3.8.1 ✅ / 3.8.2 ✅ / 3.8.3 ✅
- **本轮范围**：在企业运营层（3.8.0~3.8.3）基座之上，补齐「运营指标 / 项目分析 / 流程效率 / AI使用 / 风险预警」五类智能洞察能力。

---

## 0. 最高红线（6 条，fail-closed，全程恒守）

| # | 红线 | 本轮落点 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | 所有服务构造/写路径首行断言 `safety_invariants_ok()`（= `load_engineering_enabled() is False`）；启用态下构造一律抛 `EnterpriseRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | 无 `approve`/`engineering_approved` 入口（`_RedLineForbiddenMixin` 拦截） |
| ③ | **禁止自动经营决策**（3.8.4 语义升级） | analytics 层无经营/管理决策入口；额外拦截 `auto_business_decision`/`make_management_decision`/`decide`/`resolve`/`mitigate`/`manage` |
| ④ | 禁止自动审批 | 无 `approve`/`sign`/`authorize` 入口 |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | 以 `safety_invariants_ok()` 作为统一构造/写路径前置护栏 |
| ⑥ | **禁止 AI 代替管理责任**（3.8.4 语义升级） | 审计如实标 actor；AI 使用记录恒记 `AI`；风险候选 `requires_human_confirmation` 恒 True；无 `record_human_approval` 入口 |

> 本轮红线③/⑥ 措辞较 3.8.0~3.8.3 升级为「自动经营决策」「AI 代替管理责任」。analytics 层所有输出（指标/分析/洞察/风险候选）**仅为事实记录、洞察、或待人工确认候选**，无任何代决策或代管理入口。

---

## 1. 任务1 —— 运营指标模型（`agents/enterprise/operation_metric.py`）

- `OperationMetricType`（中性事实型枚举）：`COUNT` / `SUM` / `AVERAGE` / `RATE` / `RATIO` / `DURATION` / `GAUGE` / `DELTA`——**不含任何评价性/决策性类型**（如质量分/合格率的判定语义交由调用方）。
- `OperationMetric`：字段严格对应 `metric_id` / `org_id` / `metric_type` / `value` / `period` / `source` + `recorded_at` / `recorded_by`；**只记录事实**，不承载评价/决策结论。
- `OperationMetricService(org_id, audit=None)`：`create_metric` / `get` / `list_metrics`（可按 `metric_type` / `period` 过滤）。
  - 写路径断言 `safety_invariants_ok()`（红线①/⑤）；跨域操作抛 `EnterpriseIsolationError`。
  - 可选联动审计：默认 `record_ai_action`（actor=AI）；可由 `actor_kind="user"` 显式标 USER（人工登记场景），如实标注采集方。
  - `_FORBIDDEN` 额外拦截 `auto_business_decision` / `make_management_decision`（红线③），从结构上杜绝 AI 代管理做经营决策。

## 2. 任务2 —— 项目分析（`agents/enterprise/project_analytics.py`）

- `ProjectAnalytics`：字段 `total_projects` / `completed_count` / `completion_rate` / `avg_cycle_days` / `status_distribution` + `notes`。
  - **事实统计**：完成态判定以 `archived` 视为完成（业务事实约定，非质量评价）。
  - **不含任何工程质量评价字段**（红线③/⑥）。
- `ProjectAnalyticsService.compute_project_analytics`：只读注入的 `ProjectService`，输出事实统计。
  - **禁止工程质量评价入口**：`_FORBIDDEN` 拦截 `evaluate_quality` / `score_project`（红线③/⑥）——AI 不代管理评价工程好坏。
  - 跨域访问由 `ProjectService` 作用域过滤；构造断言 `safety_invariants_ok()`。

## 3. 任务3 —— 流程效率分析（`agents/enterprise/workflow_analytics.py`，红线③ 重点）

- `WorkflowAnalytics`：字段 `stage_duration` / `sla_status` / `bottleneck` / `insight`。
  - `insight` 为**纯描述性洞察**（如「耗时最长阶段为 X」「存在 N 条 SLA 逾期，建议人工排查」），**非处置指令**。
- `WorkflowAnalyticsService.compute_workflow_analytics`：只读 `workflow_metrics` + `workflow_slas`：
  - 累加各阶段耗时 `stage_duration`，瓶颈 = 累计耗时最大阶段（**事实推导**）；
  - 统计 SLA 状态分布 `sla_status`（ON_TRACK/WARNING/OVERDUE）；
  - 生成描述性 `insight`。
  - **禁止自动修改流程**：`_FORBIDDEN` 额外拦截 `modify_workflow` / `update_workflow` / `auto_fix`（红线③/⑥）。

## 4. 任务4 —— AI 使用分析（`agents/enterprise/ai_usage_analytics.py`，红线⑥ 重点）

- `AIUsageEvent`：字段 `event_id` / `org_id` / `task_type` / `success` / `response_time` / `recorded_at` / `recorded_by`（**恒为 `ai`**，来源备注不改 actor）。
- `AIUsageAnalytics`：字段 `total_calls` / `task_type_distribution` / `response_ok` / `response_fail` / `avg_response_time`。
- `AIUsageAnalyticsService.record_ai_usage`：**恒记 `actor=AI`**，内部调用 `record_ai_action`，**绝不调用** `record_user_action` 伪造为人工（红线⑥）。
- `compute_analytics` 聚合事件输出统计；`list_events` 只读列出。跨域访问抛 `EnterpriseIsolationError`。

## 5. 任务5 —— 风险预警（`agents/enterprise/operation_risk.py`，红线③/⑥ 重点）

- `RiskSeverity`（事实分级）：`LOW` / `MEDIUM` / `HIGH`。
- `RiskCandidate`：`requires_human_confirmation` **恒为 True**（`__post_init__` 强制——即便传入 `False` 也置 True）；`detected_by=ai`（检测方，**非决策方**）。
- `OperationRiskDetector.detect_risks`：基于外部事实信号（`signals` 列表，含 `risk_type`/`severity`/`description`/`evidence`）**如实转换**为 `RiskCandidate`，**要求人工确认**。
  - **禁止决策入口**：`_FORBIDDEN` 拦截 `decide` / `resolve` / `auto_decide` / `mitigate` / `manage` / `auto_business_decision` / `make_management_decision`（红线③/⑥）——AI 不代管理处置风险。
  - 无 `resolve`/`close`/`approve_risk` 等任何状态流转入口；仅输出候选，处置权留给人。

## 6. 任务6 —— 测试（六类，38 用例全绿）

| 测试文件 | 覆盖 | 用例数 |
|---|---|---|
| `test_enterprise_operation_metric.py` | 事实登记 / 过滤 / 跨域隔离 / 审计 actor / fail-closed / forbidden 经营决策方法 | 7 |
| `test_enterprise_project_analytics.py` | 事实统计 / 平均周期 / 无质量评价入口 / 审计 / fail-closed | 5 |
| `test_enterprise_workflow_analytics.py` | 阶段耗时+瓶颈+洞察 / 无修改流程入口 / 审计 / fail-closed | 4 |
| `test_enterprise_ai_usage_analytics.py` | 调用统计 / 恒记 AI / 绝不伪造人工 / fail-closed / forbidden | 4 |
| `test_enterprise_operation_risk.py` | 风险候选+人工确认 / 强制确认 / 无决策入口 / 审计 / fail-closed | 5 |
| `test_enterprise_analytics_red_line.py` | 全局红线 + 5 服务 fail-closed + forbidden 决策方法 + 风险强制确认 + AI 不伪造人工 + 聚合装配 | 13 |

- **全 agents 套件：1002 passed（964 基线 + 38）零回归**。
- 红线 fail-closed 测试一律 `monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)` 注入，**绝不修改** `verified.json` / `config.yaml` / `engineering_enabled`。

---

## 7. 装配与集成

- `agents/enterprise/service.py`：在 3.8.0~3.8.3 装配基础上，**新增 5 个子服务**，共享同一 `audit` 实例：
  - `operation_metrics`（`OperationMetricService`）
  - `project_analytics`（`ProjectAnalyticsService`，注入 `self.projects`）
  - `workflow_analytics`（`WorkflowAnalyticsService`，注入 `self.workflow_metrics` + `self.workflow_slas`）
  - `ai_usage_analytics`（`AIUsageAnalyticsService`）
  - `operation_risk`（`OperationRiskDetector`）
- `agents/enterprise/__init__.py`：导出 5 个新模块的全部符号（`OperationMetric`/`OperationMetricType`/`OperationMetricService`、`ProjectAnalytics`/`ProjectAnalyticsService`/`ProjectStatus`、`WorkflowAnalytics`/`WorkflowAnalyticsService`、`AIUsageEvent`/`AIUsageAnalytics`/`AIUsageAnalyticsService`、`RiskCandidate`/`RiskSeverity`/`OperationRiskDetector`）。

---

## 8. 红线守约自检

- ① `engineering_enabled=false`：所有服务构造/写路径首行 `safety_invariants_ok()`；启用态构造测试 6/6 抛 `EnterpriseRedLineViolationError`。✅
- ② 无 `engineering_approved`/`approve` 输出：5 服务均继承 `_RedLineForbiddenMixin`，**无** approve/engineering_approved 方法。✅
- ③ 禁止自动经营决策：analytics 层无经营/管理决策入口；`_FORBIDDEN` 结构性拦截 `auto_business_decision`/`make_management_decision`/`decide`/`resolve`/`mitigate`/`manage`/`modify_workflow`/`update_workflow`/`auto_fix`。✅
- ④ 禁止自动审批：无 `approve`/`sign`/`authorize` 方法。✅
- ⑤ 不绕过 `UnifiedActivationGate`：统一以 `safety_invariants_ok()` 作构造/写路径前置护栏。✅
- ⑥ 禁止 AI 代替管理责任：审计如实标 actor；AI 使用记录恒记 `AI`（测试验证不产生 USER 记录）；风险候选 `requires_human_confirmation` 恒 True（测试验证）；无 `record_human_approval`。✅

---

## 9. 交付物清单

| 类型 | 路径 |
|---|---|
| 运营指标 | `agents/enterprise/operation_metric.py` |
| 项目分析 | `agents/enterprise/project_analytics.py` |
| 流程效率分析 | `agents/enterprise/workflow_analytics.py` |
| AI 使用分析 | `agents/enterprise/ai_usage_analytics.py` |
| 风险预警 | `agents/enterprise/operation_risk.py` |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_{operation_metric,project_analytics,workflow_analytics,ai_usage_analytics,operation_risk,analytics_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.4_enterprise_analytics_intelligence_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_4` 块 + 顶层 `phase_3_8_4_status=ENTERPRISE_ANALYTICS_INTELLIGENCE_BUILT_NO_GO`） |
| 路线图 | `.ai/roadmap_v8.md`（第 7 节 + 状态链补 3.8.4 行） |

---

## 10. 结论与停止状态

Phase 3.8.4 企业运营分析与智能洞察层已构建完成：五类 analytics 能力全部落地，输出仅限事实记录/洞察/待人工确认候选，红线 6/6 守约（含 3.8.4 语义升级③自动经营决策 / ⑥AI代替管理责任）。

- **不修改** `verified.json` / `config.yaml` / `engineering_enabled`。
- **保持** `engineering_enabled=false`。
- **不输出** `engineering_approved`。
- 全 agents 套件 **1002 passed** 零回归。

**完成后停止**：等待主理人 + 专家线下提交真实证据、并经人类终端显式将 `engineering_enabled=true` 后，方可进入后续实现/经营决策路线；AI 不代管理做决策。
