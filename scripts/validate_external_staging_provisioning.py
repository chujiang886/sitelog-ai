#!/usr/bin/env python3
"""Phase 3.9.12 —— 校验确定性供给算子包（fail-closed）。

断言：
- phase == 3.9.12
- terminal_state == EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO
- contains_real_secret == False
- production_activation_prohibited == True
- engineering_enabled == False
- operator_gate.status ∈ {blocked, pending_human_input, ready_for_human_provisioning_review}
  （**禁** GO / APPROVED / PRODUCTION_READY）
- environment_identity.production == False
- 重算 package_hash == 存储 hash（确定性 / 未被篡改）
- 全包无 forbidden token（go / approved / production_ready / production_apply / auto / executed / ...）
- pending_resources 数 == 8

exit: 0 = PASS, 1 = 违反（fail-closed）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.external_staging_provisioning.models import (
    EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE,
)
from agents.external_staging_provisioning.package import package_hash

# Operator Gate 仅允许 3 态（禁止 GO/APPROVED/PRODUCTION_READY）。
ALLOWED_OPERATOR_GATE_STATUSES = {
    "blocked",
    "pending_human_input",
    "ready_for_human_provisioning_review",
}

# 全包禁止 token（小写匹配）。
_FORBIDDEN_TOKENS = (
    "go",
    "approved",
    "production_ready",
    "production_apply",
    "auto",
    "automatic",
    "executed",
    "deploy_production",
    "engineering_approved",
)


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _has_forbidden_token(text: str) -> str | None:
    lowered = text.lower()
    for tok in _FORBIDDEN_TOKENS:
        if re.search(rf"(?i)(?<![\w]){re.escape(tok)}(?![\w])", lowered):
            return tok
    return None


def main() -> int:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
    else:
        p = (
            REPO_ROOT
            / ".ai"
            / "staging"
            / "external_staging_provisioning_operator_package.json"
        )

    if not p.is_file():
        _fail(f"package not found: {p}")

    d = json.loads(p.read_text(encoding="utf-8"))

    if d.get("phase") != "3.9.12":
        _fail(f"phase={d.get('phase')} != 3.9.12")
    if d.get("terminal_state") != EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE:
        _fail(
            f"terminal_state={d.get('terminal_state')} "
            f"!= {EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE}"
        )
    if d.get("contains_real_secret") is not False:
        _fail("contains_real_secret must be False")
    if d.get("production_activation_prohibited") is not True:
        _fail("production_activation_prohibited must be True")
    if d.get("engineering_enabled") is not False:
        _fail("engineering_enabled must be False")
    if d.get("environment_identity", {}).get("production") is not False:
        _fail("environment_identity.production must be False")

    gate_status = d.get("operator_gate", {}).get("status")
    if gate_status not in ALLOWED_OPERATOR_GATE_STATUSES:
        _fail(
            f"operator_gate.status={gate_status!r} 不在允许 3 态 "
            f"{ALLOWED_OPERATOR_GATE_STATUSES}（含禁止态 GO/APPROVED/PRODUCTION_READY）"
        )

    if package_hash(d) != d.get("package_hash"):
        _fail("package_hash mismatch (non-deterministic or tampered)")

    # 全包 forbidden token 扫描
    blob = json.dumps(d, ensure_ascii=False)
    hit = _has_forbidden_token(blob)
    if hit:
        _fail(f"package 含禁止 token={hit!r}（GO/APPROVED/PRODUCTION/AUTO 等语义）")

    if len(d.get("pending_resources", [])) != 8:
        _fail(f"pending_resources count={len(d.get('pending_resources', []))} != 8")

    print(
        "[PASS] provisioning operator package valid (fail-closed): "
        f"phase=3.9.12, gate={gate_status}, hash deterministic, "
        "no real secret, no GO/APPROVED/PRODUCTION/AUTO"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
