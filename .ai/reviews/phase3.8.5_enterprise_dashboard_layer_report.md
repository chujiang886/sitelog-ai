# Phase 3.8.5 收口报告 —— Enterprise Intelligence Dashboard Layer（企业智能驾驶舱层）

- **生成**：2026-08-04
- **身份**：BOIP AI Chief Architect
- **性质**：Phase 3.8.5 = **企业智能驾驶舱层构建（非激活、只读、事实型呈现）**：在 3.8.4 企业运营分析与智能洞察层既有事实数据之上，新增 Dashboard 模型 / 指标组件模型 / 四类企业视图 / 角色可见性策略 / 驾驶舱审计。全 agents 套件 **1059 passed（1002 基线 + 57 驾驶舱层）零回归**。
- **依据**：`.ai/project_status.json`（新增 `task_status.phase_3_8_5` 块；顶层 `phase_3_8_5_status=ENTERPRISE_DASHBOARD_LAYER_BUILT_NO_GO`）、`.ai/roadmap_v8.md`（§8）、真实源码 `agents/enterprise/{dashboard,dashboard_views,dashboard_visibility,audit,service,__init__}.py` + `tests/agents/test_enterprise_dashboard{,_widget,_visibility,_analytics_permission,_audit,_red_line}.py`
- **权威声明**：本文件为 Phase 3.8.5 的唯一收口报告；状态刷新同步写入 `project_status.json` 与 `roadmap_v8.md`。

---

## 0. 最高红线（6 条，fail-closed）—— 全程恒守

| # | 红线 | 本层落实 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | 所有企业服务构造/写路径断言 `safety_invariants_ok()`（`load_engineering_enabled() is False`）；测试以 `monkeypatch` 内存翻转护栏信号验证，绝不触碰 `config.yaml`/`verified.json` |
| ② | 禁止输出 `engineering_approved` | `_FORBIDDEN` 含 `engineering_approved`；本层无该动作、无该字段输出 |
| ③ | 禁止自动报价 | `_FORBIDDEN` 含 `quote`/`pricing`；驾驶舱组件 `__post_init__` 结构性拦截 `decision`/`recommendation`/`approval`/`quote`/`pricing`/`engineering_approved` 等决策性事实键，**只展示事实** |
| ④ | 禁止自动审批 | `_FORBIDDEN` 含 `approve`/`sign`/`authorize`；本层无任何审批入口 |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | 以 `safety_invariants_ok()` 作为统一前置护栏，等价于门禁护栏 |
| ⑥ | 禁止 AI 代替管理责任 | `AuditService` 始终不提供 `record_human_approval`（mixin 拦截）；驾驶舱审计 `view/query/export` 仅如实标注 actor（默认 USER），绝不伪造人工审批；`auto_business_decision`/`make_management_decision`/`evaluate_quality`/`decide`/`resolve`/`mitigate` 等决策入口被拦截 |

**状态结论**：🟢 **BUILT_NO_GO**。`engineering_enabled=false`；无 `engineering_approved`；不自动报价、不自动审批、不 AI 代责、不自动经营决策。

---

## 1. 本轮任务与交付对照

| 指令任务 | 交付物 | 状态 |
|---|---|---|
| 任务1 Dashboard 模型（dashboard_id/org_id/owner_id/widgets/visibility/created_at） | `Dashboard` + `DashboardService`（`create_dashboard`/`add_widget`/`get_dashboard`/`list_dashboards`/`remove_widget`；跨域 `EnterpriseIsolationError`；写路径断言红线①/⑤） | ✅ DONE |
| 任务2 指标组件模型（metric/chart/table/risk，只展示事实） | `WidgetType` + `DashboardWidget`（`__post_init__` 拦截决策性事实键，红线③/⑥） | ✅ DONE |
| 任务3 企业视图（Project/Workflow/AI/Risk） | `ProjectDashboard`/`WorkflowDashboard`/`AIDashboard`/`RiskDashboard`（只读组合 3.8.4 事实，拆解事实型 widget 并打 `source` 标记） | ✅ DONE |
| 任务4 权限控制（接入 AnalyticsVisibilityPolicy，不同角色看不同数据） | `AnalyticsVisibilityPolicy`（默认拒绝角色→数据源映射 + `can_view_dashboard`/`visible_widgets`/`filter_dashboard`；private/org/role:<kind> 叠加；未知 visibility 默认拒绝） | ✅ DONE |
| 任务5 Dashboard 审计（记录 view/query/export，禁止记录为人工审批） | `AuditActionCategory.DASHBOARD` + `record_dashboard_view`/`record_dashboard_query`/`record_dashboard_export`；`DashboardService.render_dashboard`/`run_query`/`export_dashboard` 联动；`record_human_approval` 仍被拦截（红线⑥） | ✅ DONE |
| 任务6 测试（dashboard/widget/visibility/analytics权限/audit/red line；不改 verified.json/engineering_enabled） | 6 类测试 **52 用例全绿**；全 agents 套件 **1054 passed** 零回归 | ✅ DONE |

---

## 2. 源码实现要点

### 2.1 Dashboard 模型与服务（`agents/enterprise/dashboard.py`）
- `Dashboard`：固定 6 字段 `dashboard_id` / `org_id` / `owner_id` / `widgets` / `visibility` / `created_at`。
- `DashboardService(_RedLineForbiddenMixin)`：`_FORBIDDEN` 在 3.8.4 语义升级基础上保留 `approve`/`engineering_approved`/`quote`/`pricing`/`sign`/`authorize`/`record_human_approval`，并扩展 `auto_business_decision`/`make_management_decision`/`decide_operation`/`evaluate_quality`（红线③/⑥）。
  写路径（`create_dashboard`/`add_widget`/`remove_widget`）断言 `safety_invariants_ok()`；`_get_scoped` 跨域抛 `EnterpriseIsolationError`。

### 2.2 指标组件（事实型，`dashboard.py`）
- `WidgetType`（metric / chart / table / risk）；`DashboardWidget.facts` 必须为 `dict`。
- `__post_init__` 结构性拦截 `decision`/`recommendation`/`approval`/`approved`/`quote`/`pricing`/`engineering_approved` 七类决策性或建议性事实键，命中即抛 `EnterpriseRedLineViolationError`（红线③/⑥：驾驶舱只展示事实）。

### 2.3 企业视图（只读组合，`agents/enterprise/dashboard_views.py`）
- `ProjectDashboard`/`WorkflowDashboard`/`AIDashboard`/`RiskDashboard`：分别只读组合 3.8.4 既有 `ProjectAnalytics` / `WorkflowAnalytics` / `AIUsageAnalytics` / `list[RiskCandidate]`，拆解为事实型 widget（metric/chart/table/risk）并打 `source` 标记（`project_analytics`/`workflow_analytics`/`ai_usage_analytics`/`operation_risk`）。
- `WorkflowAnalytics.insight` 仅作 `widget.note`（描述性，不入 facts）；`RiskCandidate` 仅列出并要求人工确认的事实（`requires_human_confirmation` 恒 True）。
- 视图构建为纯只读装配，不写数据、不持有任何红线方法。

### 2.4 可见性策略（`agents/enterprise/dashboard_visibility.py`）
- `AnalyticsVisibilityPolicy`：`_ROLE_VISIBLE_SOURCES` 默认拒绝映射（`RoleKind` → 允许可见的数据源集合）。示例差异：
  - DESIGNER / ENGINEER：可见 `project_analytics` / `workflow_analytics` / `ai_usage_analytics`，**不可见** `operation_risk`；
  - EXPERT：可见 `project_analytics` / `ai_usage_analytics`，**不可见** `workflow_analytics` / `operation_risk`；
  - REVIEWER / ADMIN：可见全部四类源。
- `can_view_dashboard`：`private`（仅 owner）/ `org`（组织内，按角色过滤）/ `role:<kind>`（仅该角色）/ 未知声明 → 默认拒绝（fail-closed）。
- `filter_dashboard`：返回仅含可见事实组件的副本，不修改原对象。本策略仅决定「展示哪些事实组件」，不授予权限、不做决策；真实权限仍由 `IdentityService.check` 校验。

### 2.5 驾驶舱审计扩展（`agents/enterprise/audit.py` + `dashboard.py`）
- 新增 `AuditActionCategory.DASHBOARD`。
- `AuditService` 新增 `record_dashboard_view` / `record_dashboard_query` / `record_dashboard_export`：actor 如实标注（默认 USER，可显式 AI），**始终不提供 `record_human_approval`**（红线⑥：禁止把动作记录为人工审批）。
- `DashboardService.render_dashboard` / `run_query` / `export_dashboard` 联动写入对应 DASHBOARD 类别审计；与既有 `AI_ACTION` / `USER_ACTION` 类别互不串类。

### 2.6 聚合装配（`agents/enterprise/service.py` + `__init__.py`）
- `EnterpriseOperationLayer` 在 3.8.4 五子服务之上追加：`dashboards`（DashboardService）/ `project_dashboard` / `workflow_dashboard` / `ai_dashboard` / `risk_dashboard` / `dashboard_visibility`（AnalyticsVisibilityPolicy），共享同一 `audit` 实例。
- `agents/enterprise/__init__.py` 导出 `WidgetType`/`DashboardWidget`/`Dashboard`/`DashboardService`/`ProjectDashboard`/`WorkflowDashboard`/`AIDashboard`/`RiskDashboard`/`AnalyticsVisibilityPolicy`。

---

## 3. 测试与回归

- 新增 7 类测试（`tests/agents/test_enterprise_dashboard{,_widget,_visibility,_view,_analytics_permission,_audit,_red_line}.py`），**共 57 用例**（含本轮补强的独立四类视图测试 5 用例）。
- 覆盖：Dashboard 模型/服务、widget 事实型约束（决策键拦截）、四类企业视图（事实型、Risk 保持 `requires_human_confirmation=true`、视图无 forbidden 方法）、角色可见性默认拒绝、角色级数据差异（DESIGNER 看不到 risk、EXPERT 看不到 workflow）、驾驶舱审计类别隔离与 actor 标注、`record_human_approval` 拦截、构造 fail-closed（monkeypatch 翻转 `load_engineering_enabled`）、决策类 forbidden 方法不可达。
- 全 agents 套件 **1059 passed（1002 基线 + 57）零回归**。
- **未修改** `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

---

## 4. 交付物清单

| 类型 | 路径 |
|---|---|
| Dashboard 模型与服务 | `agents/enterprise/dashboard.py` |
| 企业视图（四态） | `agents/enterprise/dashboard_views.py` |
| 可见性策略 | `agents/enterprise/dashboard_visibility.py` |
| 驾驶舱审计扩展 | `agents/enterprise/audit.py`（DASHBOARD 类别 + view/query/export） |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×7（57 用例） | `tests/agents/test_enterprise_dashboard{,_widget,_visibility,_view,_analytics_permission,_audit,_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.5_enterprise_dashboard_layer_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_5` 块 + 顶层 `phase_3_8_5_status=ENTERPRISE_DASHBOARD_LAYER_BUILT_NO_GO`） |
| 路线刷新 | `.ai/roadmap_v8.md`（§1 / §3 状态链 / §8） |

---

## 5. 未完成（人工动作，pending_verification）

- 真实驾驶舱在企业内的角色授权落地（identity 层 `view_*` 权限与 `AnalyticsVisibilityPolicy` 的协同配置）；
- 真实双签阈值录入；
- 人类对风险候选与经营数据作人工确认与处置（AI 仅输出事实与待确认候选，不作判定）；
- ESW 窗口维持 `OPEN_EMPTY`，等待主理人 + 专家线下提交真实证据后经人类终端显式置 `enabled=true`。

**完成后停止**：本轮仅完成企业智能驾驶舱层的构建与收口，`engineering_enabled` 保持 `false`，不输出 `engineering_approved`。

---

## 6. 完成标准自检（指令要求 5 项输出）

### 6.1 交付概览
Phase 3.8.5（Enterprise Intelligence Dashboard Layer · 企业智能驾驶舱层）在 3.8.4 既有事实数据之上构建**只读、事实型**的驾驶舱呈现层。**8 任务全部完成**：Dashboard 模型（组织隔离、无决策字段）、DashboardWidget（metric/chart/table/risk 事实型，结构性拦截决策键）、四类企业视图（Project/Workflow/AI/Risk，Risk 保持 `requires_human_confirmation=true`）、AnalyticsVisibilityPolicy（org/role/permission 三因子，默认拒绝、不绕过 Enterprise Access Permission）、驾驶舱审计（view/query/export，actor 真实、禁止记录为人工审批）、7 类测试（含独立四类视图测试）、最终验证、收口文档。状态 🟢 **BUILT_NO_GO**。

### 6.2 代码文件清单
| 类型 | 文件 |
|---|---|
| Dashboard 模型 + 指标组件 + 服务 | `agents/enterprise/dashboard.py` |
| 四类企业视图（只读组合） | `agents/enterprise/dashboard_views.py` |
| 可见性策略（AnalyticsVisibilityPolicy） | `agents/enterprise/dashboard_visibility.py` |
| 驾驶舱审计扩展（DASHBOARD 类别 + view/query/export） | `agents/enterprise/audit.py` |
| 聚合装配（EnterpriseOperationLayer 挂载 6 个驾驶舱成员） | `agents/enterprise/service.py` |
| 符号导出 | `agents/enterprise/__init__.py` |
| 测试 ×7（共 57 用例） | `tests/agents/test_enterprise_dashboard.py` / `_widget.py` / `_visibility.py` / `_view.py` / `_analytics_permission.py` / `_audit.py` / `_red_line.py` |
| 收口报告 | `.ai/reviews/phase3.8.5_enterprise_dashboard_layer_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_5` 块 + 顶层 `ENTERPRISE_DASHBOARD_LAYER_BUILT_NO_GO`） |
| 路线刷新 | `.ai/roadmap_v8.md`（§1 / §3 状态链 / §8） |

### 6.3 测试结果
- **全 agents 套件：1059 passed（1002 基线 + 57 驾驶舱层），0 失败，零回归**（本轮 `backend/.venv/bin/python -m pytest tests/agents -q` 实测）。
- 7 类测试覆盖：dashboard 模型/服务、widget 事实型约束（决策键拦截）、四类企业视图（事实型、Risk 保持人工确认、视图无 forbidden 方法）、角色可见性默认拒绝、角色级数据差异、驾驶舱审计类别隔离与 actor 标注、`record_human_approval` 拦截、构造 fail-closed、决策类 forbidden 方法不可达、跨域组织隔离。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（git 状态核验：`verified.json`/`config.yaml` 均不在变更列表）。

### 6.4 六大红线验证（实测）
| # | 红线 | 验证方式 | 结果 |
|---|---|---|---|
| ① | 禁开 `engineering_enabled` | `safety_invariants_ok()` 实测 = `True`（护栏关闭）；构造/写路径均断言 | ✅ 守约 |
| ② | 禁输出 `engineering_approved` | 访问 `approve`/`engineering_approved` 等 11 个 forbidden 方法名全部抛 `EnterpriseRedLineViolationError` | ✅ 守约 |
| ③ | 禁自动经营决策 | `DashboardWidget` 注入 `decision`/`recommendation`/`approval`/`quote`/`pricing`/`engineering_approved` 六类键全部拦截；视图仅组装事实 | ✅ 守约 |
| ④ | 禁自动审批 | `approve`/`sign`/`authorize` 在 forbidden 名单，访问即抛错；无审批入口 | ✅ 守约 |
| ⑤ | 禁绕过 `UnifiedActivationGate` | `DashboardService.__init__` + 所有写路径断言 `safety_invariants_ok()`，等价于门禁护栏 | ✅ 守约 |
| ⑥ | 禁 AI 代管理责任 | `AuditService` 无 `record_human_approval`；驾驶舱审计 actor 如实标注（默认 USER，可显式 AI），绝不伪造人工审批；跨域访问抛 `EnterpriseIsolationError` | ✅ 守约 |

### 6.5 激活状态声明
- **`engineering_enabled = false`**（来源：`agents/config.yaml` 第 102 行 `engineering_enabled: false`，本轮未修改；`safety_invariants_ok()` 实测 `True`）。
- **未输出 `engineering_approved`**（代码中无任何该字段/动作，forbidden 名单拦截）。
- **未进入 Phase 3.8.6**，按指令停止，**等待主理人审核**。ESW 窗口维持 `OPEN_EMPTY`，待主理人 + 专家线下提交真实证据后由人类终端显式置 `enabled=true`。

---

## 7. 最终收口核验（2026-08-04 终验）

按主理人指令逐项执行最终收口，结论如下：

| 步骤 | 核验项 | 实测结果 |
|---|---|---|
| 1 | 运行完整 agents 测试 | **1059 passed（1002 基线 + 57 驾驶舱层），0 失败，零回归**（`backend/.venv/bin/python -m pytest tests/agents -q`） |
| 2 | `engineering_enabled=false` | `agents/config.yaml` 第 102 行 `engineering_enabled: false`；`safety_invariants_ok()` 实测 `True` ✅ |
| 3 | 无 `engineering_approved` | 访问 `approve`/`engineering_approved`/`sign`/`authorize`/`quote`/`pricing`/`record_human_approval`/`auto_business_decision`/`make_management_decision` 9 个决策/审批/报价方法名全部抛 `EnterpriseRedLineViolationError`；`decide`/`resolve` 不在 API（ABSENT）；**可干净调用方法数 = 0** ✅ |
| 4 | Dashboard 无决策字段 | `Dashboard` 仅含 `dashboard_id/org_id/owner_id/widgets/visibility/created_at`（无 decision/recommendation/approval/quote/pricing）；`DashboardWidget` 注入六类决策键全部拦截 ✅ |
| 5 | 权限过滤 | `AnalyticsVisibilityPolicy`：DESIGNER 看 RiskDashboard 的 risk widget = 0（默认拒绝）；ADMIN = 1（可见）；EXPERT 看 WorkflowDashboard = 0（默认拒绝）；Risk 组件 `requires_human_confirmation` 全 `True` ✅ |
| 6 | 生成收口报告 | 本报告（`.ai/reviews/phase3.8.5_enterprise_dashboard_layer_report.md`） |
| 7 | 更新 `project_status.json` / `roadmap_v8.md` | 见 §8 / 状态文档 |

### 7.1 本轮回修（根因修复）
- `agents/enterprise/dashboard_views.py`：`RiskDashboard.build()` 对 `severity` 的防御表达式原为 `isinstance(c.severity, type(c.severity))`（恒为 True），当 `RiskCandidate.severity` 为字符串（如 `"low"`）时崩溃（AttributeError: 'str' has no attribute 'value'）。修正为 `isinstance(c.severity, RiskSeverity)`，枚举路径不变、字符串路径安全降级为 `str()`。修复后四类视图测试 + 全量套件 **1059 passed 零回归**。
- 该修复纯属序列化健壮性，**不引入任何决策/审批/报价/记录人工方法**，不触碰红线，未改 `verified.json`/`config.yaml`/`engineering_enabled`。

### 7.2 git 变更核验
- `verified.json` / `config.yaml` **均不在 git 变更列表**（未修改）✅。
- `engineering_enabled` 保持 `false` ✅；无 `engineering_approved` 输出 ✅。

### 7.3 完成标准自检（5 项）
1. **交付概览**：Dashboard 模型 / DashboardWidget（事实型四态）/ 四类企业视图（Risk 保持人工确认）/ AnalyticsVisibilityPolicy（org·role·permission 默认拒绝）/ 驾驶舱审计（view·query·export，actor 真实、禁伪造人工审批）/ 7 类测试 / 最终验证 / 收口文档。状态 🟢 **BUILT_NO_GO**。
2. **代码文件清单**：`dashboard.py` / `dashboard_views.py`（含本轮回修）/ `dashboard_visibility.py` / `audit.py`（DASHBOARD 扩展）/ `service.py` + `__init__.py` 装配；测试 ×7（57 用例）。
3. **测试结果**：全 agents 套件 **1059 passed** 零回归。
4. **六大红线验证**：见 §6.4（①~⑥ 全 ✅）。
5. **激活状态声明**：`engineering_enabled=false`，未输出 `engineering_approved`，未进入 Phase 3.8.6，等待主理人审核。

**完成后停止**：本轮仅完成最终收口核验，`engineering_enabled` 保持 `false`，不输出 `engineering_approved`，不进入下一阶段。
