"""BOIP Phase 3.9.15 — External Staging Real Resource Onboarding & Live Qualification.

Canonical constants, terminal state, and registries for the
8-Resource Live State Machine, 9 Isolation dimensions, and 13 Runtime Live checks.

Design principle — **fail-closed & honest**:
  * Nothing is "qualified" until real human input + dual-key authorization +
    real connectivity evidence exist.
  * This module NEVER performs, and NEVER pretends to perform, any real
    provisioning, credential injection, or production action.
"""
from __future__ import annotations

from enum import Enum


PHASE = "3.9.15"
PHASE_NAME = "External Staging Real Resource Onboarding & Live Qualification"

# Terminal state for this phase. Governance rule: MUST NOT contain
# GO / APPROVED / PRODUCTION_READY.
LIVE_TERMINAL_STATE = (
    "PHASE_3_9_15_EXTERNAL_STAGING_REAL_RESOURCE_LIVE_QUALIFICATION_BUILT_NO_GO"
)
BUILT_NO_GO = "BUILT_NO_GO"

# The 8 External Staging resources onboarded in this phase.
class ExternalStagingResource(str, Enum):
    DATABASE = "database"
    SECRET_PROVIDER = "secret_provider"
    IDP = "identity_provider"
    OBJECT_STORAGE = "object_storage"
    TELEMETRY = "telemetry"
    ALERT_SANDBOX = "alert_sandbox"
    DOMAIN_TLS = "domain_tls"
    DEPLOYMENT_TARGET = "deployment_target"


ALL_RESOURCES = tuple(ExternalStagingResource)


# 8-Resource Live State Machine:
#   15 happy-path states  +  4 failure states  =  19 total.
# No skipping; no backward-to-success jump. Terminal success = QUALIFIED.
class ResourceLiveState(str, Enum):
    # --- happy path (15) ---
    PENDING_EXTERNAL_STAGING_RESOURCE = "PENDING_EXTERNAL_STAGING_RESOURCE"
    ACQUISITION_LOCKED = "ACQUISITION_LOCKED"
    CREDENTIAL_CACHED = "CREDENTIAL_CACHED"
    ACCOUNT_VERIFIED = "ACCOUNT_VERIFIED"
    HUMAN_INPUT_INTAKE = "HUMAN_INPUT_INTAKE"
    HUMAN_AUTHORIZED = "HUMAN_AUTHORIZED"
    PROVIDER_INIT = "PROVIDER_INIT"
    PROVIDER_VALIDATE = "PROVIDER_VALIDATE"
    PROVIDER_PLAN = "PROVIDER_PLAN"
    CONNECTIVITY_CHECKING = "CONNECTIVITY_CHECKING"
    CONNECTIVITY_VERIFIED = "CONNECTIVITY_VERIFIED"
    ISOLATION_CHECKING = "ISOLATION_CHECKING"
    REGISTRATION = "REGISTRATION"
    RUNTIME_DEPLOY = "RUNTIME_DEPLOY"
    QUALIFIED_EXTERNAL_STAGING = "QUALIFIED_EXTERNAL_STAGING"
    # --- failure (4) ---
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    ROLLED_BACK = "ROLLED_BACK"


FAILURE_STATES = {
    ResourceLiveState.FAILED,
    ResourceLiveState.BLOCKED,
    ResourceLiveState.ROLLBACK_REQUIRED,
    ResourceLiveState.ROLLED_BACK,
}

TERMINAL_SUCCESS = ResourceLiveState.QUALIFIED_EXTERNAL_STAGING

# Allowed forward transitions. Fail-closed: any jump not listed here is illegal.
ALLOWED_TRANSITIONS: dict[ResourceLiveState, set[ResourceLiveState]] = {
    ResourceLiveState.PENDING_EXTERNAL_STAGING_RESOURCE: {
        ResourceLiveState.ACQUISITION_LOCKED, ResourceLiveState.BLOCKED,
    },
    ResourceLiveState.ACQUISITION_LOCKED: {
        ResourceLiveState.CREDENTIAL_CACHED, ResourceLiveState.BLOCKED,
    },
    ResourceLiveState.CREDENTIAL_CACHED: {
        ResourceLiveState.ACCOUNT_VERIFIED, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.ACCOUNT_VERIFIED: {
        ResourceLiveState.HUMAN_INPUT_INTAKE, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.HUMAN_INPUT_INTAKE: {
        ResourceLiveState.HUMAN_AUTHORIZED, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.HUMAN_AUTHORIZED: {
        ResourceLiveState.PROVIDER_INIT, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.PROVIDER_INIT: {
        ResourceLiveState.PROVIDER_VALIDATE, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.PROVIDER_VALIDATE: {
        ResourceLiveState.PROVIDER_PLAN, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.PROVIDER_PLAN: {
        ResourceLiveState.CONNECTIVITY_CHECKING, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.CONNECTIVITY_CHECKING: {
        ResourceLiveState.CONNECTIVITY_VERIFIED, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.CONNECTIVITY_VERIFIED: {
        ResourceLiveState.ISOLATION_CHECKING, ResourceLiveState.BLOCKED, ResourceLiveState.FAILED,
    },
    ResourceLiveState.ISOLATION_CHECKING: {
        ResourceLiveState.REGISTRATION, ResourceLiveState.BLOCKED,
        ResourceLiveState.FAILED, ResourceLiveState.ROLLBACK_REQUIRED,
    },
    ResourceLiveState.REGISTRATION: {
        ResourceLiveState.RUNTIME_DEPLOY, ResourceLiveState.BLOCKED,
        ResourceLiveState.FAILED, ResourceLiveState.ROLLBACK_REQUIRED,
    },
    ResourceLiveState.RUNTIME_DEPLOY: {
        ResourceLiveState.QUALIFIED_EXTERNAL_STAGING, ResourceLiveState.BLOCKED,
        ResourceLiveState.FAILED, ResourceLiveState.ROLLBACK_REQUIRED,
    },
    ResourceLiveState.QUALIFIED_EXTERNAL_STAGING: set(),  # terminal success
    # failure states
    ResourceLiveState.FAILED: {ResourceLiveState.ROLLED_BACK, ResourceLiveState.BLOCKED},
    ResourceLiveState.BLOCKED: {ResourceLiveState.ROLLED_BACK, ResourceLiveState.FAILED},
    ResourceLiveState.ROLLBACK_REQUIRED: {ResourceLiveState.ROLLED_BACK},
    ResourceLiveState.ROLLED_BACK: set(),
}


# 9 Isolation dimensions — each verified independently, all must pass.
class IsolationDimension(str, Enum):
    NETWORK_SEGMENT = "network_segment"
    IAM_SCOPE = "iam_scope"
    SECRET_SCOPE = "secret_scope"
    DATA_RESIDENCY = "data_residency"
    RUNTIME_NAMESPACE = "runtime_namespace"
    TRAFFIC_EGRESS = "traffic_egress"
    AUDIT_BOUNDARY = "audit_boundary"
    COST_BUDGET = "cost_budget"
    ACCESS_TENANCY = "access_tenancy"


ALL_ISOLATION_DIMENSIONS = tuple(IsolationDimension)


# 13 Runtime Live checks — each must pass for live qualification.
class RuntimeLiveCheck(str, Enum):
    API_HEALTH = "api_health"
    DB_CONNECTIVITY = "db_connectivity"
    SECRET_RESOLUTION = "secret_resolution"
    IDP_HANDSHAKE = "idp_handshake"
    OBJECT_STORE_RW = "object_store_rw"
    TELEMETRY_EMIT = "telemetry_emit"
    ALERT_ROUTE = "alert_route"
    TLS_TERMINATION = "tls_termination"
    DEPLOY_TARGET_READY = "deploy_target_ready"
    AUTOHEAL = "autoheal"
    OBSERVABILITY = "observability"
    CONFIG_DRIFT = "config_drift"
    GATEWAY_ROUTING = "gateway_routing"


ALL_RUNTIME_LIVE_CHECKS = tuple(RuntimeLiveCheck)
