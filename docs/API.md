# BOIP API（Phase 0 / T02）

所有接口返回统一信封：

```json
{ "success": true, "data": {} }
```

错误信封：

```json
{ "success": false, "error": { "code": "HTTP_404", "message": "Not Found" } }
```

> Phase 0 只提供骨架响应，不访问数据库、缓存、向量库或对象存储。工程数值均为 `pending_verification`（本阶段没有业务阈值）。

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

## OpenAPI

FastAPI 自动提供 `/docs`（Swagger UI）和 `/redoc`（ReDoc）。
