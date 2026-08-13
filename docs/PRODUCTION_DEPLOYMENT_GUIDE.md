# BOIP 生产部署指南（Production Deployment Guide）

> 适用版本：Phase 3.8.29 企业生产安全与部署强化层
> 适用对象：负责把 BOIP 治理平台部署到生产环境的运维/SRE/平台工程
> 文档性质：**可执行的部署契约**。文中每一条硬性要求都在代码里有对应的强制点
> （启动校验、依赖拒绝、CI 门禁），不是"建议最佳实践"。

---

## 0. 阅读须知：本系统的 fail-closed 立场

BOIP 是企业智能体**治理**平台，它记录的是"谁批准了什么"。因此系统在安全上
采取的一贯立场是：**配置不清楚时拒绝启动，而不是挑个默认值先跑起来。**

具体表现为三层强制，部署前请先建立这个心理预期：

| 层 | 强制点 | 违规后果 |
|---|---|---|
| 启动期 | `Settings.assert_production_safe()`（`backend/app/main.py` 在 `is_production` 时调用） | 进程**拒绝启动**并打印全部违规项 |
| 装配期 | `build_identity_service()`（`backend/app/identity/dependencies.py`） | 身份提供方配置不全 → `IdentityConfigError`，请求一律 401 |
| 交付期 | `scripts/lint/check_production_security.py`（CI 门禁，7 条红线） | CI 失败，**禁止合并** |

如果你在生产环境看到服务"启动失败并抱怨配置"，那不是 bug，是设计。请照错误
信息补配置，**不要**通过降级配置项绕过。

---

## 1. 部署拓扑

```
                       ┌──────────────────────────┐
  浏览器 ──HTTPS──────▶ │  反向代理 / 网关 (TLS 终止) │
                       └───────────┬──────────────┘
                                   │  X-Forwarded-Proto: https
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
            ┌─────────────────┐         ┌──────────────────┐
            │ Next.js 前端     │         │ FastAPI 后端      │
            │ (frontend/)     │  fetch  │ (backend/app)    │
            │ :3000           │────────▶│ :8000            │
            └─────────────────┘         └────────┬─────────┘
                                                 │
                        ┌────────────────────────┼───────────────┐
                        ▼                        ▼               ▼
                  PostgreSQL              Redis(可选)      对象存储(可选)
                  （含 audit_logs）
```

### 1.1 同源部署 vs 跨域部署（必须先做的一个决定）

这个决定会连锁影响 CORS、SameSite、Cookie Domain 三项配置，**先定它**：

- **方案 A：同源部署（推荐）**
  前端与后端挂在同一域名下（如 `https://boip.example.com` 走前端，
  `https://boip.example.com/api` 反代到后端）。
  → `CORS_ORIGINS=none`、`COOKIE_SAMESITE=lax`、`COOKIE_DOMAIN` 留空。
  安全面最小，不需要任何跨域授权。

- **方案 B：跨子域部署**
  前端 `https://app.example.com`、后端 `https://api.example.com`。
  → `CORS_ORIGINS=https://app.example.com`、`COOKIE_DOMAIN=.example.com`、
  `COOKIE_SAMESITE=lax`（同注册域属 same-site，Lax 够用）。

- **方案 C：完全跨站部署（不推荐）**
  前后端分属不同注册域。此时凭据 Cookie 必须 `SameSite=none`，浏览器要求
  同时 `Secure`，且第三方 Cookie 拦截策略会让链路脆弱。
  → 若无法避免，`COOKIE_SAMESITE=none` + `CORS_ORIGINS` 精确列举，
  并**必须**保持 CSRF 开启（此时它是主要防线，不再只是纵深防御）。

> `CORS_ORIGINS` 在生产**不允许留空**，也不允许 `*`。留空被判为"遗漏"，
> 通配符被判为"把携带凭据的跨域请求向全世界开放"。同源部署请显式填 `none`，
> 表示"我已就跨域表过态：不需要"。

---

## 2. 环境要求

| 组件 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.11+ | 后端运行时；仓库以 `backend/.venv` 为准 |
| Node.js | 18+（推荐 20 LTS） | 前端构建与运行 |
| PostgreSQL | 14+ | 主数据库；`audit_logs` 表在此 |
| Redis | 6+ | 可选，用于缓存/队列（未配置则相关功能降级但不影响身份链路） |

**关于 RS256 / OIDC 的额外依赖**：若 `IDENTITY_PROVIDER=oidc`，运行环境必须
安装 `cryptography`（RS256 验签后端）。缺失时验签器**不会假装验过**，而是
直接 fail-closed 拒绝——这是刻意的，见 §5.2。

---

## 3. 安装与构建

### 3.1 后端

```bash
cd BOIP/backend
python3.11 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

### 3.2 前端

```bash
cd BOIP            # 注意：npm workspaces 单仓，必须在根目录安装
npm install
npm run build --workspace frontend
```

> 单仓陷阱：在 `frontend/` 子目录里跑 `npm install` 会误报 `up to date`
> 而实际没装东西（依赖被提升到 `BOIP/node_modules`）。**始终在 `BOIP/` 根目录安装。**

---

## 4. 环境变量完整清单

以下变量由 `backend/app/core/config.py::Settings` 读取。标注 **【生产必填】**
的项若缺失或非法，`assert_production_safe()` 会拒绝启动。

### 4.1 运行环境

| 变量 | 取值 | 缺省 | 说明 |
|---|---|---|---|
| `APP_ENV` | `development` / `testing` / `production` | `development` | **【生产必填】** 必须精确为 `production` 才会启用生产红线 |
| `LOG_LEVEL` | `INFO` / `WARNING` / ... | `INFO` | 日志级别 |

> `APP_ENV` 写错（比如 `prod`、`Production`）会被判为**非生产**，于是所有
> 生产红线静默失效。部署后请务必用 §8.1 的自检确认环境判定生效。

### 4.2 数据存储

| 变量 | 缺省 | 说明 |
|---|---|---|
| `DATABASE_URL` | 空 | PostgreSQL 连接串，如 `postgresql+asyncpg://user:pass@host:5432/boip` |
| `REDIS_URL` | 空 | 可选 |
| `QDRANT_URL` | 空 | 可选，向量检索 |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET` | 空 | 可选，对象存储 |

### 4.3 身份与凭据

| 变量 | 缺省 | 说明 |
|---|---|---|
| `JWT_SECRET` | 空 | **【生产必填】** HS256 签名密钥。禁止使用已知测试密钥（见 §4.6） |
| `IDENTITY_PROVIDER` | `jwt` | `jwt` / `oidc` / `sso-gateway`。生产禁止 `static-dev` |
| `STATIC_DEV_IDENTITY_ENABLED` | `false` | **【生产必须 false】** 开发逃生舱开关 |
| `OIDC_ISSUER` | 空 | `IDENTITY_PROVIDER=oidc` 时必填 |
| `OIDC_AUDIENCE` | 空 | 同上 |
| `OIDC_JWKS_URL` | 空 | 同上 |
| `SSO_GATEWAY_TRUSTED` | `false` | `IDENTITY_PROVIDER=sso-gateway` 时必须显式 `true` |
| `TOKEN_TTL_MINUTES` | `60` | access token 有效期 |
| `REFRESH_GRACE_MINUTES` | `15` | 过期后仍可 `/refresh` 的宽限期 |

### 4.4 Cookie 策略

| 变量 | 缺省 | 说明 |
|---|---|---|
| `AUTH_COOKIE_NAME` | `boip_access_token` | HttpOnly 凭据 Cookie 名 |
| `COOKIE_SECURE` | `false` | 生产由 `effective_cookie_secure` **强制为 true**，无法关闭 |
| `COOKIE_SAMESITE` | `lax` | `lax` / `strict` / `none`（非法值回落 `lax`） |
| `COOKIE_DOMAIN` | 空 | 留空则不写 Domain 属性（严格同域）；跨子域填 `.example.com` |

### 4.5 CSRF

| 变量 | 缺省 | 说明 |
|---|---|---|
| `CSRF_COOKIE_NAME` | `boip_csrf_token` | 非 HttpOnly，供 JS 读取回填 |
| `CSRF_HEADER_NAME` | `X-CSRF-Token` | 回填的请求头名 |
| `CSRF_PROTECTION_ENABLED` | `false` | 生产由 `effective_csrf_enabled` **强制为 true** |

### 4.6 CORS

| 变量 | 缺省 | 说明 |
|---|---|---|
| `CORS_ORIGINS` | 空 | **【生产必填】** 逗号分隔白名单，或填 `none`/`disabled` 声明同源部署 |

### 4.7 被拒绝的密钥黑名单

以下字面量出现在 `JWT_SECRET` 中，生产启动即失败
（`KNOWN_TEST_SECRETS`，`backend/app/core/config.py`）：

```
test-jwt-secret-not-for-production, changeme, change-me, secret, test, password, ""(空)
```

生成合规密钥：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4.8 前端环境变量

| 变量 | 说明 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 后端基址，如 `https://boip.example.com`（同源部署可用相对路径策略） |
| `NEXT_PUBLIC_IDENTITY_PROVIDER` | 前端身份适配器选择；生产应为后端会话模式，**不得**指向 static-dev |
| `NEXT_PUBLIC_GOVERNANCE_DEV_TOKEN` | **生产严禁设置**。它是开发期注入令牌的口子 |

> 前端凡是 `NEXT_PUBLIC_*` 的值都会被打进产物、对任何访客可见。
> 生产构建前请确认这些变量里**没有任何机密**。

### 4.9 生产 `.env` 参考（同源部署，方案 A）

```dotenv
APP_ENV=production
LOG_LEVEL=INFO

DATABASE_URL=postgresql+asyncpg://boip:<STRONG_PASSWORD>@db.internal:5432/boip

JWT_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(48))" 的输出>
IDENTITY_PROVIDER=jwt
STATIC_DEV_IDENTITY_ENABLED=false

AUTH_COOKIE_NAME=boip_access_token
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=

CSRF_PROTECTION_ENABLED=true
CSRF_COOKIE_NAME=boip_csrf_token
CSRF_HEADER_NAME=X-CSRF-Token

TOKEN_TTL_MINUTES=60
REFRESH_GRACE_MINUTES=15

# 同源部署：显式声明不需要跨域
CORS_ORIGINS=none
```

---

## 5. 身份链路配置

### 5.1 凭据是怎么走的（部署方必须理解的一张图）

```
① 登录  POST /api/auth/login  {email, password}
        ↓
   后端签发 HS256 token
        ↓
   Set-Cookie: boip_access_token=<token>; HttpOnly; Secure; SameSite=Lax
   Set-Cookie: boip_csrf_token=<random>;              Secure; SameSite=Lax
        （前者 JS 读不到，后者故意让 JS 读）

② 后续请求
   浏览器自动带上两条 Cookie
   前端 JS 读出 csrf cookie → 放进 X-CSRF-Token 头
        ↓
   后端 csrf_protect 比对「Cookie 值 == 请求头值」（常量时间比较）
        ↓
   身份解析：resolve_raw_token(request, Authorization)
        ├─ 有 Authorization 头 → 只认它（显式独占，非法也不回落 Cookie）
        └─ 完全没有头       → 用 Cookie 兜底
```

**凭据通道优先级不可反转**，这是安全语义而非风格偏好：

`Authorization` 头是调用方**本次显式声明**的身份；Cookie 是浏览器**自动附带**
的环境凭据。若让 Cookie 压过显式头，会出现真实事故：同一浏览器登录过 A，
运维脚本带着 B 的 Bearer 头调 `/api/auth/refresh`，实际续的是 A 的会话、审计
也记成 A —— 在多租户治理场景里这就是**责任人张冠李戴**。

同理，若 `Authorization` 头存在但非法（如 `Basic xxx`），系统**不回落 Cookie**，
直接判无凭据返回 401。宁可让调用方改正，也不做静默的身份替换。

### 5.2 三种身份提供方

由 `IDENTITY_PROVIDER` 选择，装配逻辑见 `backend/app/identity/dependencies.py::build_identity_service`。

#### (a) `jwt`（默认，当前生产可用）

HS256 JWT + 数据库权威解析（角色/权限以 DB 为准，不信任 token 里的自述）。
只需 `JWT_SECRET`。

#### (b) `oidc`（对接企业 IdP）

必须三点齐全，缺一即 `IdentityConfigError` 拒绝启动：

```dotenv
IDENTITY_PROVIDER=oidc
OIDC_ISSUER=https://idp.example.com/
OIDC_AUDIENCE=boip-governance
OIDC_JWKS_URL=https://idp.example.com/.well-known/jwks.json
```

`HttpJwksResolver` 会真实发起 HTTP 拉取公钥。**重要**：若运行环境缺少
RS256 验签后端（`cryptography`），验签器不会退化成"跳过验签"，而是直接
失败。一个"不能验签却放行"的 OIDC 比没有 OIDC 危险得多。

对接 checklist：
- [ ] IdP 侧已为 BOIP 注册 client，audience 与 `OIDC_AUDIENCE` 一致
- [ ] JWKS URL 从**后端所在网络**可达（注意内网出口/代理）
- [ ] 已确认公钥轮换周期，并接受 JWKS 拉取的缓存/重试行为
- [ ] `cryptography` 已随 `requirements.txt` 安装

#### (c) `sso-gateway`（信任前置网关）

仅当后端**在网络层面不可从网关外直达**时才允许：

```dotenv
IDENTITY_PROVIDER=sso-gateway
SSO_GATEWAY_TRUSTED=true
```

`SSO_GATEWAY_TRUSTED` 是部署方的**书面担保**。若后端可被绕过网关直接访问，
攻击者伪造网关头即可冒充任意身份。开启前请先用 §8.3 验证网络隔离。

### 5.3 生产禁用项

| 项 | 生产状态 | 强制点 |
|---|---|---|
| `static-dev` 身份提供方 | **禁止** | `PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS` + 启动校验 + 装配校验 |
| `STATIC_DEV_IDENTITY_ENABLED=true` | **禁止** | `assert_production_safe()` |
| 已废止身份头 `X-Actor-Id` / `X-Actor-Kind` | **报错**，不静默忽略 | `assert_no_legacy_identity_headers()` |

最后一条值得解释：静默忽略这些头在功能上是安全的（后端本来就不读），但在
运维语义上很危险——调用方会**以为**自己成功指定了责任人。治理系统里"我以为
记的是张三、实际记的是李四"属于责任错置，比直接失败严重得多。

---

## 6. 数据库与审计

### 6.1 迁移

```bash
cd BOIP/backend
./.venv/bin/alembic upgrade head
```

Phase 3.8.29 引入迁移 `5d1a2b3c4e40_phase3_8_29_security_audit`
（`down_revision = 4c9d7e1f2a30`），作用是扩展 `audit_logs.action` 的
CheckConstraint，允许新增三种安全动作。

### 6.2 审计表是 append-only

`audit_logs` 记录五类安全事件，写入口径唯一
（`app.core.security_audit.record_security_event`）：

| action | 触发时机 |
|---|---|
| `login` | 登录成功 |
| `logout` | 登出 |
| `token_refresh` | 令牌刷新成功 |
| `permission_denied` | 治理权限被拒（403） |
| `identity_failure` | 身份校验失败（401 / 身份类 403） |

约束方式是**结构性**的，不是靠约定：

- 本模块**只提供写入**，没有 UPDATE/DELETE 路径，路由层也不暴露；
- `action` 受数据库 CheckConstraint 约束，写入范围外的动作被数据库挡回；
- 新增动作必须**先加迁移改约束**，再写代码。

审计写入使用独立提交：即使后续业务事务回滚，安全留痕也保留。

### 6.3 未知主体的记法

身份失败时往往还不知道"是谁"（坏 token、跨组织复用）。`tenant_id` 非空约束
不能破，故用全零 UUID `SECURITY_AUDIT_SYSTEM_TENANT`
（`00000000-0000-0000-0000-000000000000`）标记"该事件不属于任何真实租户"。

运维排查时可直接筛：

```sql
SELECT created_at, action, actor_id, target_id, payload
FROM audit_logs
WHERE tenant_id = '00000000-0000-0000-0000-000000000000'
ORDER BY created_at DESC
LIMIT 100;
```

### 6.4 备份要求

审计表是问责链的物证。备份策略至少满足：

- [ ] 每日全量 + WAL 归档（PITR 能力）
- [ ] 备份介质与主库**隔离账号**，主库账号无权删除备份
- [ ] 定期演练恢复（备份没恢复过 = 没有备份）

---

## 7. 反向代理与 TLS

### 7.1 必须项

- [ ] 全站 HTTPS，HTTP 一律 301 到 HTTPS
- [ ] 代理向后端透传 `X-Forwarded-Proto: https`（否则 Secure Cookie 行为可能异常）
- [ ] 代理**不得**改写或剥离 `X-CSRF-Token` 头
- [ ] 代理**不得**注入 `Authorization` 头（会覆盖调用方显式凭据，见 §5.1）

### 7.2 Nginx 参考（同源部署）

```nginx
server {
    listen 443 ssl http2;
    server_name boip.example.com;

    ssl_certificate     /etc/ssl/boip/fullchain.pem;
    ssl_certificate_key /etc/ssl/boip/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 8. 上线自检（Go/No-Go Checklist）

### 8.1 启动前静态检查

```bash
cd BOIP
python3 scripts/lint/check_production_security.py --root .
```

该扫描器覆盖 7 条红线（纯标准库，无外部依赖）：

| # | 规则 | 拦截的事故 |
|---|---|---|
| 1 | Cookie 单一出口 | 绕过 `auth_cookies.py` 直接 `set_cookie`，漏掉 HttpOnly/Secure/SameSite |
| 2 | 禁 JS 保管凭据 | 页面层把 token 写进 sessionStorage/localStorage，重新打开 XSS 窃取面 |
| 3 | 禁 CORS 通配符 | `allow_origins=["*"]` 配合凭据 Cookie 等于向全网开放 |
| 4 | 禁关闭 TLS 校验 | `verify=False` / `check_hostname=False` 等 |
| 5 | 禁测试密钥进源码 | 测试密钥被误当默认值带上生产 |
| 6 | `engineering_enabled` 必须 false | 最高红线①（`agents/config.yaml`） |
| 7 | 身份提供方缺省不得为 `static-dev` | 缺省即开发身份，等于默认无认证 |

退出码 `0` 通过、`1` 有违规。**扫描器是"以后也回不到错的写法"的保险，
与测试互补**：测试证明当前实现正确，扫描证明未来不会退回错误写法。

### 8.2 启动后运行时验证

```bash
BASE=https://boip.example.com

# ① 登录应下发两条 Cookie，凭据 Cookie 必须 HttpOnly + Secure
curl -si -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"<PASSWORD>"}' \
  | grep -i 'set-cookie'
# 期望：boip_access_token=...; HttpOnly; Secure; SameSite=lax
#       boip_csrf_token=...;             Secure; SameSite=lax   （无 HttpOnly）

# ② 无 CSRF 头的状态变更请求必须 403
curl -si -X POST "$BASE/api/auth/logout" -b cookies.txt | head -1
# 期望：HTTP/1.1 403

# ③ 非法 Authorization 头不得回落 Cookie
curl -si "$BASE/api/auth/me" -b cookies.txt -H 'Authorization: Basic Zm9vOmJhcg==' | head -1
# 期望：HTTP/1.1 401（而不是 200）

# ④ 已废止身份头必须报错而非忽略
curl -si "$BASE/api/governance/me" -b cookies.txt -H 'X-Actor-Id: someone' | head -1
# 期望：4xx
```

### 8.3 `sso-gateway` 专项验证（仅当启用）

```bash
# 从网关外部直接访问后端端口，必须不可达
curl -m 5 -si http://<backend-internal-ip>:8000/api/auth/me
# 期望：连接超时 / 拒绝。若能通，立刻停用 sso-gateway 模式
```

### 8.4 清单

- [ ] `APP_ENV=production` 且服务成功启动（说明 `assert_production_safe()` 已通过）
- [ ] `JWT_SECRET` 为随机强密钥，不在黑名单内，且**与非生产环境不同**
- [ ] `CORS_ORIGINS` 已表态（白名单或 `none`），不含 `*`
- [ ] 凭据 Cookie 实测带 `HttpOnly; Secure`
- [ ] CSRF 缺头请求实测 403
- [ ] `alembic upgrade head` 已执行，`audit_logs` 新约束生效
- [ ] 数据库备份与恢复演练完成
- [ ] `check_production_security.py` 退出码 0
- [ ] CI 全绿（含依赖扫描 `pip-audit` / `npm audit`）
- [ ] `agents/config.yaml` 的 `engineering_enabled` 仍为 `false`

---

## 9. CI/CD 门禁

工作流 `.github/workflows/identity-governance.yml` 共 7 个 job，
**任一失败即禁止合并**（依赖扫描不设 `continue-on-error`）：

| Job | 内容 |
|---|---|
| `identity-static-scan` | 遗留身份头等静态扫描 |
| `production-security-scan` | 上述 7 条生产红线 |
| `backend-identity-tests` | 身份链路 pytest |
| `backend-production-security` | `backend/tests/test_production_security.py` |
| `governance-permission-tests` | RBAC / 问责 / 扫描器测试 |
| `dependency-audit` | `pip-audit --strict` + `npm audit --audit-level=high` |
| `frontend-identity-tests` | 前端 identity 层 jest |

本地等价执行：

```bash
bash scripts/ci/local_ci.sh     # 共 10 步，第 10 步为生产红线扫描
```

---

## 10. 回滚方案

### 10.1 决策原则

**代码可以快速回滚，数据库迁移和密钥轮换不行。** 因此回滚顺序固定为：
先回代码 → 判断是否必须回迁移 → 最后才考虑密钥。

### 10.2 应用回滚

```bash
# 后端（以 git 部署为例）
git checkout <上一个已知良好 tag>
cd backend && ./.venv/bin/pip install -r requirements.txt
systemctl restart boip-backend

# 前端
cd BOIP && npm install && npm run build --workspace frontend
systemctl restart boip-frontend
```

### 10.3 数据库回滚

Phase 3.8.29 的迁移只**放宽** CheckConstraint（新增三种允许的 action），
因此：

- **回退代码但不回退迁移是安全的**：旧代码只写旧动作，新约束是超集。
- **只有在必须回到 4c9d7e1f2a30 之前**才需要降级，且降级前必须先清理新动作
  行，否则约束重建会失败：

```bash
# 1) 确认是否存在新动作记录
psql "$DATABASE_URL" -c "SELECT action, count(*) FROM audit_logs \
  WHERE action IN ('token_refresh','permission_denied','identity_failure') GROUP BY action;"

# 2) 若存在：审计不可删除。请改为「保留迁移、只回代码」，不要执行 downgrade。
#    确需降级时，必须先经主理人书面批准并完成审计归档导出。

# 3) 归档导出后（且获批）方可降级
cd BOIP/backend && ./.venv/bin/alembic downgrade 4c9d7e1f2a30
```

> **审计数据不得为了让迁移降级成功而删除。** 删审计记录以配合回滚，等于为了
> 技术方便销毁问责证据，属于本平台的性质错误。默认答案是"保留迁移、只回代码"。

### 10.4 凭据紧急失效（怀疑密钥泄露）

轮换 `JWT_SECRET` 会使**所有在途 token 立即失效**，全体用户被强制登出。
这是紧急止血手段，不是常规操作：

```bash
NEW=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
# 写入密钥管理系统后重启后端
systemctl restart boip-backend
```

轮换后请在审计表确认异常主体的活动窗口：

```sql
SELECT created_at, action, actor_id, target_id
FROM audit_logs
WHERE action IN ('login','token_refresh','identity_failure')
  AND created_at >= now() - interval '7 days'
ORDER BY created_at DESC;
```

### 10.5 回滚后必做

- [ ] 复跑 §8.2 运行时验证
- [ ] 确认审计写入正常（做一次登录，查 `audit_logs` 是否新增 `login`）
- [ ] 在变更单登记回滚原因与影响范围

---

## 11. 故障排查

| 现象 | 最可能原因 | 处理 |
|---|---|---|
| 启动即报"生产配置安全检查未通过" | `assert_production_safe()` 拦截 | 照错误列表逐条补配置，**不要**改 `APP_ENV` 绕过 |
| 启动报 `IdentityConfigError` | OIDC 三项不全 / `SSO_GATEWAY_TRUSTED` 缺失 / provider 拼写错 | 补齐 §5.2 对应配置 |
| 登录成功但后续请求全 401 | 前端未带 `credentials: "include"`；或 Cookie Domain/SameSite 与部署拓扑不匹配 | 核对 §1.1 方案选择 |
| 所有 POST 都 403 且提示 CSRF | 前端未回填 `X-CSRF-Token`，或代理剥离了该头 | 检查代理配置（§7.1） |
| 浏览器不保存 Cookie | 站点非 HTTPS 而 Cookie 带 `Secure` | 生产必须 HTTPS，这是强制的 |
| OIDC 模式一律验签失败 | 缺 `cryptography`，或 JWKS URL 从后端网络不可达 | 装依赖 / 打通网络；**禁止**改成跳过验签 |
| 脚本用 Bearer 头却以别人身份执行 | 不应再出现（3.8.29 已修复）；若出现说明有旁路解析 | 检查是否有绕过 `resolve_raw_token` 的自写解析 |

---

## 12. 安全边界声明（部署方必须知晓）

本系统在设计上**不会**做以下事情，部署时请不要期待它们存在：

1. **不会自动降级身份。** 任何身份配置不全的情况都表现为拒绝，而不是回落到
   开发身份或匿名放行。
2. **不会由 AI 获得治理权限。** 审批、评级、禁用、修改等治理动作必须由
   `USER` 类型的真实主体执行，系统强制 human-in-the-loop。
3. **不会自动执行治理决定。** 平台产出建议与证据，落地动作需人工确认。
4. **不会静默忽略可疑输入。** 废止的身份头、非法的 Authorization、缺失的
   CSRF 头，一律报错而非忽略。

`agents/config.yaml` 的 `engineering_enabled` 在本阶段仍为 `false`，
工程能力窗口保持 `OPEN_EMPTY`，需主理人与专家线下提交真实证据后由人类终端
显式开启——**不得**通过部署配置绕过。

---

## 13. 生产发布闸门与证据包（Phase 3.9.2）

本阶段在「部署前」再加一道**只读闸门 + 人工签署**层。它**不是部署工具**，也**不替你做发布决定**——它只把"是否达到人工签署门槛"这件事，用结构化的证据与 13 项检查固化下来，交给真实责任人去签 GO / NO-GO / NEED_MORE_EVIDENCE。

### 13.1 它做什么、不做什么

- **做**：核验仓库事实（git 完整性 / commit SHA / 全量测试绿 / 安全扫描 / 身份扫描 / 治理质量门 / 预生产验证 / 回滚演练 / 恢复校验 / DB 迁移态 / 配置基线 / 部署文档 / 证据完整度），生成 SHA-256 证据清单（Release Package Manifest）。
- **不做**：不部署、不激活、不翻转 `engineering_enabled`、不写真实密钥、不授真实权限、不代替任何人签字、不输出 `engineering_approved`、不返回 `APPROVED`/`GO`。

> 闸门结论只有三态：`BLOCKED`（有硬缺失）→ `PENDING_VERIFICATION`（有标记待线下验证项）→ `READY_FOR_HUMAN_REVIEW`（材料齐备，等真人签）。**永不**自动 GO。

### 13.2 13 项检查（CHECK_KEYS）

`git_workspace_integrity` · `commit_sha_exists` · `full_test_results_green` · `production_security_scanner` · `identity_security_scanner` · `governance_quality_gate` · `staging_validation` · `rollback_drill` · `recovery_validation` · `database_migration_status` · `configuration_baseline` · `deployment_documentation` · `evidence_completeness`

任何一项缺失 → `BLOCKED`；有项标 `pending_verification` → `PENDING_VERIFICATION`；全部齐备 → `READY_FOR_HUMAN_REVIEW`。

### 13.3 证据包与清单（SHA-256）

- `ProductionReleaseEvidenceService` 收集证据：客观事实（文件存在、测试通过）标 `VERIFIED`；人工依赖项（human_signoff / production_secret）**恒 `PENDING_VERIFICATION`**——AI 不代填、不把 PENDING 抬成 VERIFIED。
- `ProductionReleaseService.build_manifest` 对存在的交付物算 SHA-256，缺文件标 `<missing>`（不伪造哈希）。清单是**证据**，不是放行令。

### 13.4 人工签署（唯一合法出口）

- 签署角色：`PRODUCTION_OWNER` / `RELEASE_MANAGER` / `SECURITY_OWNER` / `AUDITOR`。
- 决策：`GO` / `NO_GO` / `NEED_MORE_EVIDENCE`，**只能由 `USER` 类型真实主体**提交。
- API：`POST /governance/releases/{id}/signoff`（需 `governance:release:signoff`，仅 `governance-admin` 拥有；AI 主体 403）。前端：`/governance-release` 页，**无自动上线按钮、无 AI 批准按钮**。
- 每次签署落审计：`RELEASE_SIGNOFF_RECORDED`（actor 强制 `USER`）。另有 `RELEASE_CANDIDATE_CREATED` / `RELEASE_GATE_EVALUATED` / `RELEASE_MANIFEST_GENERATED` 三个审计类，合计使审计枚举总数达 **83**。

### 13.5 红线（fail-closed，AI 不可破）

`agents/enterprise/production_release/forbidden.py` 含 **314** 项禁名（含历史治理禁集并集），由 `_RedLineForbiddenMixin` 在结构级拦截：真部署 / 出 `approved` / 自动批准 / AI 代签 / 写真实密钥 / 授真实权限 / 翻转 `engineering_enabled` 一律调用即抛。全程 `engineering_enabled` 保持 `false`。

### 13.6 收口状态

本层状态 **BUILT_NO_GO**：闸门与证据体系已建成并通过验证，但**未开启生产、未进入自动激活**。最终生产发布（开 `engineering_enabled`、真部署、真签 GO）只能源于主理人在人类终端的线下决策。详见 `.ai/reviews/phase3.9.2_production_release_gate_evidence_package_report.md` 与 `.ai/roadmap_v8.md` §35。

---

## 14. 生产可观测性、SRE 与事故响应准备层（Phase 3.9.3）

### 14.1 它做什么、不做什么

- **做**：建成「生产可观测性 / SRE / 事故响应准备层」——服务健康模型（11 类组件，状态 `HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN`）、指标聚合（可用性 / 延迟分位，全 `simulation_only`）、SLI/SLO（阈值未验证 → `PENDING_VERIFICATION`）、错误预算（只计算不触停发布/回滚）、告警候选与去重关联、事故模型（SEV0–3、8 态无 `AUTO_*`）、事故时间线（append-only）、事故指挥指派（仅 `USER`）、Runbook 引用（只引用不执行）、事故响应草稿（`requires_human_review=True`）、恢复校验、Postmortem 草稿、治理整改关联、发布/安全信号关联。
- **不做**：不真接入 Prometheus/OpenTelemetry/Loki 等真实数据源；不真发送告警 / 不触真实 on-call；不自动修复、不自动回滚、不自动关单、不自动 ACK；不以任何方式描述模拟数据为真实 production observation。

### 14.2 关键 fail-closed 不变量

- `ServiceHealthService.overall_status`：`UNKNOWN` 绝不回退为 `HEALTHY`（探测缺失 = 不健康，宁错杀）。
- 告警/事故所有 `RESOLVE` / `CLOSE` / `ACKNOWLEDGE` 仅接受 `actor_kind == "user"`，AI 主体一律 403 或抛 `EnterpriseRedLineViolationError`。
- `correlate_release` 只注入 `rollback_reference`，显式 `auto_rollback=False`；`correlate_security_signals` 中 `threshold_verified=False`，绝不自动关 Incident。
- `forbidden.py` 含 **337** 项禁名（`auto_rollback_incident` / `auto_resolve_incident` / `auto_close_incident` / `assign_self_as_commander` / `act_as_incident_commander` / `silence_alert` / `fabricate_observability_evidence` 等），结构级调用即抛。
- 审计 +7 类（`OBSERVABILITY_HEALTH_CHECK` / `ALERT_CANDIDATE_CREATED` / `INCIDENT_CREATED` / `INCIDENT_HUMAN_ACKNOWLEDGED` / `INCIDENT_HUMAN_RESOLVED` / `INCIDENT_HUMAN_CLOSED` / `POSTMORTEM_DRAFT_CREATED`），`actor_kind` 恒 `USER`，当前总数 96（本阶段 89 → 96，含前序 3.9.2 受控激活/RC冻结层遗留 +6）。

### 14.3 人工动作入口

- 只读看板：`GET /governance/observability/health|metrics|slo|incidents`（合成全 `UNKNOWN` + `simulation_only=true`，前端 `/governance-observability`）。
- 人工动作（须 `governance:incident:action`，仅 admin；须填 incident_id + 理由）：`POST /governance/observability/incidents/{id}/acknowledge|assign-commander|resolve|close`，返回 `auto_state_transition: false`，落审计。
- 真实故障指挥、关单、回滚、恢复执行只能源于主理人 / SRE / incident-commander 在人类终端的线下决策。

### 14.4 收口状态

本层状态 **BUILT_NO_GO**：可观测性 / SRE / 事故响应准备体系已建成并通过验证，但**未真接入生产、未发送真实告警、未进入自动修复**。详见 `.ai/reviews/phase3.9.3_production_observability_incident_readiness_report.md` 与 `.ai/roadmap_v8.md` §35.2。

## 15. 生产遥测接入适配与合成运维验证层（Phase 3.9.4）

### 15.1 它做什么、不做什么

- **做**：把「遥测接入」抽象成 `TelemetryProvider` 端口（ABC + 5 抽象方法： `check` / `query_health` / `query_metrics` / `query_traces` / `query_logs`），并提供 Synthetic / Prometheus / OpenTelemetry 三类适配器 + 归一化 + 聚合 + 注册表 + 告警路由 + 合成故障演练编排。
- **不做**：**不真接入**真实生产数据源（未配置真实源时返回空 / `NOT_CONFIGURED`，绝不降级伪装为 Synthetic，红线⑪）；**不真发送** PagerDuty / 企业微信 / Slack / Email 告警（红线⑫）；**不自动**回滚 / 关单 / ACK / RESOLVE / CLOSE（红线⑨）；**不自动执行** Runbook（红线⑬）；**不替代** SRE / incident-commander / production-owner（红线⑩）。

### 15.2 关键 fail-closed 不变量

- `TelemetryProvider` 端口未配置真实源 → 空 / `NOT_CONFIGURED`，**绝不降级伪装为 Synthetic（红线⑪）**。
- `TelemetryAggregator`：仅合成源时返回 `synthetic_only`，**不判 `operational`（红线⑪）**。
- `TelemetryProviderRegistry.get_production_provider`：仅返回真实已配置源，合成源**不 fallback** 顶替真实源；缺失真实源 → `pending_verification=True`。
- `TelemetryAlertRouter`：合成源仅 `SIMULATED_DELIVERY`（模拟投递），未配置源 → `null`；**禁真实外发**。
- 合成演练 Incident 状态恒 `open`，`auto_rollback/auto_resolve/auto_close/auto_acknowledge` 全 `False`；`delivery == simulated_delivery`；`human_actions` 仅 `close` 经真实 USER 后才 → `closed_by_human`。
- `forbidden.py` 含 **102** 项禁名（`send_real_pagerduty_alert` / `send_real_wechat_alert` / `auto_rollback_incident` / `auto_resolve_incident` / `auto_close_incident` / `execute_runbook` / `act_as_sre` / `fabricate_telemetry_evidence` 等），结构级调用即抛。
- 审计 +4 类（`TELEMETRY_PROVIDER_CHECKED` / `SYNTHETIC_DRILL_STARTED` / `SYNTHETIC_DRILL_COMPLETED` / `TELEMETRY_EVIDENCE_RECORDED`），`actor_kind` 恒 `USER`，当前总数 **100**（96 → 100，与 `.ai/baselines/phase3.8_governance_release_baseline.json` `audit_category_contract.total = 100` 一致）。

### 15.3 人工动作入口

- 只读看板：`GET /governance/telemetry/providers|summary|/{provider_id}/health|metrics|traces|logs`（合成全 `simulation_only=true`，前端 `/governance-observability` 的「生产遥测接入与合成运维验证」区块）。
- 巡检：`POST /governance/telemetry/{provider_id}/check`（OBSERVABILITY_READ，落审计）。
- 合成演练（须 `governance:incident:action`，仅 admin；生产环境 `is_production=True` → 403）：`POST /governance/telemetry/synthetic/run`，返回 `auto_*: false` + `delivery: simulated_delivery` + `status: open`，**不真接入、不真外发、不自动修复**。
- 真实数据源接入、真实告警外发、真实事故指挥 / 回滚 / 恢复执行只能源于主理人 / SRE / incident-commander 在人类终端的线下决策。

### 15.4 收口状态

本层状态 **BUILT_NO_GO**：遥测接入适配与合成运维验证体系已建成并通过验证，但**未真接入生产遥测源、未真发送告警、未进入自动修复 / 回滚**。详见 `.ai/reviews/phase3.9.4_telemetry_synthetic_operations_report.md` 与 `.ai/roadmap_v8.md` §35.4。

---

## 16. 生产激活证据准备层（Phase 3.9.6）

> 完整治理纪律见姊妹文档 `PRODUCTION_ACTIVATION_GOVERNANCE_GUIDE.md`。本节只给部署方最关键的结论。

### 16.1 它做什么、不做什么

- **做**：把前序各阶段能力收拢为「生产激活就绪 dossier」——软件证据包 v2、四角色签署要求、SoD 校验、就绪闸门（8 检查）、阻断器 B1–B6、pending 登记 PV1–PV6、机器可读复核包、工程激活契约、后端 API（8 路由，无 `/activate`）、前端看板、CI 门禁。
- **不做**：**不激活** `engineering_enabled`（保持 `false`）；**不部署**；**不宣布 GO / APPROVED**；**不自动**生成真实工程参数 / 报价 / 评级；**不替代**四角色或主理人的人工责任；**不提供**任何 `/activate` 或 `/deploy-production` 端点（红线①–⑧）。

### 16.2 关键 fail-closed 不变量

- 终端态恒为 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`（模块常量，不可被运行时改写）。
- `ProductionActivationReadinessGate` 状态只可能是 `BLOCKED` / `PENDING_VERIFICATION` / `READY_FOR_HUMAN_SIGNOFF`，**永不 `APPROVED`**；`set_engineering_enabled(...)` 触发 `EnterpriseRedLineViolationError`。
- 当前态：闸门 `blocked`（证据包未齐 / B1–B6 未解 / PV1–PV6 未清 / 四角色未签），`contract.activation_allowed_for_human == False`。
- 审计真实 +4 类（`ACTIVATION_EVIDENCE_SUBMITTED` / `ACTIVATION_EVIDENCE_VALIDATED` / `HUMAN_SIGNOFF_REGISTERED` / `ACTIVATION_REVIEW_PACKAGE_GENERATED`），基线 100 → 104，与 `.ai/baselines/audit_action_category_ledger.json` `total=104` 一致。
- `ACTIVATION_READINESS_FORBIDDEN_COUNT = 340`（结构级禁名，`forbidden.py` 调用即抛）。

### 16.3 人工动作入口（唯一合法出口）

- 只读看板：`GET /governance/activation/readiness|evidence|blockers|pending-verifications|signoff-requirements|contract|review-packet`。
- 真实人工签署（须 `governance:release:signoff`，仅 admin；强制 `actor_kind="user"` + 非空 `signature_reference`）：`POST /governance/activation/signoff`。
- **真激活**是主理人在**人类终端**显式置 `engineering_enabled=true` 这一唯一动作（见 `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`），AI 不代执行。

### 16.4 收口状态

本层状态 **PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO**：全部软件证据 / 人工责任结构 / 检查清单包 / 回滚包 / 签署模板 / Go-No-Go 输入已就位，但**无真实生产激活**。详见 `.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md` 与 `.ai/roadmap_v8.md` §35.10 / §35.11。

---

## 17. 生产变更管控层（Phase 3.9.7-change）

> 完整治理纪律见姊妹文档 `PRODUCTION_CHANGE_MANAGEMENT_GUIDE.md` 与人工清单 `PRODUCTION_CHANGE_HUMAN_CHECKLIST.md`。本节只给部署方最关键的结论。

### 17.1 它做什么、不做什么

- **做**：构建生产变更管控平面——变更请求 / 计划 / 窗口 / 预检 / 检查点 / 中止策略 / 回滚引用 / 后验证 / 证据 / 模拟 / 失败场景 / 受控包装配，全部只读装配 + 真实 USER 登记。提供后端 API（27 路由：13 GET 只读 + 13 POST 真实 USER 登记 + `/signoff` + `/decision`）与前端只读看板 `/governance-change`。
- **不做**：**不执行**变更；**不部署**；**不迁移**；**不回滚**；**不激活** `engineering_enabled`（保持 `false`）；**不宣布 GO / APPROVED**；**不自动**执行（执行模式无 `AI_AUTOMATIC`；状态机无 `AUTO_*` 态）；**不替代**四角色或主理人的人工责任；**不提供**任何 `/execute` / `/deploy` / `/rollback` / `/apply` / `/migrate` / `/activate` 端点（红线①–⑩）。

### 17.2 关键 fail-closed 不变量

- 终端态恒为 `PHASE_3_9_7_PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO`（模块常量，不可被运行时改写）。
- `ProductionChangeControlService` 继承 `_RedLineForbiddenMixin`，结构级禁名拦截 `execute_change` / `deploy_production` / `rollback_production` / `apply_change` / `migrate_production` / `auto_execute_change` / `declare_change_go` 等（getattr 即抛 `EnterpriseRedLineViolationError`）。
- `ChangeExecutionMode` 不含 `AI_AUTOMATIC`；`ChangeState` 只可能是 `HUMAN_DRAFTED` / `AWAITING_HUMAN_REVIEW` / `HUMAN_COMPLETED` / `HUMAN_ABORTED`，**永不 `AUTO_*` / `AI_APPROVED`**。
- `run_controlled_change_simulation()` 仅静态推演，`is_simulation` 恒 True；`ControlledChangePackage.simulated_only` 恒 True——**绝不真实变更**。
- 审计真实 +13 类（`CHANGE_*`），基线 108 → 121，与 `.ai/baselines/audit_action_category_ledger.json` `total=121` 一致。
- `PRODUCTION_CHANGE_FORBIDDEN_COUNT = 388`（结构级禁名）。

### 17.3 人工动作入口（唯一合法出口）

- 只读看板：`GET /governance/change/readiness | contract | plan | window | preflight | checkpoint | abort-policy | rollback-reference | post-verification | evidence | simulation | failure-scenarios | package | decision-ledger`。
- 真实人工登记（须 `governance:release:signoff`，仅 admin；强制 `actor_kind="user"`）：`POST /governance/change/signoff`、`POST /governance/change/decision`。
- **真变更执行**是用户在**人类终端**手工执行的唯一动作；主理人在人类终端显式置 `engineering_enabled=true`（见 `PRODUCTION_CHANGE_HUMAN_CHECKLIST.md`），AI 不代执行。

### 17.4 收口状态

本层状态 **PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO**：生产变更管控平面已建成并通过红线验证，但**无真实生产变更执行**。详见 `.ai/reviews/phase3.9.7_production_change_control_report.md` 与 `.ai/roadmap_v8.md` §35.12。

---

## 附录 A：变更记录

| 版本 | 变更 |
|---|---|
| Phase 3.8.29 | 首次发布。HttpOnly Cookie + CSRF 双提交、OIDC/SSO 适配器、环境隔离红线、append-only 安全审计、CI 生产门禁、本部署指南 |
| Phase 3.9.2 | 新增 §13 生产发布闸门与证据包层：13 项 CHECK_KEYS、SHA-256 证据清单、4 角色人工签署（GO/NO-GO/NEED_MORE_EVIDENCE，仅 `USER`）、4 个 RELEASE_* 审计类（总数 83）、314 项 fail-closed 禁名、只读 API + 签署端点、前端 `/governance-release` 页（无自动上线 / 无 AI 批准按钮） |
| Phase 3.9.3 | 新增 §14 生产可观测性、SRE 与事故响应准备层：11 组件健康模型（UNKNOWN 不回退 HEALTHY）、SLI/SLO（未验证 PENDING_VERIFICATION）、错误预算只计算、告警去重关联、SEV0–3 事故模型（8 态无 AUTO_*）、append-only 时间线、Runbook 只引用、发布/安全信号关联（auto_rollback=false / threshold_verified=false）、337 项 fail-closed 禁名、只读 API + 人工 ACK/RESOLVE/CLOSE 端点（auto_state_transition=false）、前端 `/governance-observability` 页（无 Auto Fix/Rollback/Resolve/Close/AI Approve）、7 个 OBSERVABILITY_* 审计类（总数 90） |
| Phase 3.9.7-change | 新增 §17 生产变更管控层：19 模块只读装配 + 真实 USER 登记（production_change/），执行模式无 AI_AUTOMATIC、状态机无 AUTO_* 态、受控变更包 simulated_only 恒 True、模拟只静态推演；388 项 fail-closed 禁名（_RedLineForbiddenMixin 结构级拦截）；27 路由（13 GET 只读 + 13 POST USER 登记 + /signoff + /decision，无 /execute /deploy /rollback /apply /migrate /activate）；前端 `/governance-change` 只读看板（无 Deploy/Execute/Rollback Now）；13 个 CHANGE_* 审计类（总数 121）；门禁脚本 check_production_change_control_gate.py + 人工清单 PRODUCTION_CHANGE_HUMAN_CHECKLIST.md |
| Phase 3.9.4 | 新增 §15 生产遥测接入适配与合成运维验证层：`TelemetryProvider` 端口（ABC + 5 抽象方法）+ Synthetic/Prometheus/OTel 适配器（未配置真实源→空/`NOT_CONFIGURED`，绝不降级伪装 Synthetic）、`TelemetryNormalizer` 复用 production_observability 模型、`TelemetryAggregator`（仅合成源→`synthetic_only` 不判 operational）、`TelemetryProviderRegistry`（真实源不 fallback）、`TelemetryAlertRouter`（合成源仅 `SIMULATED_DELIVERY`，禁真实外发）、SyntheticFaultScenario 合成演练（incident 恒 open、`auto_*=false`）、102 项 fail-closed 禁名、只读 API `governance_telemetry.py`（9 路由，生产环境合成演练 403，USER 强制）+ 前端 SYNTHETIC/PRODUCTION 徽章与演练 UI、4 个 TELEMETRY_* 审计类（总数 100）、CI `telemetry-quality-gate.yml`（4 job） |
