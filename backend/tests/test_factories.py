"""Tests for the shared relational test-data factories."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.project import Project
from app.db.models.tenant import Tenant
from app.db.models.user import User
from tests.factories import create_project, create_tenant, create_user


def test_factories_create_related_models(db_session: Session) -> None:
    """Factories must persist a valid tenant/user/project ownership chain."""

    tenant: Tenant = create_tenant(db_session, slug="factory-tenant")
    user: User = create_user(
        db_session,
        tenant=tenant,
        email="factory-user@boip.local",
        role="designer",
    )
    project: Project = create_project(db_session, tenant=tenant, owner=user)

    assert db_session.get(Tenant, tenant.id) is tenant
    assert db_session.get(User, user.id) is user
    assert db_session.get(Project, project.id) is project
    assert user.tenant_id == tenant.id
    assert project.tenant_id == tenant.id
    assert project.owner_id == user.id
    assert project.floor is None
    assert project.input_payload["source"] == "pending_verification"


def test_factories_generate_independent_defaults(db_session: Session) -> None:
    """Default values must remain unique and create all required relations."""

    first_project: Project = create_project(db_session)
    second_project: Project = create_project(db_session)

    assert first_project.id != second_project.id
    assert first_project.tenant_id != second_project.tenant_id
    assert first_project.owner_id != second_project.owner_id
