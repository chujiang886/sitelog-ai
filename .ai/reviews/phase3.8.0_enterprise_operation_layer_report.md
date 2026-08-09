# Phase 3.8.0 Enterprise Operation Layer（企业运营层）收口报告

- **日期**：2026-08-04
- **身份**：BOIP AI Chief Architect
- **基线**：Phase 3.7.0~3.7.9 ✅（工程 AI 助手交互层 DONE，2026-08-03；全 agents 测试 791 passed）
- **状态**：🟢 **ENTERPRISE_OPERATION_LAYER_BUILT_NO_GO**（已构建，未激活）
- **激活态**：`engineering_enabled=false`；**NO-GO 维持**

---

## 0. 最高红线（fail-closed，6 条，与 Phase 3.7.x 实质一致）

| # | 红线 | 企业运营层落点 |
|---|---|---|
| 1 | 禁止开启 `engineering_enabled` | 所有 Enterprise 服务构造/写路径均断言 `safety_invariants_ok()`（等价 `load_engineering_enabled() is False`） |
| 2 | 禁止输出 `engineering_approved` | forbidden 方法名 `approve` / `engineering_approved` 被 `_RedLineForbiddenMixin` 拦截（结构上不可达） |
| 3 | 禁止自动报价 | forbidden 方法名 `quote` / `pricing` 被 mixin 拦截 |
| 4 | 禁止自动审批 | forbidden 方法名 `approve` / `sign` / `authorize` 被 mixin 拦截 |
| 5 | 禁止绕过 `UnifiedActivationGate` | 本层不持有 gate 实例，但以 `safety_invariants_ok()` 作为统一构造/写前置护栏（语义等价门禁） |
| 6 | 禁止 AI 代替人工责任 | `AuditService` 禁止 `record_human_approval`（forbidden 方法名拦截）；审计只如实标注 `actor_kind ∈ {ai, user, system}` |

> 企业运营层**自包含**：仅共享 `agents.config_loader.load_engineering_enabled` 这一只读信号，不反向依赖 engineering 内部类型。本层只编排运营数据（用户/组织/项目/文件/审计），不写 `verified.json`、不开启 `engineering_enabled`、不输出 `engineering_approved`、不生成任何真实工程参数、不报价、不审批、不代签。

---

## 1. 任务交付清单

### 任务1：用户权限模型（User / Role / Permission）
- **位置**：`agents/enterprise/identity.py`
- **`Permission`**（13 个原子）：`VIEW_PROJECT` / `CREATE_PROJECT` / `CREATE_DESIGN` / `VIEW_DESIGN` / `VIEW_SOLUTION` / `RUN_WORKFLOW` / `MANAGE_FILES` / `REVIEW_SOLUTION` / `PROVIDE_EXPERTISE` / `REVIEW_AUDIT` / `VIEW_AUDIT` / `MANAGE_USERS` / `MANAGE_ORG`
- **`RoleKind`**（5 类）：`ADMIN` / `DESIGNER` / `ENGINEER` / `EXPERT` / `REVIEWER`
- **`ROLE_PERMISSIONS`**：五类角色权限集；**fail-closed 不含任何批准/报价/审批权限**（权限枚举本身不含 `approve`/`quote`/`sign` 等动作）。
- **`User` / `Role` / `IdentityService`**：`make_user` / `assign_role`（跨域抛 `EnterpriseIsolationError`）/ `check`。

### 任务2：组织模型与企业级隔离（Organization / Department / Member）
- **位置**：`agents/enterprise/organization.py`
- **`EnterpriseIsolationError`**：跨企业组织域访问被拒护栏（独立于工程层）。
- **`OrganizationService`**：`create_organization` / `add_department` / `add_member`（跨域成员登记抛隔离错误）。
- **`assert_same_org(expected, actual, context)`**：staticmethod，凡涉及资源归属校验之处调用，跨域一律拒绝（绝不静默放行）。

### 任务3：项目管理模型（Project）
- **位置**：`agents/enterprise/project.py`
- **`Project`**：聚合根，以**字符串外键**关联 `customer_id` / `file_ids` / `workflow_id` / `solution_id`——**零耦合**工程内部类型。
- **`ProjectService`**：`create_project` / `attach_file` / `link_workflow` / `link_solution` / `get` / `list_projects`（作用域过滤）；跨域访问抛 `EnterpriseIsolationError`。

### 任务4：文件资产管理（FileAsset）
- **位置**：`agents/enterprise/file_asset.py`
- **`compute_sha256(data: bytes)`**：标准 `hashlib.sha256` 封装。
- **`FileAsset`**：`content_hash`(sha256) / `version`(递增) / `source`(upload/import/generated) / `permission` / `owner_id`。
- **`FileAssetService`**：`upload`(version=1，算 hash) / `add_version`(version 递增，重算 hash) / `get` / `verify_hash` / `list_assets`（作用域过滤）；跨域访问抛 `EnterpriseIsolationError`。

### 任务5：AI 操作审计（AuditService，红线⑥核心）
- **位置**：`agents/enterprise/audit.py`
- **`AuditActorKind`**（`ai`/`user`/`system`）/ **`AuditActionCategory`**（`ai_action`/`user_action`/`workflow_event`）/ **`AuditRecord`**（纯数据载体）。
- **`AuditService(_RedLineForbiddenMixin)`**：`record_ai_action` / `record_user_action` / `record_workflow_event` 三类如实记录。
- **红线⑥**：`record_human_approval` 被 mixin 拦截——AI 不得把任何动作记录为「人工审批」；`actor_kind` 如实标注，绝不伪造 human approval。

### 任务6：测试（六类）
- **文件**：`tests/agents/test_enterprise_{permission,organization,project,file,audit,red_line}.py`（**+40 用例**）
- **分类**：权限/角色（9）/ 组织隔离（5）/ 项目模型（6）/ 文件资产（7）/ 审计+红线⑥（6）/ 全局红线（7，含 parametrized 6 子用例 + 2）
- **红线覆盖**：构造 fail-closed（monkeypatch `load_engineering_enabled` 翻转）、forbidden 方法名拦截、`record_human_approval` 拦截、跨域 `EnterpriseIsolationError`、字符串外键关联、sha256/version 验证。
- **不修改 `verified.json` / `engineering_enabled`**：fail-closed 路径全部经内存 monkeypatch 注入，不触碰任何配置文件。

### 聚合门面
- **位置**：`agents/enterprise/service.py`
- **`EnterpriseOperationLayer(org_id)`**：装配 `identity` / `organization` / `projects` / `files` / `audit` 五子服务；构造即断言 `safety_invariants_ok()`；`is_activation_safe()` 只读暴露护栏状态（不用于翻转开关）。

---

## 2. 设计要点：自包含 fail-closed 红线基座

- **`agents/enterprise/red_line.py`**（NEW）：
  - `EnterpriseRedLineViolationError(Exception)`：企业层红线违例（与 `SolutionRedLineViolationError` 同性质、命名独立、零耦合）。
  - `safety_invariants_ok() -> bool`：只读返回 `load_engineering_enabled() is False`。
  - `_ENTERPRISE_FORBIDDEN_METHODS = ("approve","engineering_approved","quote","pricing","sign","authorize","record_human_approval")`。
  - `_RedLineForbiddenMixin`：`__getattr__` 拦截 forbidden 方法名，让「批准/报价/审批/记录为人工」在结构上不可达。

```python
# 结构性红线：以下调用在 Enterprise 服务上被 mixin 直接拦截
AuditService(org_id="org-1").record_human_approval(...)   # → EnterpriseRedLineViolationError（红线⑥）
IdentityService(org_id="org-1").approve(...)              # → EnterpriseRedLineViolationError（红线②/④）
# 所有服务构造在 engineering_enabled=True 时一律抛错（红线①/⑤）
monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
EnterpriseOperationLayer(org_id="org-1")                  # → EnterpriseRedLineViolationError
```

---

## 3. 测试结果与回归基线

| 维度 | 数值 |
|---|---|
| 新增 enterprise 测试 | **40 passed** |
| 全 agents 套件（含 3.8.0） | **831 passed**（基线 791 + 40） |
| 失败 / 错误 | **0** |
| 修改 `verified.json` | 否 |
| 修改 `engineering_enabled` | 否（保持 `false`） |
| 输出 `engineering_approved` | 否 |

> 运行命令：`backend/.venv/bin/python -m pytest tests/agents -q` → `831 passed`。
> 注：早期一次被中断的重跑因残留状态短暂显示 25 failed（`test_threshold_real_drill.py` 真实演练用例，依赖外部 LLM，与本次纯新增改动无关）；干净重跑稳定 **831 passed 零回归**。

---

## 4. 跨域隔离验证

| 场景 | 行为 |
|---|---|
| `IdentityService.assign_role(foreign_user)` | 跨 `org_id` → 抛 `EnterpriseIsolationError` |
| `OrganizationService.add_member(foreign_user)` | 跨 `org_id` → 抛 `EnterpriseIsolationError` |
| `ProjectService.get(cross_org_project)` | 跨 `org_id` → 抛 `EnterpriseIsolationError` |
| `FileAssetService.get(cross_org_file)` | 跨 `org_id` → 抛 `EnterpriseIsolationError` |
| `OrganizationService.assert_same_org("org-1","org-2")` | 跨域 → 抛 `EnterpriseIsolationError` |
| `list_projects()` / `list_assets()` | 仅返回当前 `org_id` 下资源（作用域过滤） |

---

## 5. 状态与后续

- **当前状态**：🟢 `ENTERPRISE_OPERATION_LAYER_BUILT_NO_GO`——能力已构建，激活开关维持关闭。
- **未做之事（按指令）**：未开启 `engineering_enabled`；未输出 `engineering_approved`；未写入任何真实工程参数/报价/审批；未代人工签字或代责。
- **后续路径**（如需）：真实企业运营落地须经主理人 + 专家线下决策，按既有 G1–G6 治理链显式置 `engineering_enabled=true` 并经 `UnifiedActivationGate` 人工核准——不在本层自动发生。

---

## 6. 交付物清单

| 类型 | 路径 |
|---|---|
| 红线基座 | `agents/enterprise/red_line.py` |
| 权限模型 | `agents/enterprise/identity.py` |
| 组织模型 | `agents/enterprise/organization.py` |
| 项目模型 | `agents/enterprise/project.py` |
| 文件资产 | `agents/enterprise/file_asset.py` |
| AI 审计 | `agents/enterprise/audit.py` |
| 聚合门面 | `agents/enterprise/service.py` |
| 包导出 | `agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_{permission,organization,project,file,audit,red_line}.py` |
| 本报告 | `.ai/reviews/phase3.8.0_enterprise_operation_layer_report.md` |
| 状态刷新 | `.ai/project_status.json`（`task_status.phase_3_8` 块 + `_phase_status`/`phase_3_8_status` 刷新） |
| 路线图 | `.ai/roadmap_v8.md`（NEW） |
