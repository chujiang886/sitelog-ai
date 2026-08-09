# Phase 3.8.28 企业身份认证与权限治理实装层 — 收口报告

- **阶段名称**：Enterprise Identity & Permission Governance Implementation Layer
- **分支**：`feat/phase3.8.28-enterprise-identity`
- **收口时间**：2026-08-09
- **收口状态**：`BUILT_NO_GO`（已构建，未放行）
- **变更规模**：21 files changed（1779 insertions / 261 deletions）+ 9 个新增文件；后端身份包 ~1870 行
- **测试**：后端身份安全套件 58 例全绿；前端身份链路 81 例全绿；治理相关套件合计 144 例零回归
- **红线开关**：`agents/config.yaml:102 engineering_enabled: false`（本阶段未触碰，仍为 false）
- **报告完成后**：**立即停止，不进入 Phase 3.8.29，等待主理人审核**

---

## 一、阶段目标

把 Phase 3.8.27 仅完成"接口抽象"的前端身份层，落地为**真正可运行、fail-closed、前后端词表一致**的企业身份认证与权限治理链路。治理身份不再由请求头声称，而由后端从 `Authorization: Bearer <token>` 派生，并经权威数据源（数据库）二次裁定。

六个任务：

| 任务 | 目标 | 状态 |
|---|---|---|
| T1 身份验证适配层 | `verifier` 把凭据变成"经密码学校验的声明"，HS256 实装、OIDC/SSO 仅留骨架 | ✅ 完成 |
| T2 权限目录 | `permissions` 定义唯一治理权限词表（9 项）+ 4 治理角色 + 禁语扫描 | ✅ 完成 |
| T3 身份链路打通（前后端） | 后端 `principal`/`resolver`/`dependencies`/`service` + 前端 `BackendSessionIdentityProvider`/`token-store`/登录页 | ✅ 完成 |
| T4 责任闭环（accountability） | `accountability` 固化"责任五元组"，问责记录不可被自动审批动作写入 | ✅ 完成 |
| T5 安全测试 | 6 类 fail-closed + 头伪造回归 + 前后端词表对齐 | ✅ 完成（58 例） |
| T6 CI 与仓库规则 | CODEOWNERS 守护身份模块 + 专项 CI 工作流 + 静态扫描禁语头回归 | ✅ 完成 |

**边界声明**：本阶段**不改变任何 AI 治理边界**。所有 Human-in-the-loop 守卫的位置与强度与 3.8.27 完全一致，无一处放宽；`engineering_enabled` 维持 false，AI 仍无权获得治理权限、无权自动审批/执行、无权代替人工责任。

---

## 二、架构设计

```
                        Authorization: Bearer <token>
                                    │
   ┌────────────────────────────────┼────────────────────────────────┐
   │ 后端（唯一权威）                  │  前端（只递凭据，不声明身份）      │
   │                                  │                                │
   │  dependencies.get_current_principal                               │
   │      │  assert_no_legacy_identity_headers  ── x-actor-* ⇒ 400     │
   │      ▼                                                           │
   │  service.authenticate(authorization)                             │
   │      ├─ 1. extract_bearer_token  （只接受 Bearer，拒绝 ?token=）   │
   │      ├─ 2. verifier.verify  ────── HS256 验签 / 过期 / 结构 （401/500）
   │      └─ 3. resolver.resolve ───── 回库确认主体仍 active、重读角色   │
   │              │                     （非真人⇒403 / 失效⇒401 / 跨组织⇒401）│
   │              ▼                                                   │
   │  principal.GovernancePrincipal （actor_kind 恒为 USER，禁语即拒）  │
   │      │                                                           │
   │      ├─ require_governance_permission(p) ── 默认拒绝（403）        │
   │      └─ require_same_org(principal, requested) ── 跨组织（403）    │
   │                                                                  │
   │  GET /governance/me   → 返回后端裁定的身份与权限（前端只用于渲染）  │
   └────────────────────────────────┬────────────────────────────────┘
                                    │
                         前端 registry 缺省 = backend-session
                                    │
                         拿 token 问 /governance/me："我是谁"
                                    │
                         BackendSessionIdentityProvider
                         权限采信后端，不再回退前端角色表
                                    │
                         token-store（sessionStorage，关页即失效）
```

四层后端身份包（`backend/app/identity/`）：`permissions` → `verifier` → `resolver` → `principal`，外加 `service`（编排）、`dependencies`（FastAPI 依赖装配）、`accountability`（责任五元组）、`seed`（治理 RBAC 目录）、`errors`（只抛不兜的异常族）。

---

## 三、实装清单

**新增 — 后端**
- `backend/app/identity/` 整包：`__init__.py`、`errors.py`、`verifier.py`、`principal.py`、`permissions.py`、`resolver.py`、`dependencies.py`、`service.py`、`accountability.py`、`seed.py`（共 ~1870 行）
- `backend/app/api/governance_identity.py`：GET `/governance/me`、GET `/governance/catalog`
- `backend/alembic/versions/4c9d7e1f2a30_phase3_8_28_governance_rbac.py`：治理角色/权限目录迁移
- `backend/tests/test_governance_identity_security.py`：T5 安全套件（58 例）
- `backend/tests/test_governance_accountability.py`：T4 责任闭环测试

**新增 — 前端**
- `frontend/src/lib/identity/providers/backend-session.ts`：生产默认适配器，问后端"我是谁"
- `frontend/src/lib/identity/token-store.ts`：sessionStorage 凭据存储（关页即失效）

**修改 — 后端**
- `backend/app/api/__init__.py`、`main.py`：注册 `governance_identity_router`
- `backend/app/api/governance_dashboard.py`、`governance_operations.py`：改用 `require_governance_permission`
- `backend/app/db/models/rbac.py`：治理角色/权限模型字段对齐
- `backend/tests/conftest.py`：新增 `governance_env` 隔离测试环境（真实登录签发 token，无任何伪造身份捷径）

**修改 — 前端**
- `providers/jwt.ts`、`static-dev.ts`、`gateway-header.ts`：废除 `toActorHeaders`，改发 `toGovernanceHeaders`（仅复述 org-id）
- `registry.ts`：缺省适配器由 `static-dev` 改为 `backend-session`
- `guards.ts`、`types.ts`、`index.ts`、`__tests__/identity.test.ts`、`app/login/page.tsx`、`app/governance-dashboard/page.tsx`

**T6 — 仓库与 CI**
- `.github/CODEOWNERS`：身份模块纳入 `@boip/governance-owners` 守护
- `.github/workflows/identity-governance.yml`：身份专项 CI（静态扫描 + 后端安全测试 + 前端链路测试）
- `scripts/lint/check_legacy_identity_headers.py`：禁止遗留身份头的信任回归
- `scripts/ci/local_ci.sh`：新增第 9 步调用上述扫描

---

## 四、六类 fail-closed 安全矩阵

所有失败模式一律**拒绝**，绝不降级为匿名/默认责任人/只读放行。

| # | 失败类别 | 触发条件 | HTTP | 异常类 | 测试锚点 |
|---|---|---|---|---|---|
| 1 | JWT 校验 | 签名坏 / 结构坏 / secret 缺失 | 401 / 500 | `IdentityTokenInvalidError` / `IdentityConfigError` | `test_jwt_verifier_rejects_*`、`test_jwt_verifier_config_missing_secret_fails_closed` |
| 2 | 过期 | `exp` 已过 | 401 | `IdentityTokenExpiredError` | `test_jwt_verifier_rejects_expired_token`、`test_expired_token_rejected_over_http` |
| 3 | 非法身份 | 非真人（agent/service）/ 主体失效（停用·软删） | 403 / 401 | `IdentityNotHumanError` / `IdentitySubjectInactiveError` | `test_build_principal_rejects_non_human`、`test_suspended_subject_rejected_over_http`、`test_ai_forgery_rejected_over_http` |
| 4 | 权限拒绝 | 缺本次动作所需治理权限（默认拒绝） | 403 | `IdentityPermissionDeniedError` | `test_require_governance_permission_denies_by_default`、`test_permission_denial_over_http` |
| 5 | 跨组织 | 凭据声明的组织与库中不一致 / 请求组织非本人归属 | 401 / 403 | `IdentityTokenInvalidError` / `IdentityCrossOrgError` | `test_cross_org_token_reuse_rejected_over_http`、`test_require_same_org_rejects_cross_org` |
| 6 | AI 伪造 | 凭据自称 `actor_kind=agent/service` 或声明 `auto_*` 类禁语权限 | 403 | `IdentityNotHumanError` / `IdentityRedLineViolationError` | `test_ai_forgery_rejected_over_http`、`test_service_forgery_rejected_over_http`、`test_forbidden_permission_claim_rejected` |

HTTP 状态码映射集中在 `dependencies.http_status_for`：未知身份异常一律 403（fail-closed），由 `test_http_status_mapping` / `test_unknown_identity_error_fails_closed` 钉死。

---

## 五、头伪造回归与词表对齐

**头伪造回归（4 类测试）**：`x-actor-id` / `x-actor-kind` 一律 400（不静默忽略），大小写变体（`X-Actor-Id`）、双头同发均覆盖（`test_legacy_identity_header_rejected`、`test_both_legacy_headers_rejected`）。`assert_no_legacy_identity_headers` 与 `LEGACY_IDENTITY_HEADERS` 常量由 `test_assert_no_legacy_identity_headers_helper`、`test_legacy_header_constant_regression` 钉死。

**静态扫描（`scripts/lint/check_legacy_identity_headers.py`）**：字面量 `x-actor-(id|kind)` 只允许出现在身份包（`backend/app/identity/`、`frontend/src/lib/identity/`）与测试文件中；其余位置（含注释）一律禁止，违规即 CI 失败。已清理 4 处历史注释中的残留引用（`governance_dashboard.py` / `governance_operations.py` / `governance_workflow_repository.py` / `login/page.tsx`）。

**词表对齐（前后端逐字一致）**：由 `test_vocabulary_*` 三组用例钉死——
- `ALL_GOVERNANCE_PERMISSIONS`（前端 9 项）== 后端 `GovernancePermission` 枚举；
- 前端 `FORBIDDEN_PERMISSION_PATTERNS` == 后端 `FORBIDDEN_PERMISSION_PATTERNS`（对齐为同一并集 **25 项**，含 `auto_approve/auto-approve/autoapprove/auto_confirm/auto-confirm/auto_execute/auto-execute/auto_close/auto-close/auto_review/auto-review/ai_approve/ai-approve/agent_approve/self_approve/bypass_human/bypass-human/skip_human/skip-human/skip_review/skip-review/without_human/no_human/engineering_approved/engineering_enabled`）；
- 前端 `ROLE_PERMISSIONS` == 后端 `GOVERNANCE_ROLE_PERMISSIONS`（4 角色逐项权限相等）；
- 治理角色与业务角色（`RBAC_ROLES = admin/designer/viewer`）命名空间零碰撞。

---

## 六、前端身份链路收敛

- **废除"声明即身份"漏洞**：删除旧 `toActorHeaders`（发 `x-actor-id`/`x-actor-kind` 充当身份）。所有适配器只透传 `Authorization: Bearer …` + `toGovernanceHeaders`（仅复述 `org-id`，对不上后端 403）。
- **生产默认路径 = `BackendSessionIdentityProvider`**：前端拿凭据问后端 `/governance/me`，身份与权限由后端权威回答；前端 `ROLE_PERMISSIONS` 不再参与生产计算，从根上消除前后端词表漂移。
- **`token-store`**：凭据存 `sessionStorage`（关标签页即失效），注释说明未用 httpOnly Cookie 的原因（需后端签发链路 + CSRF 改动，超出本阶段）。
- **`registry` 缺省值硬化**：由 `static-dev` 改为 `backend-session`，开发与生产同走真实登录态——消除"未登录分支仅生产首次触发"的隐患；`static-dev` 无真实凭据即抛 `IdentityProviderNotConfiguredError`，不再 silently 发旧头。
- **登录页实装**：邮箱+密码 → `/api/auth/login` → 取 `access_token` → `writeGovernanceToken` → 问后端"是不是自己" → 进入驾驶舱；登出/失败均 `clearGovernanceToken` + `resetIdentityProvider`。

---

## 七、测试覆盖

**后端 `test_governance_identity_security.py`：58 例**
- 验证器 9 例（空/坏签名/缺 sub/缺 org/非 list roles/缺 secret/过期/携带 actor_kind/正常）
- 主体构造 4 例（非真人/缺 actor_id/禁语角色名/非真人 claim）
- 解析器 3 例（非真人 claim / 停用主体 HTTP / 跨组织 token HTTP）
- 权限拒绝 9 例（`require_governance_permission` 单元 + 5 组 HTTP 矩阵 + 默认拒绝）
- 跨组织 3 例（单元 + HTTP token 复用）
- AI 伪造 3 例（agent / service / 禁语权限）
- 头伪造 6 例（单头×大小写 + 双头 + helper + 常量回归）
- HTTP 状态码映射 11 例（含未知异常 fail-closed）
- 身份端点契约 5 例（`/governance/me` 自述 / 无权限空集 / 需认证 / `/governance/catalog`）
- 词表对齐 4 例

**前端 `identity.test.ts`：81 例**（含 `BackendSessionIdentityProvider` 15 例、`token-store`、`registry` 缺省、`assertNoLegacyIdentityHeaders`、禁语红线、无默认责任人）。

**回归基线**：治理相关套件（security + accountability + dashboard + persistence_workflow + rbac）合计 **144 例全绿**，零回归。

---

## 八、CI 与仓库规则

- **CODEOWNERS**：新增 `/backend/app/identity/`、`/backend/app/api/governance_identity.py`、`/backend/tests/test_governance_identity_security.py` 由 `@boip/governance-owners` 守护（身份链路改动强制治理负责人评审）。
- **专项工作流 `identity-governance.yml`**：PR/Push 触发，三步 fail-closed——① 遗留身份头静态扫描；② 后端身份安全测试；③ 前端身份链路测试。任一步失败整条失败。
- **本地 CI `local_ci.sh`**：原 8 步升级为 9 步，第 9 步调用 `check_legacy_identity_headers.py`，保持本地与远端 parity。

---

## 九、权限与角色模型

- **9 项治理权限**（读写分列）：`workflow:read` / `review:read` / `review:confirm` / `execution:read` / `audit:read` / `summary:read` / `workflow:report` / `execution:submit` / `workflow:close`。
- **4 个治理角色**（与业务角色不共用命名空间）：`governance-admin`（全权限）、`governance-reviewer`（可研判处置，无 `audit:read`）、`governance-auditor`（全量只读，零写权限——职责分离）、`governance-viewer`（仅 3 项只读）。
- **默认拒绝**：`permissions_for_roles` 对未知角色贡献空集；空角色列表 ⇒ 空权限 ⇒ 拒绝一切治理动作（含读）。业务角色（admin/designer/viewer）在治理维度上给空集。
- **结构性红线**：权限词表中**不存在**任何 `auto_*` 语义权限点；`review:confirm` 只授予"有资格提交一次人工研判"，判断仍由自然人做出。`FORBIDDEN_PERMISSION_PATTERNS` 命中即整份凭据不可信（非过滤后放行）。

---

## 十、残余风险与已知限制

1. **XSS 可窃取 sessionStorage 凭据**：凭据未用 httpOnly Cookie（需后端签发链路 + CSRF 改动，超出本阶段）。风险已记录，待后续阶段以 httpOnly Cookie + 同源 CSRF 令牌收口。
2. **OIDC / SSO 网关验证器为骨架**：`OidcTokenVerifier` / `SsoGatewayVerifier` 未配即抛 `IdentityConfigError`（明确报错而非静默放行），需真实 IdP / 部署方显式确认后才实装。
3. **角色撤销延迟**：`DbBackedPrincipalResolver` 每次请求回库重读角色，消除"token 未过期但人已撤职"的窗口；但 `ClaimsOnlyPrincipalResolver`（无状态部署）仍依赖 token 过期，非生产默认。
4. **跨租户复用**：凭据声明的 `tenant_id` 与库中不一致即拒绝（401），组织边界以数据库为准。
5. **`/governance/me` 只需认证**：无治理角色的用户看到"你没有权限"而非 403 白屏，权限集为空由前端置灰；每个治理写请求后端独立再判。

---

## 十一、范围外 / 未变更

- 不改变 AI 治理边界：`engineering_enabled` 仍为 `false`，AI 无治理权限、无自动审批/执行、无人格化责任。
- 不新增治理语义（无新权限点、无新动作），仅落地既有语义的真实鉴权与责任闭环。
- 不处理真实生产账号/SSO 接入（属"缺外部资源"，按纪律未擅自动作）。
- 前端 `tsc --noEmit` 存在与本次改动**无关**的既有错误（`consult/page.tsx`、`__tests__` jest-dom 类型、`lib/api.test.ts`、`lib/chat.ts`），运行态 110 测试全绿，未在本阶段范围内修改。

---

## 十二、验收标准与人工待办

**自动验收（已达成）**
- [x] 6 类 fail-closed 全部被测试覆盖并通过
- [x] 遗留身份头 `x-actor-*` 在身份包与测试之外零出现，CI 静态扫描通过
- [x] 前后端权限/角色/禁语词表逐字一致
- [x] 后端身份安全 58 例 + 前端身份链路 81 例 + 治理相关 144 例全绿
- [x] 迁移 `4c9d7e1f2a30` 落地治理 RBAC 目录

**人工待办（需主理人/专家线下动作，AI 不代劳）**
1. 审核本报告与代码变更，确认身份链路符合企业接入预期。
2. 提交本阶段改动（`git commit` + 开 PR 至主干），触发 `identity-governance.yml` 与 `ci.yml` 双流水线。
3. **真实证据就绪后**，由人类终端显式将 `agents/config.yaml:102 engineering_enabled` 置 `true`；此前 ESW 窗口维持 `OPEN_EMPTY`，AI 不得自动开启。
4. 规划后续收口 XSS/Cookie 风险（第十节第 1 项）与 OIDC/SSO 实装。

---

## 十三、收口声明

本阶段（`Phase 3.8.28 企业身份认证与权限治理实装层`）所有六项任务（T1–T6）已完成，测试全绿，红线未放宽，`engineering_enabled` 维持 `false`。

**收口状态：`BUILT_NO_GO`。**

**报告完成后立即停止——不进入 Phase 3.8.29，不自动开启任何治理开关，等待主理人审核。** 后续任何放行动作（提交、开 PR、置 `engineering_enabled=true`）必须由真实人类责任人显式执行，AI 仅提供本报告与代码，不承担治理责任。
