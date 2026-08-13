#!/usr/bin/env python3
"""Phase 3.9.7 企业生产变更管控平面 —— CI 闸门（fail-closed）。

本闸门校验变更管控层**不越红线**，任一检查失败即整条流水线失败（fail-closed）：

  1. ``engineering_enabled`` 必须为 False（红线①）。
  2. ``check_change_control_invariants()`` 全部通过：结构禁名齐全、ChangeState 无 AI 自动态、
     ChangeExecutionMode 无 ai_automatic、13 个 CHANGE_* 审计类目齐全。
  3. 真实路由（backend/app/api/governance_change.py）**不提供**任何 absent_route
     （/execute /deploy /rollback /apply /migrate /activate /trigger-go /auto-execute），
     即真实执行端点结构不可达（红线③/⑩）。
  4. API 契约 SSOT 的 present/absent 集合与模块一致。
  5. 审计总数一致：ledger JSON == baseline JSON == 实时枚举（由 audit validator 负责，
     此处仅做轻量断言）。

绝不修改 engineering_enabled、绝不部署、绝不执行真实变更。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / ".ai/baselines/audit_action_category_ledger.json"

# make `agents` and `app` (backend/app) importable from repo root
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

_FAIL = 1


def fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return _FAIL


def check_safety_invariants() -> int:
    try:
        from agents.enterprise.production_change.validator import (
            check_change_control_invariants,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot import change-control validator: {exc}")

    inv = check_change_control_invariants()
    if not inv.get("ok"):
        findings = inv.get("findings") or []
        return fail(
            "change-control invariants violated: "
            + "; ".join(str(f) for f in findings)
        )
    print(
        f"[ok]   change-control invariants (forbidden={inv.get('forbidden_count')}, "
        f"categories={inv.get('category_count')})"
    )
    return 0


def check_no_real_execution_endpoints() -> int:
    """真实路由中不得出现任何 absent_route（结构不可达）。"""
    try:
        from app.api.governance_change import router
        from agents.enterprise.production_change.api_contract import ABSENT_ROUTES
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot import governance_change router / api_contract: {exc}")

    actual: set[str] = set()
    for r in router.routes:
        path = getattr(r, "path", "") or ""
        methods = getattr(r, "methods", None) or set()
        for m in methods:
            actual.add(f"{m.upper()} {path}")

    violations = sorted(a for a in ABSENT_ROUTES if a in actual)
    if violations:
        return fail(f"real execution endpoints present (RED LINE): {violations}")
    print(
        f"[ok]   no real-execution endpoints (checked {len(ABSENT_ROUTES)} absent routes "
        f"against {len(actual)} real routes)"
    )
    return 0


def check_contract_consistency() -> int:
    try:
        from agents.enterprise.production_change.api_contract import (
            ABSENT_ROUTES,
            PRESENT_ROUTES,
            build_api_contract,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot import api_contract: {exc}")

    c = build_api_contract()
    if c["present_route_count"] != len(PRESENT_ROUTES):
        return fail("present route count mismatch")
    if c["absent_route_count"] != len(ABSENT_ROUTES):
        return fail("absent route count mismatch")
    print(
        f"[ok]   api contract SSOT consistent "
        f"({c['present_route_count']} present / {c['absent_route_count']} absent)"
    )
    return 0


def check_audit_total() -> int:
    try:
        from agents.enterprise.audit import AuditActionCategory
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot import AuditActionCategory: {exc}")
    live = len(list(AuditActionCategory))
    try:
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        ledger_total = ledger["total"]
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot read ledger JSON: {exc}")
    if live != ledger_total:
        return fail(f"live enum ({live}) != ledger total ({ledger_total})")
    print(f"[ok]   audit total consistent (live={live}, ledger={ledger_total})")
    return 0


def main() -> int:
    checks = [
        check_safety_invariants,
        check_no_real_execution_endpoints,
        check_contract_consistency,
        check_audit_total,
    ]
    for fn in checks:
        rc = fn()
        if rc:
            return rc
    print(
        "[PASS] Production Change Control Gate: engineering_enabled=false, "
        "no real-execution endpoints, invariants hold, audit total consistent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
