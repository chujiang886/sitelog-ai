"""Phase 1 / T06b 会话 (conversation) 路由。

提供 4 个端点，统一返回 ``{success, data}`` 或 ``{success, false, error}`` 信封：

- ``POST /api/conversations`` 创建会话
- ``GET  /api/conversations/{id}`` 读取会话 + 全量消息
- ``POST /api/conversations/{id}/messages`` 追加消息并触发 Core Agent chat
- ``GET  /api/conversations/{id}/messages`` 分页查询消息

设计原则（16 第五章 + 16 第三章）：
- 最小正确实现：所有业务字段保持 pending_verification；
- 任何 LLM 接入失败、provider 缺失或 None 输入均降级到 placeholder，不让对话 API 崩溃；
- tenant 隔离：以请求头 ``X-Tenant-Id`` 标识租户，未传则强制返回 400。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.exceptions import NotFoundError  # noqa: E402
from app.db.models.conversation import Conversation  # noqa: E402
from app.db.models.message import Message  # noqa: E402
from app.db.models.project import Project  # noqa: E402
from app.db.session import get_db  # noqa: E402

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# --------------------------------------------------------------------------- #
# 内部 helper                                                                  #
# --------------------------------------------------------------------------- #


def _resolve_tenant_id(x_tenant_id: str | None) -> uuid.UUID:
    """解析租户 ID：要求 ``X-Tenant-Id`` 头存在且为合法 UUID。"""

    if not x_tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Tenant-Id header",
        )
    try:
        return uuid.UUID(x_tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid X-Tenant-Id header: {x_tenant_id}",
        ) from exc


def _resolve_user_id(x_user_id: str | None) -> uuid.UUID:
    """解析用户 ID：要求 ``X-User-Id`` 头存在且为合法 UUID。"""

    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-User-Id header",
        )
    try:
        return uuid.UUID(x_user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid X-User-Id header: {x_user_id}",
        ) from exc


def _conversation_to_dict(conv: Conversation) -> dict[str, object]:
    """将会话对象序列化为前端友好的 dict。"""

    return {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "user_id": str(conv.user_id),
        "project_id": str(conv.project_id) if conv.project_id else None,
        "title": conv.title,
        "status": conv.status,
        "state": conv.state,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def _message_to_dict(msg: Message) -> dict[str, object]:
    """将消息对象序列化为前端友好的 dict。"""

    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "tenant_id": str(msg.tenant_id),
        "role": msg.role,
        "content": msg.content,
        "intent": dict(msg.intent or {}),
        "evidence": dict(msg.evidence or {}),
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _require_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Conversation:
    """根据 tenant 隔离查找会话；找不到则抛 404。"""

    conv: Conversation | None = (
        db.query(Conversation)
        .filter_by(id=conversation_id, tenant_id=tenant_id)
        .one_or_none()
    )
    if conv is None:
        raise NotFoundError(f"Conversation not found: {conversation_id}")
    return conv


# --------------------------------------------------------------------------- #
# Pydantic 入参模型                                                              #
# --------------------------------------------------------------------------- #


class CreateConversationBody(BaseModel):
    """创建会话请求体。"""

    project_id: str | None = Field(
        default=None,
        description="可选项目 UUID；未传则创建未挂载项目的会话",
    )
    title: str | None = Field(default=None, max_length=255)


class AppendMessageBody(BaseModel):
    """追加消息并触发 chat 编排的请求体。"""

    role: str = Field(default="user", min_length=1, max_length=16)
    content: str = Field(default="", description="消息正文")


# --------------------------------------------------------------------------- #
# 路由                                                                          #
# --------------------------------------------------------------------------- #


@router.post("")
async def create_conversation(
    body: CreateConversationBody,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, object]:
    """创建一条新的会话记录。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    user_id: uuid.UUID = _resolve_user_id(x_user_id)

    project_id: uuid.UUID | None = None
    if body.project_id:
        try:
            project_id = uuid.UUID(body.project_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid project_id: {body.project_id}",
            ) from exc
        project: Project | None = (
            db.query(Project)
            .filter_by(id=project_id, tenant_id=tenant_id)
            .one_or_none()
        )
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}",
            )

    conv: Conversation = Conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        project_id=project_id,
        title=body.title or "未命名会话",
        status="Active",
        state="Active",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return {
        "success": True,
        "data": _conversation_to_dict(conv),
    }


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, object]:
    """获取单个会话 + 其全部消息（按 created_at 升序）。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    try:
        conv_uuid: uuid.UUID = uuid.UUID(conversation_id)
    except (TypeError, ValueError):
        raise NotFoundError(f"Conversation not found: {conversation_id}")

    conv: Conversation = _require_conversation(db, conv_uuid, tenant_id)
    messages: list[Message] = (
        db.query(Message)
        .filter_by(conversation_id=conv.id, tenant_id=tenant_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    return {
        "success": True,
        "data": {
            "conversation": _conversation_to_dict(conv),
            "messages": [_message_to_dict(m) for m in messages],
        },
    }


@router.post("/{conversation_id}/messages")
async def append_message(
    conversation_id: str,
    body: AppendMessageBody,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, object]:
    """追加一条用户消息，并触发 Core Agent chat 编排得到 assistant 回应。

    编排结果落到新 ``assistant`` 消息的 ``intent`` / ``evidence`` 字段，
    保证后续前端从 ``GET /api/conversations/{id}`` 拉取完整对话。
    """

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    user_id: uuid.UUID = _resolve_user_id(x_user_id)
    try:
        conv_uuid: uuid.UUID = uuid.UUID(conversation_id)
    except (TypeError, ValueError):
        raise NotFoundError(f"Conversation not found: {conversation_id}")

    conv: Conversation = _require_conversation(db, conv_uuid, tenant_id)

    role: str = body.role.strip().lower() or "user"
    if role not in {"user", "assistant", "system"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported role: {body.role}",
        )

    # 1) 持久化用户消息（content 由调用方决定，可以为空字符串）
    user_msg: Message = Message(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        role=role,
        content=body.content,
        intent={},
        evidence={"source": "phase1_t06b_append_message"},
    )
    db.add(user_msg)
    db.flush()

    # 2) 加载最近 20 条历史作为编排器上下文（避免长会话爆栈）
    history_rows: list[Message] = (
        db.query(Message)
        .filter_by(conversation_id=conv.id, tenant_id=tenant_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(20)
        .all()
    )
    history_payload: list[dict[str, object]] = [
        {"role": m.role, "content": m.content} for m in reversed(history_rows)
    ]

    # 3) 调用 Core Agent chat 编排（容错：失败时使用占位结果）
    from agents.core.orchestrator import CoreOrchestrator

    orchestrator = CoreOrchestrator()
    chat_input: dict[str, object] = {
        "user_message": body.content,
        "history": history_payload,
        "request_id": str(user_msg.id),
    }
    chat_envelope: dict[str, object]
    pending_verification: bool = True
    try:
        chat_envelope = await orchestrator.chat(chat_input, history=history_payload)
    except Exception as exc:  # noqa: BLE001 - 兜底降级
        chat_envelope = {
            "success": False,
            "data": {
                "intent": {"intent": "unknown", "confidence": 0.0, "method": "rule"},
                "pipeline": [],
                "agent_steps": [],
                "history_len": len(history_payload),
                "pending_verification": True,
                "placeholder_reply": f"(chat 编排失败：{type(exc).__name__})",
            },
            "error": {"code": "CHAT_RUNTIME_ERROR", "message": str(exc)},
        }

    chat_data: dict[str, object] = chat_envelope.get("data", {}) or {}
    raw_intent: object = chat_data.get("intent", {})
    intent_payload: dict[str, object] = dict(raw_intent) if isinstance(raw_intent, dict) else {}

    # 4) 持久化 assistant 消息（占位回复 + 编排证据）
    assistant_msg: Message = Message(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        role="assistant",
        content=str(chat_data.get("placeholder_reply", "")),
        intent=intent_payload,
        evidence={
            "agent_steps": list(chat_data.get("agent_steps", []) or []),
            "pipeline": list(chat_data.get("pipeline", []) or []),
            "history_len": chat_data.get("history_len", len(history_payload)),
            "pending_verification": bool(chat_data.get("pending_verification", True)),
        },
    )
    db.add(assistant_msg)

    # 5) 把 user_id 同步给会话拥有者（首次发言时填入）
    if conv.user_id is None or conv.user_id == uuid.UUID(int=0):
        conv.user_id = user_id

    db.commit()
    db.refresh(assistant_msg)

    pending_verification = bool(
        (assistant_msg.evidence or {}).get("pending_verification", True)
    )

    return {
        "success": True,
        "data": {
            "message_id": str(assistant_msg.id),
            "user_message_id": str(user_msg.id),
            "intent": intent_payload,
            "agent_steps": list(chat_data.get("agent_steps", []) or []),
            "placeholder_reply": assistant_msg.content,
            "pending_verification": pending_verification,
        },
    }


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    """分页列出某会话下的消息（按 created_at 升序）。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    try:
        conv_uuid: uuid.UUID = uuid.UUID(conversation_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid conversation_id: {conversation_id}",
        ) from exc

    conv: Conversation = _require_conversation(db, conv_uuid, tenant_id)
    offset: int = (page - 1) * page_size

    query = (
        db.query(Message)
        .filter_by(conversation_id=conv.id, tenant_id=tenant_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    total: int = query.count()
    rows: list[Message] = query.offset(offset).limit(page_size).all()

    return {
        "success": True,
        "data": {
            "items": [_message_to_dict(m) for m in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }