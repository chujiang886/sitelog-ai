"""Generate the machine-readable production activation review packet (Phase 3.9.6).

Read-only: assembles the activation-readiness dossier from repo facts and serializes
the human-review-relevant subset to `.ai/release-gate/production_activation_review_packet.json`.

This is an evidence/input artifact for real-human Go/No-Go. It NEVER asserts APPROVED
or PRODUCTION_READY. Terminal state is fixed at
PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.enterprise.production_release import (  # noqa: E402
    assemble_activation_readiness_dossier,
)
from agents.enterprise.production_release.human_signoff import (  # noqa: E402
    HumanSignoffRegistry,
)

RC_ID = "RC-3.9.6"


def main() -> int:
    registry = HumanSignoffRegistry(rc_id=RC_ID)
    d = assemble_activation_readiness_dossier(
        rc_id=RC_ID, root_dir=str(ROOT), signoff_registry=registry
    )

    rg = d["readiness_gate"]
    contract = d["contract"]

    packet = {
        "schema_version": "1.0.0",
        "artifact": "production_activation_review_packet",
        "phase": "3.9.6",
        "rc_id": RC_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contains_real_secret": False,
        "terminal_status": d["status_terminal"],
        "engineering_enabled": d["engineering_enabled"],
        "governance_integrity_9_9": rg["checks"].get("governance_integrity_9_9"),
        "evidence_bundle_complete": d["evidence_bundle"]["production_evidence_complete"],
        "readiness_gate": {
            "gate_id": rg["gate_id"],
            "status": rg["status"],
            "checks": rg["checks"],
            "missing": rg["missing"],
            "note": rg.get("note"),
        },
        "contract": {
            "required_gates": list(contract["required_gates"]),
            "required_evidence": list(contract["required_evidence"]),
            "required_signoffs": list(contract["required_signoffs"]),
            "blocker_count": contract["blocker_count"],
            "pending_count": contract["pending_count"],
            "activation_allowed_for_human": contract["activation_allowed_for_human"],
            "note": contract.get("note"),
        },
        "evidence_bundle": {
            "bundle_id": d["evidence_bundle"]["bundle_id"],
            "version": d["evidence_bundle"]["version"],
            "item_count": d["evidence_bundle"]["item_count"],
            "production_evidence_complete": d["evidence_bundle"]["production_evidence_complete"],
            "items": d["evidence_bundle"]["items"],
        },
        "blockers": d["blockers"],
        "pending_verification": d["pending_verification"],
        "signoff_requirements": d["signoff_requirements"],
        "sod": d["sod"],
        "human_review_required": True,
        "automated_approval_prohibited": True,
        "next_human_actions": [
            "主理人 + 四角色线下提交真实生产激活证据（RC 冻结基线 / 回滚 runbook / 真实凭证占位）",
            "四角色（production-owner / release-manager / security-owner / auditor）线下完成各自签署",
            "主理人显式置 engineering_enabled=true（唯一人类终端动作，AI 不代执行）",
        ],
    }

    out_path = ROOT / ".ai" / "release-gate" / "production_activation_review_packet.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[ok] wrote {out_path} "
        f"(terminal_status={packet['terminal_status']}, "
        f"gate={packet['readiness_gate']['status']}, "
        f"contract.allowed={packet['contract']['activation_allowed_for_human']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
