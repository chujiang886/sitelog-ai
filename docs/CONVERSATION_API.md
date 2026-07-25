# BOIP 对话 API（Phase 1 / T06b / T06c）

本文件定义 `app/api/conversations.py` 暴露的 4 条路由、信封格式、错误码与典型调用示例。
所有路由统一返回 `{success, data}` 或 `{success, false, error}` 信封（16 第七章）。

---

## 1. 通用约定

### 1.1 请求头
| 头 | 必填 | 说明 |
|---|---|---|
| `X-Tenant-Id` | ✅ | UUID，租户隔离；缺失/非法 → 400 |
| `X-User-Id` | ✅（POST） | UUID，调用方身份；缺失/非法 → 400 |
| `Content-Type` | POST 时必填 | `application/json` |

### 1.2 信封
```json
// success
{ "success": true,  "data": { ... } }

// failure
{ "success": false, "error": { "code": "NOT_FOUND", "message": "..." } }
```

---

## 2. 路由

### 2.1 `POST /api/conversations` — 创建会话

请求体：
```json
{ "project_id": "<uuid|null>", "title": "BOIP 咨询会话" }
```

返回 `data`：
```json
{
  "id": "<conv-uuid>", "tenant_id": "...", "user_id": "...",
  "project_id": null, "title": "...", "status": "Active", "state": "Active",
  "created_at": "...", "updated_at": "..."
}
```

### 2.2 `GET /api/conversations/{id}` — 获取会话 + 全部消息

`data`：
```json
{
  "conversation": { /* 同上 */ },
  "messages": [
    {
      "id": "...", "conversation_id": "...", "tenant_id": "...",
      "role": "user|assistant|system", "content": "...",
      "intent": { /* NLU 结果 */ }, "evidence": { /* agent steps */ },
      "created_at": "..."
    }
  ]
}
```

### 2.3 `POST /api/conversations/{id}/messages` — 追加消息 + 触发 chat

请求体：`{"role": "user|assistant|system", "content": "..."}`

返回 `data`：
```json
{
  "message_id": "<assistant-message-uuid>",
  "user_message_id": "<user-message-uuid>",
  "intent": { "intent": "consult", "confidence": 0.0, "method": "rule", "rationale": "..." },
  "agent_steps": [
    { "name": "environment", "status": "pending_verification", "pending_verification": true, "notes": [...] }
  ],
  "placeholder_reply": "Phase 1 placeholder: intent=consult,method=rule,confidence=0.40",
  "pending_verification": true
}
```

副作用：同时持久化 `user` + `assistant` 两条 `messages` 记录；assistant 行携带 `intent` + `evidence`。

### 2.4 `GET /api/conversations/{id}/messages` — 分页消息

Query：`page` (默认 1) / `page_size` (默认 50, ≤200)

`data`：
```json
{
  "items": [ /* message 对象数组 */ ],
  "total": 6,
  "page": 1,
  "page_size": 50
}
```

---

## 3. 错误码

| HTTP | error.code | 触发场景 |
|---|---|---|
| 400 | `INVALID_TENANT_HEADER` | `X-Tenant-Id` 缺失或非法 UUID |
| 400 | `INVALID_USER_HEADER` | `X-User-Id` 缺失或非法 UUID |
| 400 | `INVALID_PROJECT_ID` | `project_id` 非法 UUID |
| 400 | `INVALID_CONVERSATION_ID` | 路径 UUID 非法 |
| 400 | `UNSUPPORTED_ROLE` | `role` 不在 user/assistant/system |
| 404 | `NOT_FOUND` | 会话不存在或跨租户访问 |
| 404 | `PROJECT_NOT_FOUND` | 创建会话时 `project_id` 不存在 |
| 500 | `CHAT_RUNTIME_ERROR` | Core Agent chat 编排失败（已降级为 placeholder） |

---

## 4. 前端调用

```ts
import {
  createConversation, getConversation, appendMessage, listMessages,
} from "@/lib/chat";

await createConversation({ tenantId, userId }, { title: "..." });
await appendMessage({ tenantId, userId }, convId, { role: "user", content: "..." });
```

详见 `frontend/src/lib/chat.ts` 与 `frontend/src/app/consult/page.tsx`。

---

## 5. 已知边界

- Phase 1.0 默认 `llm.enabled=false`：所有回复均为占位 + `pending_verification=true`。
- 任何 chat 编排异常都会被捕获并降级为 `{intent: unknown, ...}`，前端不会因此 500。
- `evidence.pending_verification` 字段由后端强制计算：true 表示本次回复**未经过真实 LLM**。