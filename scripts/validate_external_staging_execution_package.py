#!/usr/bin/env python3
"""Phase 3.9.11 —— 校验确定性执行包（fail-closed）。

断言：
- phase == 3.9.11
- terminal_state == EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO
- contains_real_secret == False
- production_activation_prohibited == True
- engineering_enabled == False
- gate.status == pending_external_staging_resource
- environment_identity.production == False
- 重算 package_hash == 存储 hash（确定性 / 未被篡改）
- 全包无 forbidden token（go / approved / production_ready / executed / ...）
- pending_resources 数 == 8

exit: 0 = PASS, 1 = 违反（fail-closed）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.external_staging_execution.models import (
    EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE,
)
from agents.external_staging_execution.package import package_hash
from agents.external_staging_qualification.models import GateStatus

# 闸门仅允许 4 态（禁止 APPROVED/PRODUCTION_READY/GO）。
ALLOWED_GATE_STATUSES = {s.value for s in GateStatus}


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[FAIL] {msg}")
    sys.exit(1)


def main() -> int:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
    else:
        p = REPO_ROOT / ".ai" / "staging" / "external_staging_execution_qualification_package.json"

    if not p.is_file():
        _fail(f"package not found: {p}")

    d = json.loads(p.read_text(encoding="utf-8"))

    if d.get("phase") != "3.9.11":
        _fail(f"phase={d.get('phase')} != 3.9.11")
    if d.get("terminal_state") != EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE:
        _fail(f"terminal_state={d.get('terminal_state')} != {EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE}")
    if d.get("contains_real_secret") is not False:
        _fail("contains_real_secret must be False")
    if d.get("production_activation_prohibited") is not True:
        _fail("production_activation_prohibited must be True")
    if d.get("engineering_enabled") is not False:
        _fail("engineering_enabled must be False")
    if d.get("gate", {}).get("status") != "pending_external_staging_resource":
        _fail(f"gate.status={d.get('gate', {}).get('status')} != pending_external_staging_resource")
    if d.get("environment_identity", {}).get("production") is not False:
        _fail("environment_identity.production must be False")

    if package_hash(d) != d.get("package_hash"):
        _fail("package_hash mismatch (non-deterministic or tampered)")

    gate_status = d.get("gate", {}).get("status")
    if gate_status not in ALLOWED_GATE_STATUSES:
        _fail(f"gate.status={gate_status!r} 不在允许 4 态 {ALLOWED_GATE_STATUSES}（含禁止态 GO/APPROVED）")

    if len(d.get("pending_resources", [])) != 8:
        _fail(f"pending_resources count={len(d.get('pending_resources', []))} != 8")

    print(
        "[PASS] execution package valid (fail-closed): phase=3.9.11, "
        "gate=pending_external_staging_resource, hash deterministic, "
        "no real secret, no GO"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
