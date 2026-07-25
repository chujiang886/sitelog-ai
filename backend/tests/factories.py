"""Typed test-data factories for the Phase 0/1 relational models."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.tenant import Tenant
from app.db.models.user import User


def create_tenant(
    db_session: Session,
    *,
    name: str = "Test Tenant",
    slug: str | None = None,
) -> Tenant:
    """Create and flush a tenant with a collision-resistant default slug."""

    resolved_slug: str = slug or f"test-tenant-{uuid4().hex}"
    tenant = Tenant(name=name, slug=resolved_slug, status="active")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def create_user(
    db_session: Session,
    *,
    tenant: Tenant | None = None,
    email: str | None = None,
    role: str = "customer",
) -> User:
    """Create and flush a user, creating its tenant when omitted."""

    resolved_tenant: Tenant = tenant or create_tenant(db_session)
    resolved_email: str = email or f"test-{uuid4().hex}@boip.local"
    user = User(
        tenant_id=resolved_tenant.id,
        email=resolved_email,
        hashed_password="phase0-test-password-not-for-production",
        role=role,
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_project(
    db_session: Session,
    *,
    tenant: Tenant | None = None,
    owner: User | None = None,
    address: str = "pending_verification",
) -> Project:
    """Create and flush a project without inventing domain measurements."""

    resolved_tenant: Tenant = tenant or create_tenant(db_session)
    resolved_owner: User = owner or create_user(db_session, tenant=resolved_tenant)
    project = Project(
        tenant_id=resolved_tenant.id,
        owner_id=resolved_owner.id,
        address=address,
        floor=None,
        orientation="",
        status="pending",
        state="Draft",
        input_payload={"source": "pending_verification"},
        output_payload={},
        evidence_payload={},
    )
    db_session.add(project)
    db_session.flush()
    return project


def create_conversation(
    db_session: Session,
    *,
    tenant: Tenant | None = None,
    user: User | None = None,
    project: Project | None = None,
    title: str = "Test Conversation",
) -> Conversation:
    """Create and flush a Conversation for Phase 1 / T06b tests."""

    resolved_tenant: Tenant = tenant or create_tenant(db_session)
    resolved_user: User = user or create_user(db_session, tenant=resolved_tenant)
    conversation = Conversation(
        tenant_id=resolved_tenant.id,
        user_id=resolved_user.id,
        project_id=project.id if project is not None else None,
        title=title,
        status="Active",
        state="Active",
    )
    db_session.add(conversation)
    db_session.flush()
    return conversation


def create_message(
    db_session: Session,
    *,
    conversation: Conversation | None = None,
    role: str = "user",
    content: str = "pending_verification",
    intent: dict | None = None,
    evidence: dict | None = None,
) -> Message:
    """Create and flush a Message belonging to a Conversation."""

    resolved_conversation: Conversation = conversation or create_conversation(db_session)
    message = Message(
        tenant_id=resolved_conversation.tenant_id,
        conversation_id=resolved_conversation.id,
        role=role,
        content=content,
        intent=intent or {},
        evidence=evidence or {},
    )
    db_session.add(message)
    db_session.flush()
    return message