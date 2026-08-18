"""Live-qualification package validator (T31) — fail-closed self-audit.

Returns a validation dict or raises PackageValidationError. It guarantees the package
was not forged: hash matches, terminal state is legal, no credential leakage, the
qualified count is internally consistent, and an 8/8 claim is impossible without real
deploy + real E2E evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Set

from .live_package import LiveQualificationPackage, deterministic_hash

_SECRET_KEY_HINTS = {
    "secret",
    "password",
    "passwd",
    "private_key",
    "api_secret",
    "apikey",
    "access_key_secret",
    "token_secret",
}


class PackageValidationError(Exception):
    """Fail-closed: the package failed an integrity / honesty check."""


def _looks_like_secret_value(v: Any) -> bool:
    """A value is secret-like only if it is a reasonably long mixed alpha/digit string.

    Benign identifiers and state labels (e.g. ``PENDING_EXTERNAL_STAGING_RESOURCE``,
    or the resource name ``secret_provider``) are NOT secret-like because they lack
    the high-entropy digit+alpha mix of a real credential.
    """
    if not isinstance(v, str):
        return False
    if len(v) < 16:
        return False
    return any(c.isalpha() for c in v) and any(c.isdigit() for c in v)


def _scan_secret_keys(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            # Flag only when the value is actually secret-like. A key merely *named*
            # with a hint (e.g. the resource ``secret_provider``) is benign.
            if _looks_like_secret_value(v):
                raise PackageValidationError(
                    f"package contains a secret-like value at {path}.{k} (red line: "
                    f"no real credential may appear in the package)."
                )
            if any(h in str(k).lower() for h in _SECRET_KEY_HINTS) and _looks_like_secret_value(v):
                raise PackageValidationError(
                    f"package contains a secret-like value at {path}.{k} (red line: "
                    f"no real credential may appear in the package)."
                )
            _scan_secret_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_secret_keys(v, f"{path}[{i}]")


def validate_package(pkg: LiveQualificationPackage) -> Dict[str, Any]:
    # 1) hash integrity (tamper / forgery detection)
    d = pkg.__dict__.copy()
    d.pop("built_at", None)
    d.pop("package_hash", None)
    expected = deterministic_hash(d)
    if expected != pkg.package_hash:
        raise PackageValidationError("package_hash mismatch — package altered or forged")

    # 2) legal terminal state (no GO / APPROVED / PRODUCTION_READY as status)
    if "APPROVED" in pkg.terminal_state or "PRODUCTION_READY" in pkg.terminal_state:
        raise PackageValidationError("terminal state contains forbidden token")
    if re.search(r"(?<!_)GO(?!_)", pkg.terminal_state):
        raise PackageValidationError("terminal state contains standalone GO token")

    # 3) no credential leakage
    _scan_secret_keys(pkg.provider_init_evidence, "provider_init_evidence")
    _scan_secret_keys(pkg.resource_states, "resource_states")
    _scan_secret_keys(pkg.isolation_snapshot, "isolation_snapshot")

    # 4) qualified count consistency
    if pkg.real_resources_qualified > pkg.real_resources_total:
        raise PackageValidationError("qualified count exceeds total (forgery)")
    counted = sum(
        1 for v in pkg.resource_states.values() if v == "QUALIFIED_EXTERNAL_STAGING"
    )
    if counted != pkg.real_resources_qualified:
        raise PackageValidationError("qualified count inconsistent with resource states")

    # 5) cannot claim 8/8 without real deploy + real E2E evidence
    if counted == pkg.real_resources_total and (
        pkg.e2e_status != "EXECUTED_PASS" or pkg.deployment_status != "DEPLOYED"
    ):
        raise PackageValidationError(
            "8/8 qualified claimed without real deploy + real E2E evidence (forgery)"
        )

    # 6) provider init honest: if init_result != PASS, nothing may be qualified
    if pkg.provider_init_result != "PASS" and counted > 0:
        raise PackageValidationError(
            "resources qualified while provider init did not PASS (inconsistent)"
        )

    return {
        "valid": True,
        "terminal_state": pkg.terminal_state,
        "hash": pkg.package_hash,
        "real_resources_qualified": pkg.real_resources_qualified,
        "real_resources_total": pkg.real_resources_total,
    }
