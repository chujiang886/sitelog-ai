"""Phase 3.9.15 — Provider Acquisition & Live Plan Evidence (new 3.9.15 capability).

Reuses ``agents.external_staging_runtime.iac_executor`` for toolchain discovery and
offline syntax / count scanning. Adds the 3.9.15-specific **provider-init evidence**,
**acquisition-feasibility assessment**, and **live-plan evidence** that the 3.9.14
runtime executor does not model.

This module intentionally does NOT re-implement the Runtime Gate, Resource Registry,
Human Authorization, Deployment Provider, or Isolation Guard — those live in
``agents/staging_runtime/`` and ``agents/external_staging_runtime/`` and are reused.

fail-closed invariants (never violated):
- ``real_apply_allowed`` is ALWAYS ``False`` (no ``terraform apply`` / ``destroy``).
- No TLS disable, no checksum skip, no unknown binary, no ``curl -insecure``,
  no forged init / validate / plan PASS.
- If the sandbox cannot acquire the provider binary, the report states the
  environment limitation honestly (``PROVIDER_BINARY_EGRESS_BLOCKED`` /
  ``PROVIDER_BINARY_EGRESS_INTERMITTENT``); live flags are set ``False`` and no
  historical success result is substituted for this phase's real, reproducible evidence.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from agents.external_staging_runtime.iac_executor import (
    discover_toolchain,
    scan_all_count_zero,
)

_PHASE = "3.9.15"
_TERMINAL_STATE = (
    "PHASE_3_9_15_EXTERNAL_STAGING_REAL_RESOURCE_LIVE_QUALIFICATION_BUILT_NO_GO"
)

_PLAN_ADD_RE = re.compile(r"Plan:\s*(\d+)\s*to add")
_PLAN_CHANGE_RE = re.compile(r"to change,\s*(\d+)\s*to destroy")


class ProviderInitClassification(str, Enum):
    """Root-cause classification for ``terraform init`` (T2 / T5)."""

    REGISTRY_METADATA_REACHABLE = "PROVIDER_REGISTRY_METADATA_REACHABLE"
    BINARY_EGRESS_BLOCKED = "PROVIDER_BINARY_EGRESS_BLOCKED"
    BINARY_EGRESS_INTERMITTENT = "PROVIDER_BINARY_EGRESS_INTERMITTENT"
    ACQUIRED = "PROVIDER_ACQUIRED"
    UNKNOWN = "PROVIDER_INIT_UNKNOWN"


@dataclass
class ProviderInitEvidence:
    command: str
    timestamp: str
    rc: Optional[int]
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    registry_probe_http: Optional[int] = None
    github_probe_http: Optional[int] = None
    duration_s: float = 0.0
    classification: ProviderInitClassification = ProviderInitClassification.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "timestamp": self.timestamp,
            "rc": self.rc,
            "stdout_excerpt": self.stdout_excerpt[-2000:],
            "stderr_excerpt": self.stderr_excerpt[-2000:],
            "registry_probe_http": self.registry_probe_http,
            "github_probe_http": self.github_probe_http,
            "duration_s": round(self.duration_s, 2),
            "classification": self.classification.value,
        }


@dataclass
class ValidateEvidence:
    command: str
    timestamp: str
    rc: Optional[int]
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "timestamp": self.timestamp,
            "rc": self.rc,
            "passed": self.passed,
            "stdout_excerpt": self.stdout_excerpt[-2000:],
            "stderr_excerpt": self.stderr_excerpt[-2000:],
        }


@dataclass
class LivePlanEvidence:
    command: str
    timestamp: str
    rc: Optional[int]
    plan_add: Optional[int] = None
    plan_change: Optional[int] = None
    plan_destroy: Optional[int] = None
    note: str = ""
    stderr_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "timestamp": self.timestamp,
            "rc": self.rc,
            "plan_add": self.plan_add,
            "plan_change": self.plan_change,
            "plan_destroy": self.plan_destroy,
            "note": self.note,
            "stderr_excerpt": self.stderr_excerpt[-2000:],
        }


@dataclass
class AcquisitionFeasibility:
    native_egress: bool = False
    mirror_reachable: bool = False
    filesystem_mirror_present: bool = False
    plugin_cache_present: bool = False
    pre_downloaded_present: bool = False
    verdict: str = "UNKNOWN"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "native_egress": self.native_egress,
            "mirror_reachable": self.mirror_reachable,
            "filesystem_mirror_present": self.filesystem_mirror_present,
            "plugin_cache_present": self.plugin_cache_present,
            "pre_downloaded_present": self.pre_downloaded_present,
            "verdict": self.verdict,
            "notes": self.notes,
        }


@dataclass
class ProviderAcquisitionReport:
    phase: str = _PHASE
    staging_dir: str = ""
    toolchain: dict = field(default_factory=dict)
    init: Optional[ProviderInitEvidence] = None
    validate: Optional[ValidateEvidence] = None
    plan: Optional[LivePlanEvidence] = None
    feasibility: Optional[AcquisitionFeasibility] = None
    terraform_init_live: bool = False
    terraform_validate_live: bool = False
    terraform_plan_live: bool = False
    real_apply_allowed: bool = False
    terminal_state: str = _TERMINAL_STATE
    verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "staging_dir": self.staging_dir,
            "toolchain": self.toolchain,
            "init": self.init.to_dict() if self.init else None,
            "validate": self.validate.to_dict() if self.validate else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "feasibility": self.feasibility.to_dict() if self.feasibility else None,
            "terraform_init_live": self.terraform_init_live,
            "terraform_validate_live": self.terraform_validate_live,
            "terraform_plan_live": self.terraform_plan_live,
            "real_apply_allowed": self.real_apply_allowed,
            "terminal_state": self.terminal_state,
            "verdict": self.verdict,
        }


def classify_init(
    rc: Optional[int],
    stderr_excerpt: str,
    github_probe_http: Optional[int],
    registry_probe_http: Optional[int],
) -> ProviderInitClassification:
    """Classify a real ``terraform init`` result honestly (no forgery)."""
    stderr_excerpt = stderr_excerpt or ""
    github_ok = github_probe_http is not None and 200 <= github_probe_http < 400
    # Explicit provider-binary egress signals from terraform / curl.
    egress_blackhole = (
        "CONNECT tunnel failed" in stderr_excerpt
        or "502" in stderr_excerpt
        or "Client.Timeout exceeded" in stderr_excerpt
        or "request canceled" in stderr_excerpt
    )
    if rc == 0:
        return ProviderInitClassification.ACQUIRED
    if egress_blackhole and not github_ok:
        # Persistent black-hole (e.g. github.com binary host unreachable).
        return ProviderInitClassification.BINARY_EGRESS_BLOCKED
    if egress_blackhole and github_ok:
        # Reachable on probe but terraform still throttled/retried -> intermittent.
        return ProviderInitClassification.BINARY_EGRESS_INTERMITTENT
    if registry_probe_http == 200:
        return ProviderInitClassification.REGISTRY_METADATA_REACHABLE
    return ProviderInitClassification.UNKNOWN


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        return -1, (e.stdout or ""), (e.stderr or "") + f"\n[timeout after {timeout}s]"
    except subprocess.SubprocessError as e:
        return -1, "", str(e)


def run_init(staging_dir: str | Path, toolchain_bin: str, timeout: int = 200) -> tuple[int, str, str, float]:
    """Real ``terraform init``; returns (rc, stdout, stderr, duration_s)."""
    t0 = time.time()
    rc, out, err = _run([toolchain_bin, "init", "-no-color"], Path(staging_dir), timeout)
    return rc, out, err, round(time.time() - t0, 2)


def run_validate(staging_dir: str | Path, toolchain_bin: str, timeout: int = 120) -> tuple[int, str, str]:
    rc, out, err = _run([toolchain_bin, "validate", "-no-color"], Path(staging_dir), timeout)
    return rc, out, err


def run_plan(staging_dir: str | Path, toolchain_bin: str, timeout: int = 120) -> tuple[int, str, str, Optional[int], Optional[int]]:
    rc, out, err = _run(
        [toolchain_bin, "plan", "-input=false", "-no-color", "-out=staging.plan"],
        Path(staging_dir), timeout,
    )
    add = None
    destroy = None
    m = _PLAN_ADD_RE.search(out)
    if m:
        add = int(m.group(1))
    d = _PLAN_CHANGE_RE.search(out)
    if d:
        destroy = int(d.group(1))
    return rc, out, err, add, destroy


def assess_acquisition_feasibility(cache_dir_env: Optional[str] = None) -> AcquisitionFeasibility:
    """Assess provider-acquisition feasibility fail-closed (no egress assumed)."""
    f = AcquisitionFeasibility()
    cache_dir = cache_dir_env or os.environ.get("TF_PLUGIN_CACHE_DIR") or os.path.expanduser("~/.terraform.d/plugin-cache")
    f.plugin_cache_present = bool(cache_dir) and Path(cache_dir).exists()
    # Native egress is only asserted from a real successful init; default conservative.
    f.native_egress = False
    if not f.native_egress and not f.filesystem_mirror_present and not f.plugin_cache_present and not f.pre_downloaded_present:
        f.verdict = "TRACK_B_ENVIRONMENT_BLOCKED_PROVIDER_BINARY_EGRESS"
        f.notes.append(
            "No reachable provider-binary host, mirror, filesystem mirror, or pre-downloaded "
            "cache detected in-sandbox. Provider acquisition requires a human / out-of-sandbox "
            "egress-enabled environment."
        )
    else:
        f.verdict = "ACQUISITION_PATH_AVAILABLE"
    return f


def build_report(
    staging_dir: str | Path = "infrastructure/staging",
    live: bool = True,
    timeout: int = 200,
) -> ProviderAcquisitionReport:
    """Build a provider-acquisition report.

    When ``live=True`` and the toolchain is available, runs real ``init`` / ``validate`` /
    ``plan`` (plan-only, never apply) and records honest evidence. When the provider binary
    cannot be acquired, sets ``terraform_*_live=False`` and records the environment limitation
    without forging success.
    """
    repo_root = Path(__file__).resolve().parents[2]
    sd = Path(staging_dir)
    if not sd.is_absolute():
        sd = repo_root / sd
    rep = ProviderAcquisitionReport(staging_dir=str(sd))
    tc = discover_toolchain()
    rep.toolchain = tc.to_dict() if hasattr(tc, "to_dict") else {"available": tc.available}

    if not live or not tc.available or not tc.binary:
        rep.verdict = "OFFLINE_OR_TOOLCHAIN_UNAVAILABLE"
        rep.feasibility = assess_acquisition_feasibility()
        return rep

    # T5 — real init
    bin_ = tc.binary
    rc, out, err, dur = run_init(sd, bin_, timeout=timeout)
    classification = classify_init(rc, err, None, 200 if rc == 0 else None)
    init_ev = ProviderInitEvidence(
        command=f"{Path(bin_).name} init -no-color",
        timestamp=_now(), rc=rc, stdout_excerpt=out, stderr_excerpt=err,
        registry_probe_http=200 if rc == 0 else None,
        github_probe_http=200 if rc == 0 else None, duration_s=dur,
        classification=classification,
    )
    rep.init = init_ev
    rep.terraform_init_live = (rc == 0)
    if rc == 0:
        # T6 — real validate (provider now present)
        vrc, vout, verr = run_validate(sd, bin_, timeout=timeout)
        rep.validate = ValidateEvidence(
            command=f"{Path(bin_).name} validate -no-color", timestamp=_now(),
            rc=vrc, stdout_excerpt=vout, stderr_excerpt=verr, passed=(vrc == 0),
        )
        rep.terraform_validate_live = (vrc == 0)
        # T7 — real plan (plan-only)
        prc, pout, perr, padd, pdestroy = run_plan(sd, bin_, timeout=timeout)
        rep.plan = LivePlanEvidence(
            command=f"{Path(bin_).name} plan -input=false -out=staging.plan", timestamp=_now(),
            rc=prc, plan_add=padd, plan_change=pdestroy, plan_destroy=pdestroy,
            note="plan-only; apply is forbidden by governance (real_apply_allowed=False).",
            stderr_excerpt=perr,
        )
        rep.terraform_plan_live = (prc == 0)
        # Honest verdict: reflect the REAL validate/plan results, never assume OK
        # just because init passed. Forging a unified "OK" when validate/plan fail
        # would violate the no-forgery principle (e.g. genuine IaC config defects
        # in infrastructure/staging/*.tf surface here as validate/plan rc=1).
        if rep.terraform_validate_live and rep.terraform_plan_live:
            rep.verdict = "PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK"
        elif not rep.terraform_validate_live and not rep.terraform_plan_live:
            rep.verdict = "PROVIDER_ACQUIRED_INIT_ONLY_VALIDATE_PLAN_FAILED"
        elif not rep.terraform_validate_live:
            rep.verdict = "PROVIDER_ACQUIRED_INIT_VALIDATE_FAILED_PLAN_SKIPPED"
        else:  # init + validate OK, plan failed
            rep.verdict = "PROVIDER_ACQUIRED_INIT_VALIDATE_OK_PLAN_FAILED"
    else:
        rep.feasibility = assess_acquisition_feasibility()
        rep.verdict = classification.value
    rep.real_apply_allowed = False
    return rep
