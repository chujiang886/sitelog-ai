"""Phase 3.9.7 企业生产变更管控平面 —— API 契约 SSOT 生成器。

把变更管控 API 的**真实路由集**与**明确不存在（禁提供）的路由集**固化成机器可读 JSON
（``.ai/baselines/production_change_api_contract.json``），供 CI / 文档 / 前端对照。

契约要点（fail-closed）：
- 仅暴露「只读查看」与「真实人工登记」两类端点；
- **不提供** ``/execute`` / ``/deploy`` / ``/rollback`` / ``/apply`` / ``/migrate`` /
  ``/activate`` 等任何真实变更执行端点（红线③/⑩）；
- 所有写端点强制真实 USER + 最小权限（RELEASE_READ / RELEASE_SIGNOFF）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

AI = Path(__file__).resolve().parents[3] / ".ai" / "baselines"

# 真实存在的路由（prefix=/governance/change）。
PRESENT_ROUTES: List[Dict[str, str]] = [
    {"method": "GET", "path": "/governance/change/readiness", "op": "view_change_readiness", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/plan", "op": "record_change_plan", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/window", "op": "reserve_change_window", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/preflight", "op": "record_change_preflight", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/checkpoint", "op": "record_change_checkpoint", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/abort-policy", "op": "register_change_abort_policy", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/rollback-reference", "op": "register_change_rollback_ref", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/post-verification", "op": "record_post_change_verification", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/evidence", "op": "submit_change_evidence", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/simulation", "op": "perform_change_simulation", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/failure-scenarios", "op": "evaluate_failure_scenario", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/package", "op": "build_change_package", "perm": "governance:release:read"},
    {"method": "GET", "path": "/governance/change/decision-ledger", "op": "record_change_decision", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/plan", "op": "record_change_plan", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/window", "op": "reserve_change_window", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/preflight", "op": "record_change_preflight", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/checkpoint", "op": "record_change_checkpoint", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/abort-policy", "op": "register_change_abort_policy", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/rollback-reference", "op": "register_change_rollback_ref", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/post-verification", "op": "record_post_change_verification", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/evidence", "op": "submit_change_evidence", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/simulation", "op": "perform_change_simulation", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/failure-scenarios", "op": "evaluate_failure_scenario", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/package", "op": "build_change_package", "perm": "governance:release:read"},
    {"method": "POST", "path": "/governance/change/signoff", "op": "register_change_signoff", "perm": "governance:release:signoff"},
    {"method": "POST", "path": "/governance/change/decision", "op": "record_change_decision", "perm": "governance:release:signoff"},
]

# 明确**不提供**的路由（任何一条存在都违反红线③/⑩）。
ABSENT_ROUTES: List[str] = [
    "POST /governance/change/execute",
    "POST /governance/change/deploy",
    "POST /governance/change/rollback",
    "POST /governance/change/apply",
    "POST /governance/change/migrate",
    "POST /governance/change/activate",
    "POST /governance/change/trigger-go",
    "POST /governance/change/auto-execute",
]


def build_api_contract() -> Dict[str, object]:
    """构造 API 契约 SSOT 字典。"""

    return {
        "schema_version": 1,
        "plane": "production_change_control",
        "phase": "3.9.7-change",
        "prefix": "/governance/change",
        "red_line": "fail-closed; no real execution endpoints; real USER + min-permission only",
        "present_routes": PRESENT_ROUTES,
        "present_route_count": len(PRESENT_ROUTES),
        "absent_routes": ABSENT_ROUTES,
        "absent_route_count": len(ABSENT_ROUTES),
        "note": "本契约为 SSOT；任何 absent_route 若真实存在即违反红线③/⑩，CI 须失败。",
    }


def write_api_contract_json(out_path: Path | None = None) -> Path:
    """把 API 契约写入 ``.ai/baselines/production_change_api_contract.json``。"""

    out = out_path or (AI / "production_change_api_contract.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(build_api_contract(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


__all__ = [
    "PRESENT_ROUTES",
    "ABSENT_ROUTES",
    "build_api_contract",
    "write_api_contract_json",
]
