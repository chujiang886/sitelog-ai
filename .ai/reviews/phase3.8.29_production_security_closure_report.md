# Phase 3.8.29 企业生产安全与部署强化层 —— 收口报告

| 项 | 值 |
|---|---|
| 阶段 | Phase 3.8.29 Enterprise Production Security & Deployment Hardening |
| 分支 | `feat/phase3.8.29-production-security`（自 Phase 3.8.28 `f10c5dc` 切出） |
| 日期 | 2026-08-09 |
| 状态 | **BUILT_NO_GO** —— 已建成，未放行 |
| 激活态 | `agents/config.yaml:102` `engineering_enabled: false`（未改） |
| 测试 | 后端生产安全 **49 passed**；后端全量 **291 passed / 1 failed（继承债，见 §十一）**；前端 identity **88 passed**；红线扫描 **exit 0** |

---

## 一、阶段目标

3.8.28 建成了企业身份与 RBAC 骨架，但把凭据放在 `sessionStorage`，并把"存在 XSS
即可窃取治理凭据"作为已知残余风险登记在案。本阶段的任务就是**兑现那笔债**，
并把"这套东西能不能真的上生产"从口头判断变成结构性强制。

七个交付项：

| # | 任务 | 结论 |
|---|---|---|
| T1 | Token 安全强化：sessionStorage → HttpOnly Cookie（Cookie 策略 / CSRF / SameSite / 刷新） | ✅ |
| T2 | OIDC/SSO 生产接口：IdP 适配器标准化，缺配置 fail-closed，禁自动 fallback 开发身份 | ✅ |
| T3 | 环境隔离：dev / testing / production 三态，生产禁 static-dev、禁测试密钥 | ✅ |
| T4 | 安全审计增强：append-only Audit Trail（login/logout/refresh/denied/failure） | ✅ |
| T5 | CI/CD 生产门禁：身份安全 / 权限 / 红线扫描 / 依赖扫描，失败禁合并 | ✅ |
| T6 | 部署文档 `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` | ✅ |
| T7 | production-security 测试，全部 fail-closed | ✅ |

**贯穿本阶段的一条判断**：安全属性如果只靠"大家记得这么写"，它就不存在。因此
每一条要求都落到三个强制层之一——启动期拒绝、装配期拒绝、CI 期拒绝。

---

## 二、架构设计

### 2.1 三层强制点

| 层 | 实现 | 违规后果 |
|---|---|---|
| 启动期 | `Settings.assert_production_safe()`（`backend/app/main.py:34` 在 `is_production` 时调用） | 进程拒绝启动，打印全部违规项 |
| 装配期 | `build_identity_service()`（`backend/app/identity/dependencies.py:83`） | `IdentityConfigError`，请求一律 401 |
| 交付期 | `scripts/lint/check_production_security.py`（7 条红线） | CI 失败，禁止合并 |

三层是**互补**而非冗余：启动期挡住"这台机器配错了"，装配期挡住"身份链路半配
不配"，CI 期挡住"以后有人把代码改回错误写法"。少任何一层都会留下一类无人看守
的退化路径。

### 2.2 凭据双通道与优先级

```
resolve_raw_token(request, Authorization)
  ├─ Authorization 头存在 → 显式独占
  │    ├─ 合法 Bearer → 用它
  │    └─ 非法（Basic / 空）→ 判无凭据，**不回落 Cookie**
  └─ 完全没给头 → 读 HttpOnly Cookie 兜底
```

**优先级不可反转，理由是安全语义。** `Authorization` 是调用方本次显式声明的
身份；Cookie 是浏览器自动附带的环境凭据。若 Cookie 压过显式头，会出现两类真实
故障：① 同一浏览器登录过 A，脚本带着 B 的 Bearer 头调 `/refresh`，实际续的是 A
的会话、审计也记成 A —— 多租户治理场景下即**责任人张冠李戴**；② 自动化客户端
无法覆盖残留会话，调试与审计都指向错误 actor。

"显式头非法也不回落"同理：调用方已表态用某种方式认证，我们不支持就该拒绝。
悄悄改用浏览器残留身份执行，会让调用方以为自己是 X、系统却记成 Y。

### 2.3 Cookie + CSRF 双提交

| Cookie | HttpOnly | 用途 |
|---|---|---|
| `boip_access_token` | ✅ | 身份凭据本身，JS 读不到，XSS 偷不走 |
| `boip_csrf_token` | ❌（刻意） | 双提交令牌，JS 读出后经 `X-CSRF-Token` 头回传 |

HttpOnly 消灭了 XSS 窃取面，代价是 Cookie 会被浏览器**自动附带**——这是 Bearer
方案不需要、Cookie 方案必须补的一层，故引入 CSRF 双提交。非 HttpOnly 的 CSRF
cookie 被读走不构成泄露：单独持有随机串无法伪装身份，真凭据在 JS 永远拿不到的
那条 Cookie 里。

CSRF 与 SameSite 并存、不互相替代：SameSite 挡跨站自动携带，双提交覆盖"同源但
非预期来源""SameSite=none 的跨站部署"等残留面。比较使用 `hmac.compare_digest`
常量时间，避免时序侧信道。

---

## 三、实装清单

### 3.1 新增文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `backend/app/core/auth_cookies.py` | 241 | Cookie 唯一出口 + 凭据解析唯一实现 |
| `backend/app/core/csrf.py` | 71 | CSRF 双提交依赖 |
| `backend/app/core/security_audit.py` | 105 | append-only 安全审计写入 |
| `backend/alembic/versions/5d1a2b3c4e40_phase3_8_29_security_audit.py` | 51 | 扩展 `audit_logs.action` 约束 |
| `backend/tests/test_production_security.py` | 890 | 生产安全测试（49 例） |
| `scripts/lint/check_production_security.py` | 413 | 7 条生产红线静态扫描器 |
| `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` | 629 | 生产部署指南（T6） |

### 3.2 修改文件（本阶段范畴 18 个，+1104 / −137）

| 文件 | 关键改动 |
|---|---|
| `backend/app/core/config.py` | +166。新增 12 项配置、三态环境判定、`assert_production_safe()`、密钥黑名单、CORS 表态语义 |
| `backend/app/api/auth.py` | +192。login 种双 Cookie、logout/refresh 加 CSRF 依赖、三处安全审计、`_extract_token` 收敛 |
| `backend/app/identity/dependencies.py` | +110。`build_identity_service` 按 provider 装配，缺配置抛 `IdentityConfigError` |
| `backend/app/identity/verifier.py` | +94。`HttpJwksResolver` 真实 HTTP 拉取；缺 RS256 后端 fail-closed |
| `backend/app/core/security.py` | +46。凭据解析改走 `resolve_raw_token` |
| `backend/app/middleware/cors.py` | +25。生产读白名单，空值即无跨域，永不写 `*` |
| `backend/app/db/models/audit.py` | +6。CheckConstraint 扩展三种安全动作 |
| `backend/app/main.py` | +4。生产启动红线调用 |
| `frontend/src/lib/identity/token-store.ts` | +79。凭据不再由 JS 保管；新增 CSRF 读取与头构造 |
| `frontend/src/lib/identity/providers/backend-session.ts` | +105。双模式 `CredentialMode`，cookie 模式带 `credentials:include` |
| `frontend/src/app/login/page.tsx` | +74。迁移到 Cookie 流程，刻意不读响应体 token |
| `.github/workflows/identity-governance.yml` | +104。3 job → 7 job |
| `scripts/ci/local_ci.sh` | +23。8 步 → 10 步 |

---

## 四、六类 fail-closed 安全矩阵

| # | 类别 | 拒绝条件 | 验证用例 |
|---|---|---|---|
| 1 | Cookie 安全 | 生产未带 Secure / 越过唯一出口种 Cookie | Cookie 属性断言 + 扫描规则 1 |
| 2 | CSRF | 状态变更请求缺头 / 头与 Cookie 不匹配 | 403 断言（缺 Cookie、缺头、不匹配三分支） |
| 3 | OIDC 失败 | issuer/audience/JWKS 任一缺失；缺 RS256 后端 | `IdentityConfigError` / 验签拒绝 |
| 4 | 环境隔离 | 生产用测试密钥 / static-dev / 未表态 CORS / `*` / 无 Secure / 无 JWT_SECRET | `assert_production_safe()` 六分支 |
| 5 | 权限拒绝 | 无治理权限访问治理接口 | 403 + `permission_denied` 审计 |
| 6 | 身份异常 | 坏 token / 过期超宽限 / 非法 Authorization / 废止身份头 | 401/4xx + `identity_failure` 审计 |

**全部为拒绝式断言**：没有一条测试是"配置对了能跑通"，全部是"配置不对必须挡"。
安全测试证明"坏输入被拒"才有意义，证明"好输入能过"只是功能测试。

---

## 五、CI 生产门禁与扫描器有效性

### 5.1 七条红线

| # | 规则 | 拦截的真实事故 |
|---|---|---|
| 1 | Cookie 单一出口（仅 `auth_cookies.py` 可 `set_cookie`/`delete_cookie`） | 旁路种 Cookie 漏掉 HttpOnly/Secure/SameSite |
| 2 | 禁 JS 保管凭据（页面层禁 `writeGovernanceToken` 等、禁写 session/localStorage） | 重新打开 XSS 窃取面，让本阶段成果失效 |
| 3 | 禁 CORS 通配符 | `allow_origins=["*"]` + 凭据 Cookie = 向全网开放 |
| 4 | 禁关闭 TLS/验签（`verify=False`、`check_hostname=False` 等） | "能连上就行"式调试代码进生产 |
| 5 | 禁测试密钥进生产源码 | 测试密钥被当默认值带上生产 |
| 6 | `engineering_enabled` 必须 false | 最高红线① |
| 7 | 身份提供方缺省不得为 `static-dev` | 缺省即开发身份 = 默认无认证 |

纯标准库实现，无外部依赖；注释行、blessed 模块、测试目录、黑名单定义处均有精确
豁免。**当前干净仓库零误报**（含本阶段新增的 629 行部署文档）。

### 5.2 为扫描器本身写测试

新增 14 例（第 7 节），每条规则配"抓得住违规"+ 关键"不误报"样本，另有
`test_scanner_passes_on_current_repository` 守住当前树。

理由：**扫描器是唯一没有别人来检查的检查者。** 一个静默失效的扫描器比没有扫描
器更危险——它会让所有人以为红线还在守。用合成违规样本证明规则真会失败，是唯一
能持续验证它没坏的办法。

### 5.3 CI 工作流（7 job，任一失败禁合并）

`identity-static-scan` / `production-security-scan` / `backend-identity-tests` /
`backend-production-security` / `governance-permission-tests` /
`dependency-audit`（`pip-audit --strict` + `npm audit --audit-level=high`）/
`frontend-identity-tests`。

依赖扫描**不设** `continue-on-error`：设了它就只是一份没人看的报告。

---

## 六、前端凭据链路收敛

- `token-store.ts` 不再保管凭据，只读 CSRF 令牌；`sessionTokenSource` 标注
  `@deprecated`，仅留给非浏览器客户端与 E2E。
- `backend-session.ts` 引入 `CredentialMode`：`cookie`（默认）/ `bearer`（显式）。
- `login/page.tsx` 迁移完成 —— 这是最后一处未迁移的调用点。登录请求带
  `credentials:"include"`，且**刻意不读响应体的 `access_token`**：读了就等于把
  凭据重新交回 JS，HttpOnly 白做。登出调 `POST /api/auth/logout` 由服务端撤销。
- 测试用例 `缺省适配器走 Cookie 模式：配置判定不依赖 sessionStorage` 替换了原
  `缺省适配器读 sessionStorage 中的登录凭据`。旧语义会制造真实事故：用户登录
  成功（Cookie 已下发）但 sessionStorage 为空，页面误判未登录把人挡在门外。

---

## 七、测试覆盖

| 套件 | 结果 |
|---|---|
| `backend/tests/test_production_security.py` | **49 passed**（35 安全 + 14 扫描器自检） |
| `backend/tests` 全量 | **291 passed, 1 failed** —— 唯一失败为继承债，见 §十一 |
| `frontend/src/lib/identity` jest | **88 passed** |
| `tsc --noEmit`（identity/login 范围） | **0 error** |
| `check_production_security.py` | **exit 0**，7/7 通过 |

前端 tsc 全仓仍有 26 条**预存**噪音（jest-dom 类型未加载导致的 `toBeInTheDocument`
系列、`chat.ts` 的 `ApiResponse` 未导出、`.next/types` 生成类型），与本阶段无关，
未纳入范围。本阶段触及的 identity/login 范围为 0 错误。

---

## 八、修复的真实缺陷

### 8.1 `auth.py::_extract_token` 跨主体越权（本阶段发现并修复）

早期版本在 `auth.py` 内另写了一份"Cookie 优先"的凭据解析，与已收敛的"显式头
优先"规则**相反**。后果不是风格问题：浏览器登录过 A、脚本带着 B 的 Bearer 头调
`/refresh`，实际续的是 A 的会话，审计也记成 A；`/logout` 同理会把"另一个人"标记
为登出。修复为统一调用 `resolve_raw_token`。

**教训已固化为规则**：凭据解析只能有一处实现。第二处实现迟早与第一处分叉，而
分叉出来的那一处不会有人测。

### 8.2 动态加载 CLI 脚本时 dataclass 解析失败

`importlib.util.module_from_spec + exec_module` 加载扫描器时，`@dataclass` 注解
解析需回查 `sys.modules[cls.__module__]`，未登记则抛
`'NoneType' object has no attribute '__dict__'`（14 例集体失败）。修复：先
`sys.modules[name] = module` 再 `exec_module`，并在失败时清理登记。

### 8.3 CI 引用不存在的测试文件

`identity-governance.yml` 的 `governance-permission-tests` 引用了不存在的
`test_governance_rbac.py`。这类错误在"job 找不到文件就跳过"的配置下会**静默变成
永远绿灯**。改为实际存在的 `tests/test_rbac.py` + `test_governance_accountability.py`
+ `test_ci_scanners.py`。

---

## 九、生产配置契约（摘要）

完整清单见 `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`。生产必填/强制项：

| 项 | 要求 |
|---|---|
| `APP_ENV` | 必须精确为 `production` |
| `JWT_SECRET` | 随机强密钥，不得命中黑名单（`changeme`/`secret`/`test` 等 7 项） |
| `COOKIE_SECURE` | 生产由 `effective_cookie_secure` 强制 true，无法关闭 |
| `CSRF_PROTECTION_ENABLED` | 生产由 `effective_csrf_enabled` 强制 true |
| `CORS_ORIGINS` | 必须表态：白名单或 `none`；含 `*` 即拒绝启动 |
| `IDENTITY_PROVIDER` | `jwt` / `oidc` / `sso-gateway`；`static-dev` 禁止 |
| `STATIC_DEV_IDENTITY_ENABLED` | 必须 false |

`CORS_ORIGINS=none` 这个出口值得说明：区分"没配"（遗漏，必须拦）与"明确不需要"
（决策，同源部署本就不该开跨域）。没有这个出口，同源部署会被迫填一个假 Origin
才能启动，反而制造了本不存在的跨域授权。

---

## 十、残余风险与已知限制

| # | 风险 | 现状 | 建议 |
|---|---|---|---|
| 1 | OIDC 未经真实 IdP 联调 | 代码路径完整、缺配置 fail-closed，但**未对接过真实身份提供商** | 上生产前必须完成一次真实 IdP 联调（含公钥轮换观察） |
| 2 | `sso-gateway` 依赖部署方书面担保 | `SSO_GATEWAY_TRUSTED=true` 是人工声明，代码无法验证网络隔离 | 启用前执行部署指南 §8.3 的绕过验证 |
| 3 | Refresh 复用旧载荷 | `/refresh` 沿用原 token 的 roles/permissions 续期，未回查 DB | 权限变更在 TTL 内不即时生效；如需即时收权应缩短 `TOKEN_TTL_MINUTES` 或增加回查 |
| 4 | 审计写入与业务同库 | 独立提交但同数据库 | 高保障场景建议审计异地只追加副本 |
| 5 | 前端 tsc 预存噪音 26 条 | 与本阶段无关 | 单独开 hygiene 任务 |
| 6 | `tests/_tmp_drill_*` 历史债 | agents 套件历史遗留 | 单独修 hygiene，勿混入功能阶段 |

---

## 十一、范围外 / 未变更

### 11.1 继承债：`agents/enterprise/governance_traceability/`（**不在本阶段范围**）

工作树中存在 **Phase 3.8.27 未提交的产物**：未跟踪目录
`agents/enterprise/governance_traceability/`，以及 `agents/enterprise/audit.py`
中标注"Phase 3.8.27（Task 6）"的三个审计大类
（`GOVERNANCE_TRACE` / `GOVERNANCE_TIMELINE` / `GOVERNANCE_REPLAY`）。

它们使 `len(AuditActionCategory)` 由 69 变为 72，导致
`backend/tests/test_governance_persistence_workflow.py::test_audit_workflow_categories_reuse`
（断言 `== 69`）失败。

**判定**：与 3.8.29 无因果关系 —— 本阶段改动零涉及 `agents/`
（`git diff HEAD -- agents/enterprise/governance_traceability/` 为空）。
**处置**：仅登记，不修复、不提交，不纳入本阶段提交范畴。该债应由 3.8.27 的
收口负责人决定是提交、回退还是同步更新断言。

### 11.2 未变更项

- `agents/config.yaml:102` `engineering_enabled: false` —— **未改**（最高红线①）
- ESW 工程能力窗口维持 `OPEN_EMPTY`
- `agents/` 运行时、多智能体编排、治理智能中枢等前序阶段成果均未触碰
- 未新增任何 AI 自动审批 / 自动执行 / 自动评级路径

---

## 十二、验收标准与人工待办

### 12.1 已满足的验收标准

- [x] 凭据不再由 JS 保管，HttpOnly Cookie 下发，前端最后一处调用点已迁移
- [x] CSRF 双提交落地，生产强制开启，常量时间比较
- [x] IdP 适配器标准化，缺配置 fail-closed，无任何自动降级到开发身份的路径
- [x] 三态环境隔离，生产六项红线启动即校验
- [x] 五类安全事件 append-only 落库，结构性禁止 UPDATE/DELETE
- [x] CI 7 job 门禁 + 7 条红线扫描 + 依赖扫描，失败禁合并
- [x] 扫描器本身有 14 例有效性测试
- [x] 部署文档覆盖安装 / 环境变量 / 数据库 / 身份 / OIDC / 安全要求 / 回滚
- [x] 所有本阶段测试为拒绝式 fail-closed 断言

### 12.2 人工待办（**必须由主理人/运维完成，AI 不代劳**）

1. **真实 IdP 联调**：`IDENTITY_PROVIDER=oidc` 的端到端验证（残余风险 1）。
2. **密钥签发**：生产 `JWT_SECRET` 由密钥管理系统生成并注入，不进代码库。
3. **拓扑决策**：按部署指南 §1.1 选定同源/跨子域/跨站方案，确定 CORS 与 Cookie 配置。
4. **网络隔离验证**：若启用 `sso-gateway`，先完成绕过验证。
5. **备份演练**：审计表 PITR 恢复演练。
6. **继承债决策**：`agents/enterprise/governance_traceability/` 的去留（§11.1）。
7. **激活决策**：`engineering_enabled` 是否开启 —— **仅人类终端可执行**。

---

## 十三、收口声明

Phase 3.8.29 企业生产安全与部署强化层已按 T1–T7 全部建成，状态
**BUILT_NO_GO**：能力已具备，但**未获放行**。

六条最高红线全部保持：

1. `engineering_enabled` 保持 `false` —— 未改（`agents/config.yaml:102`）
2. 未输出任何 `engineering_approved`
3. 无 AI 自动评级路径
4. 无 AI 自动禁用/弃用路径
5. 无 AI 自动修改路径
6. Human-in-the-loop 未削弱 —— 本阶段所有新增能力均为**拒绝式**，不新增任何
   自动放行、自动审批或自动执行入口；`require_human_actor(USER)` 约束未松动

本阶段引入的全部新能力，性质上都是"让系统更容易拒绝"，没有一项是"让系统更容易
通过"。这是治理平台安全工作应有的方向。

**已停止，不进入 Phase 3.8.30，等待主理人审核。**

---

*报告生成：2026-08-09 | 分支 `feat/phase3.8.29-production-security` | 未 push*
