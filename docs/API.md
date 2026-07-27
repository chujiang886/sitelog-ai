# BOIP API

> **更新至 Phase 2.2（2026-07-28 收敛）**。当前共 11 个 router；`/api/uploads`、`/api/analysis/run`、`/api/report/generate` 已接 RBAC 鉴权（见下方「认证与权限」），其余端点保持匿名开放（渐进保护策略）。

所有接口返回统一信封：

```json
{ "success": true, "data": {} }
```

错误信封：

```json
{ "success": false, "error": { "code": "HTTP_404", "message": "Not Found" } }
```

> 历史说明：Phase 0 骨架期不访问数据库。当前（Phase 2.2）后端已真实访问数据库（AsyncSession）、对象存储（StorageBackend 抽象）与向量库（InMemory/Qdrant 抽象）。未经专家验证的工程数值一律 `pending_verification`。

## 路由

### GET `/health`

后端存活检查。

```json
{
  "success": true,
  "data": { "status": "ok", "service": "backend", "ts": "2025-01-01T00:00:00+00:00" }
}
```

### GET `/api/projects`

返回空项目分页。

```json
{ "success": true, "data": { "items": [], "total": 0 } }
```

### GET `/api/agents`

返回 Agent 注册表。

```json
{ "success": true, "data": { "agents": ["core", "environment", "vision", "design"] } }
```

### GET `/api/knowledge/rules`

返回空知识规则分页。

```json
{ "success": true, "data": { "items": [], "total": 0 } }
```

### 错误处理

未知路由返回 HTTP 404 和 `HTTP_404` 错误码；参数校验失败返回 HTTP 422 和 `VALIDATION_ERROR`。内部错误统一返回 HTTP 500 和 `INTERNAL_ERROR`，不暴露堆栈信息。

---

## 分析与报告（Phase 2）

Phase 2 在统一信封之上新增分析与报告生成路由，由 `AgentRegistry` 中的真实三 Agent 链驱动（详见 `docs/AGENTS.md` §8）。所有业务字段仍为 `pending_verification`。

### POST `/api/analysis/run`

触发分析编排：串联 Environment → Vision → Design Agent，返回结构化分析报告信封。

请求体：

```json
{
  "project_id": "<uuid>",
  "payload": { "intent": "consult", "image_refs": ["<image_id>"] }
}
```

成功响应：

```json
{
  "success": true,
  "data": {
    "project_id": "<uuid>",
    "environment": { "...": "pending_verification" },
    "vision": { "...": "pending_verification" },
    "design": { "...": "pending_verification" },
    "evidence": [{ "agent": "vision", "...": "..." }]
  }
}
```

### POST `/api/report/generate`

将分析结果渲染为交付物（PDF / Markdown），由 `ReportGenerator` 生成。

请求体：

```json
{ "project_id": "<uuid>", "analysis": { "...": "..." }, "format": "pdf" }
```

成功响应：

```json
{ "success": true, "data": { "report_id": "<uuid>", "url": "/reports/<uuid>.pdf" } }
```

> 注：上述字段为契约骨架，`environment/vision/design` 等具体结构以真实 Agent 输出为准。

---

## 认证与权限（Phase 2.2.6 RBAC）

三角色：`admin` / `designer` / `viewer`；权限命名 `resource:action`（如 `upload:create`、`analysis:create`、`report:create`）。权限在登录时嵌入 JWT，服务端无需每请求查库。

### POST `/api/auth/login`

请求体：

```json
{ "email": "user@example.com", "password": "***" }
```

成功响应（`data`）：

```json
{
  "access_token": "<JWT HS256>",
  "token_type": "bearer",
  "user": { "id": "<uuid>", "tenant_id": "<uuid>", "email": "...", "roles": ["admin"], "permissions": ["upload:create", "..."] }
}
```

失败统一返回 401 `Invalid email or password`（防用户枚举）。

### GET `/api/auth/me`

携带 `Authorization: Bearer <token>` 返回当前用户主体（id / tenant_id / roles / permissions）。

### 受保护端点

| 端点 | 所需权限 |
|---|---|
| `POST /api/uploads` | `upload:create` |
| `GET /api/uploads/{image_id}` | `upload:read` |
| `POST /api/analysis/run` | `analysis:create` |
| `POST /api/report/generate` | `report:create` |

- 未携带 / 无效 / 过期 token → **401**；权限不足 → **403**（`Permission denied: requires 'xxx'`）。错误信封格式统一。
- **tenant 隔离**：`tenant_id` 由 JWT 服务端签发（已弃用 `X-Tenant-Id` 请求头），跨租户读取返回 404。

---

## RAG 基础设施（Phase 2.2.5）

### POST `/api/rag/ingest`

知识入库。强制三要素溯源：`source` / `created_at` / `raw_ref` 缺失即拒（`IngestionError`）。

### POST `/api/rag/search`

向量检索（默认 InMemory 向量库；Qdrant 经环境变量启用，懒加载不进 CI）。

### GET `/api/rag/mode`

返回当前 embedding provider 与向量库模式（默认 `mock` + `memory`）。

---

## 其余端点（匿名开放）

`/api/conversations`（+`/{id}/messages`）、`POST /api/vision/analyze`、`GET /api/agents`（+`/{name}/invoke`）、`/api/projects`、`/api/knowledge/rules` —— Phase 3 按渐进策略逐步纳入保护。

## OpenAPI

FastAPI 自动提供 `/docs`（Swagger UI）和 `/redoc`（ReDoc）。
