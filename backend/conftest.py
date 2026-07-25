"""Shared pytest fixtures for BOIP backend, Agent, and API tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agents.loader import AgentLoader
from agents.registry import AgentRegistry
from app.db.base import Base
from app.db import models as _models  # noqa: F401  # Register ORM metadata.
from app.main import app


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Provide an isolated in-memory database session with the full schema."""

    test_engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture()
def agent_registry() -> Iterator[AgentRegistry]:
    """Load the Phase 0 Agents into a clean singleton registry."""

    registry: AgentRegistry = AgentRegistry()
    registry.reset()
    AgentLoader(registry=registry).load_all()
    try:
        yield registry
    finally:
        registry.reset()


@pytest.fixture()
def client(agent_registry: AgentRegistry) -> Iterator[TestClient]:
    """Provide a FastAPI test client with the Agent registry initialized."""

    del agent_registry  # The fixture dependency guarantees registry initialization.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_token() -> str:
    """Return a non-secret bearer token reserved for test dependency overrides."""

    return "Bearer phase0-test-token"
