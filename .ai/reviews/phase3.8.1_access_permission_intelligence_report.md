# BOIP Phase 3.8.1 收口报告 — Enterprise Access & Permission Intelligence（企业访问与权限智能层）

- **生成时间**：2026-08-04
- **身份**：BOIP AI Chief Architect
- **阶段定位**：Phase 3.8.1 = 在 **Phase 3.8.0 企业运营层（BUILT_NO_GO）** 之上，增强**企业级访问控制能力**（非激活、非工程计算）
- **前置状态**：Phase 3.7 ✅ Engineering Intelligence Complete；Phase 3.8.0 ✅ Enterprise Operation Layer
- **依据**：`.ai/project_status.json`（`task_status.phase_3_8_1` 块，`_phase_status=ENTERPRISE_ACCESS_INTELLIGENCE_BUILT_NO_GO`）、`.ai/roadmap_v8.md`、真实源码 `agents/enterprise/*.py` + `tests/agents/test_enterprise_*.py`
- **测试结论**：全 agents 套件 **880 passed**（3.8.0 基线 831 + 49 权限智能层），0 失败；未修改 `verified.json` / `engineering_enabled`
- **激活态**：**NO-GO 维持**（`engineering_enabled=False`，无任何 `engineering_approved` 输出）

---

## 0. 红线总览（6 条，全程 fail-closed，恒守）

| # | 红线 | 本轮保障机制 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | 所有 Enterprise 服务（含 3 个新子服务）构造/写路径首行断言 `safety_invariants_ok()`（= `load_engineering_enabled() is False`），非 False 即抛 `EnterpriseRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | `_RedLineForbiddenMixin` 拦截 `approve` / `engineering_approved` 方法名，结构上不可达；审计层无 `engineering_approved` 字段 |
| ③ | 禁止自动报价 | `_RedLineForbiddenMixin` 拦截 `quote` / `pricing` |
| ④ | 禁止自动授权工程责任 | `_RedLineForbiddenMixin` 拦截 `sign` / `authorize` |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | 以 `safety_invariants_ok()` 作为统一构造/写路径前置护栏（等价于门禁语义） |
| ⑥ | 禁止 AI 代责（伪造 human approval） | `AuditService` 拦截 `record_human_approval`；权限审计记录 `actor_kind` 恒为 `USER`，如实标注；绝不伪造人工审批 |

---

## 1. 当前状态

| 维度 | 真实状态 |
|---|---|
| 阶段链 | 3.7.0~3.7.9 ✅ → 3.8.0 企业运营层 BUILT ✅ → 🟢 **3.8.1 企业访问与权限智能层 BUILT（2026-08-04）** |
| 包规模 | `agents/enterprise/` 共 **11 文件**（较 3.8.0 的 8 文件新增 `resource_permission.py` / `expert_access.py` / `review_permission.py`，并重写 `identity.py` / `audit.py` / `service.py` / `__init__.py`） |
| 红线 | `engineering_enabled=false`（真实读取 `agents/config.yaml`）；无 `engineering_approved`；不报价；不审批；不 AI 代责 |
| 隔离 | 所有资源/用户/审核按 `org_id` 作用域过滤；跨域一律抛 `EnterpriseIsolationError` |
| 测试 | 全 agents 套件 **880 passed**（831 基线 + 49 权限智能层），0 失败 |
| 未完（人工） | 真实企业租户接入 / 显式置 `engineering_enabled=true` / 真实双签阈值录入 / 人类核准 均 `pending_verification` |

---

## 2. 任务交付明细（任务1–6）

### 任务1 · RBAC 增强（`agents/enterprise/identity.py` 覆盖）
- **角色继承**：`Role.inherits: tuple[RoleKind, ...]`；`effective_permissions()` 返回 自有 ∪ 所有父角色权限；`Role.has()` / `User.has_permission()` / `IdentityService.check()` 均解析继承链。
- **权限组合**：`PermissionBundle`（frozen dataclass，支持 `union` / `intersection` / `difference` / `requires` / `to_list`）；`compose_permissions(*bundles)` 合并多组合；`bundle_from_role(kind)` 把角色权限封装为组合单元。
- **资源级权限**：新增 `Permission.READ_RESOURCE` / `Permission.WRITE_RESOURCE`；各角色权限集补齐这二项（EXPERT/REVIEWER 仅 `READ_RESOURCE`，最小权限原则）。
- **红线**：`IdentityService` 构造 / `make_user` / `assign_role` 均断言 `safety_invariants_ok()`；跨域 `assign_role` 抛 `EnterpriseIsolationError`；本模块不含任何批准/报价/审批方法。

### 任务2 · 资源权限模型（`agents/enterprise/resource_permission.py` NEW）
- `ResourceKind` 枚举：PROJECT / FILE_ASSET / WORKFLOW / SOLUTION（四类受控资源）。
- `ResourcePermission` ACL 载体：资源 id + 类型 + `org_id` + `grantee_id` + `grantee_type`("user"|"role") + 权限集。
- `ResourcePermissionService`：`grant()` / `revoke()` / `check()`；`grant` 断言红线①/⑤ + `OrganizationService.assert_same_org`；`check` 解析 user/role 两类 grantee，跨域抛 `EnterpriseIsolationError`；可联动审计。

### 任务3 · 专家权限隔离（`agents/enterprise/expert_access.py` NEW）
- `ExpertAccessPolicy`：按 `authorized_project_ids` / `authorized_solution_ids` / `authorized_domains` 三维声明授权范围（frozenset 不可变）。
- `ExpertAccessService.define_policy()` / `can_review()`：`can_review` **范围外默认拒绝（fail-closed）**；跨域专家抛 `EnterpriseIsolationError`；可联动审计。

### 任务4 · 审核权限隔离 / 职责分离 SoD（`agents/enterprise/review_permission.py` NEW）
- `ReviewDecision`：ALLOWED / DENIED_SUBMITTER_IS_REVIEWER / DENIED_REVIEWER_NOT_AUTHORIZED / DENIED_EXPERT_CONFLICT。
- `ReviewPermissionService.validate()` 强制三规则：① 提交者≠审核者（自审禁止）；② 审核者须 REVIEWER 或 ADMIN；③ 专家不得兼任提交者或审核者（职责分离）；跨域抛 `EnterpriseIsolationError`；可联动审计。

### 任务5 · 权限审计（`agents/enterprise/audit.py` 覆盖）
- 新增 `AuditActionCategory.PERMISSION` 类别。
- 新增 `record_permission_check()` / `record_access_granted()` / `record_access_denied()`（均 `actor_kind=AuditActorKind.USER`，`category=PERMISSION`）。
- `query()` 扩展 `category` 过滤参数（与 `actor_kind` / `target` 并列）。
- **红线⑥ 未破坏**：`_FORBIDDEN` 仍含 `"record_human_approval"`，mix 拦截命中即抛 `EnterpriseRedLineViolationError`；权限记录不得伪造为人工审批。

### 任务6 · 测试（六类，49 用例全绿）
- 新增 `tests/agents/test_enterprise_rbac.py`（RBAC 继承/组合/check，~12 例）
- 新增 `tests/agents/test_enterprise_resource_permission.py`（资源 ACL / 四类资源 / 跨域隔离 / 审计联动，~10 例）
- 新增 `tests/agents/test_enterprise_expert_access.py`（专家范围拒绝 / 跨域隔离 / 审计，~8 例）
- 新增 `tests/agents/test_enterprise_review_permission.py`（SoD 三规则 / 跨域隔离 / 审计，~11 例）
- 新增 `tests/agents/test_enterprise_audit_permission.py`（PERMISSION 类别 / 三类记录 / `record_human_approval` 拦截 / 写路径 fail-closed，~9 例）
- 扩展 `tests/agents/test_enterprise_red_line.py`（3 个新服务纳入 fail-closed 参数化，+3 例）
- **不修改 `verified.json` / `engineering_enabled`**；启用态仅经内存 monkeypatch `load_engineering_enabled` 注入。

---

## 3. 聚合装配（联动记录权限决策）

`EnterpriseOperationLayer.__init__` 在 3.8.0 五子服务之外追加装配：
```python
self.resources    = ResourcePermissionService(org_id=org_id, audit=self.audit)
self.expert_access = ExpertAccessService(org_id=org_id, audit=self.audit)
self.review       = ReviewPermissionService(org_id=org_id, audit=self.audit)
```
三者共享同一 `self.audit` 实例，使资源授权、专家审阅、审核 SoD 的权限校验决策自动联动写入权限审计（`category=PERMISSION`）。`is_activation_safe()` 只读暴露护栏状态，不用于翻转开关。

---

## 4. 测试结果

```
$ backend/.venv/bin/python -m pytest tests/agents -p no:cacheprovider -q
880 passed in 20.54s
```
- 较 3.8.0 基线（831 passed）净增 **49** 用例，零回归。
- 红线验证：构造/写路径在 monkeypatch `load_engineering_enabled=True` 下全部抛 `EnterpriseRedLineViolationError`（红线①/⑤）；`record_human_approval` 调用抛 `EnterpriseRedLineViolationError`（红线⑥）。

---

## 5. 红线守约证据（关键点）

1. **无 `engineering_enabled` 开启**：所有 8 个 Enterprise 服务（含 3 个新服务）+ 聚合门面构造即断言 `safety_invariants_ok()`，测试已证明启用态下构造一律 fail-closed。
2. **无 `engineering_approved` 输出**：`agents/enterprise/audit.py` 无该字段；`_RedLineForbiddenMixin._FORBIDDEN` 含 `engineering_approved` / `approve`，结构拦截。
3. **无自动报价**：`_FORBIDDEN` 含 `quote` / `pricing`，新模块无报价路径。
4. **无自动授权/审批**：`_FORBIDDEN` 含 `sign` / `authorize`；`ReviewPermissionService` 只做 SoD 校验，不批准方案。
5. **无绕过门禁**：`safety_invariants_ok()` 统一前置；`OrganizationService.assert_same_org` 企业级隔离。
6. **无 AI 代责**：权限审计 `actor_kind` 恒 `USER`；`record_human_approval` 被拦截；专家审阅结论仅 `PROVIDE_EXPERTISE`，须经真实人工审核/批准。

---

## 6. 交付物清单

| 类型 | 路径 |
|---|---|
| RBAC 增强 | `agents/enterprise/identity.py`（覆盖） |
| 资源权限模型 | `agents/enterprise/resource_permission.py`（新建） |
| 专家权限隔离 | `agents/enterprise/expert_access.py`（新建） |
| 审核职责分离 | `agents/enterprise/review_permission.py`（新建） |
| 权限审计增强 | `agents/enterprise/audit.py`（覆盖） |
| 聚合装配 | `agents/enterprise/service.py`（覆盖） |
| 包导出 | `agents/enterprise/__init__.py`（覆盖） |
| 测试×5（新建） | `tests/agents/test_enterprise_{rbac,resource_permission,expert_access,review_permission,audit_permission}.py` |
| 测试（扩展） | `tests/agents/test_enterprise_red_line.py`（3 新服务纳入参数化） |
| 收口报告 | `.ai/reviews/phase3.8.1_access_permission_intelligence_report.md`（本文件） |
| 状态刷新 | `.ai/project_status.json`（`task_status.phase_3_8_1` 块；`_phase_status=ENTERPRISE_ACCESS_INTELLIGENCE_BUILT_NO_GO`） |
| 路线图 | `.ai/roadmap_v8.md`（增量更新：3.8.1 路线 + 状态链 + 交付物） |

---

## 7. 下一步

**停止。** 保持 `engineering_enabled=false`，不输出 `engineering_approved`。

真实企业级访问控制落地须经主理人 + 专家线下决策：
- 真实企业租户接入与角色落地（RBAC 继承/组合需真实组织树支撑）；
- 资源 ACL、专家授权范围、审核 SoD 规则需与真实治理政策对齐；
- 人类对权限决策与方案作最终核准（G6），AI 仅如实记录 `ai/user/system` 三类动作，绝不伪造 human approval。

---

**红线行（全程恒守）**：①`engineering_enabled=false` ②无 `engineering_approved` ③不自动报价 ④不自动审批 ⑤不绕过 `UnifiedActivationGate` ⑥不 AI 代责。
