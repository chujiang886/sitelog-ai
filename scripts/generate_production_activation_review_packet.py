"""Generate the machine-readable production activation review packet (Phase 3.9.6, schema 2.0.0).

Read-only: assembles the activation-readiness dossier from repo facts and serializes the
human-review-relevant subset to `.ai/release-gate/production_activation_review_packet.json`.

This is an evidence/input artifact for real-human Go/No-Go. It NEVER asserts APPROVED or
PRODUCTION_READY. Terminal state is fixed at
PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO.

Schema 2.0.0 changes (Phase 3.9.6-R1 boundary reconciliation):
- ``generated_at`` is derived from the current commit timestamp (``git show -s --format=%cI HEAD``),
  making the packet deterministic per commit (freshness is proven by ``git diff --exit-code`` in CI:
  if code changes, the packet changes and the committed copy must be regenerated).
- ``packet_sha256`` is the SHA-256 over the canonical (timestamp- and hash-excluded) payload, so the
  packet is tamper-evident and the validator can re-derive it.
- A ``layer_b`` section is added (permission boundary + evidence-storage-safety policy) so the packet
  now documents BOTH Layer A (objective readiness) and Layer B (human evidence intake & decision
  recording) — closing the Phase 3.9.6 closure-report drift where Layer B was omitted.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.enterprise.production_release import (  # noqa: E402
    assemble_activation_readiness_dossier,
)
from agents.enterprise.production_release.evidence_storage_safety import (  # noqa: E402
    EvidenceStoragePolicy,
)
from agents.enterprise.production_release.human_signoff import (  # noqa: E402
    HumanSignoffRegistry,
)
from agents.enterprise.production_release.permission_boundary import (  # noqa: E402
    ActivationPermissionBoundary,
)

RC_ID = "RC-3.9.6"
SCHEMA_VERSION = "2.0.0"

# 放行词元（红线②⑤⑩）：任何一条出现在序列化产物中即视为契约违反。
_FORBIDDEN_TOKENS = (
    "/activate",
    "/deploy-production",
    "PRODUCTION_GO",
    "engineering_approved",
)


def _canonical_payload(packet: dict) -> str:
    """排除 ``packet_sha256`` 后的规范序列化（排序键、紧凑分隔）。

    注意：包中**不嵌入**任何提交 SHA / 时间戳等每提交变化的值，保证在同一仓库状态下
    重新生成字节级一致，从而 ``git diff --exit-code``（CI 漂移检测）只在 dossier 真正
    变化时才失败——这是该门禁能正确工作的前提。新鲜度由 dossier 派生内容（审计账本 /
    配置 / 契约）与 ``packet_sha256`` 共同兜底。
    """

    canonical = {k: v for k, v in packet.items() if k != "packet_sha256"}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    registry = HumanSignoffRegistry(rc_id=RC_ID)
    d = assemble_activation_readiness_dossier(
        rc_id=RC_ID, root_dir=str(ROOT), signoff_registry=registry
    )

    rg = d["readiness_gate"]
    contract = d["contract"]

    # Layer B 结构事实（确定性、可复现，来自代码而非运行时提交）。
    perm = ActivationPermissionBoundary(rc_id=RC_ID)
    layer_b = {
        "boundary": perm.describe(),
        "evidence_storage_policy": {
            "store_by_reference_only": True,
            "rejects_inline_content": True,
            "rejects_secret_like_reference": True,
            "never_holds_evidence_plaintext": True,
            "rules": [
                "ensure_no_inline_content: 拒收任何 inline 证据正文，只收引用",
                "ensure_reference_not_secret: 拒把裸密钥/令牌当引用存（sk-/ghp_/PRIVATE KEY/...）",
                "issue_receipt: 仅签发含引用+哈希的回执，不持有任何原文",
            ],
            "note": "T13 存储安全：只存引用与哈希，永存原文，防止生产密钥/数据进入仓库或审计流",
        },
        "intake_operations": [
            "submit_evidence（真实 USER + RELEASE_READ + T13 存储安全）",
            "record_evidence_decision（真实 USER + RELEASE_SIGNOFF + 人工裁决）",
            "register_signoff（真实 USER + RELEASE_SIGNOFF，四角色签署）",
            "build_review_package（真实 USER + RELEASE_READ，材料≠裁决）",
            "record_final_decision（真实 USER + RELEASE_SIGNOFF，登记人裁决，永不激活）",
        ],
        "note": (
            "Layer B 只登记事实与人工裁决，绝不翻转 engineering_enabled / 不宣布 GO / "
            "不激活；HUMAN_GO_RECORDED ≠ PRODUCTION_ACTIVATED（红线②⑤⑩）"
        ),
    }

    packet: dict = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "production_activation_review_packet",
        "phase": "3.9.6",
        "rc_id": RC_ID,
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
        "layer_b": layer_b,
        "human_review_required": True,
        "automated_approval_prohibited": True,
        "forbidden_endpoints": ["/activate", "/deploy-production", "/go", "engineering_approved 输出"],
        "next_human_actions": [
            "主理人 + 四角色线下提交真实生产激活证据（RC 冻结基线 / 回滚 runbook / 真实凭证占位）",
            "四角色（production-owner / release-manager / security-owner / auditor）线下完成各自签署",
            "主理人在人类终端显式置 engineering_enabled=true（唯一人类终端动作，AI 不代执行）",
        ],
    }

    # 规范哈希（排除 generated_at / packet_sha256）。
    packet["packet_sha256"] = hashlib.sha256(
        _canonical_payload(packet).encode("utf-8")
    ).hexdigest()

    # 放行词元扫描（fail-closed）：排除"禁止端点声明"字段本身，只扫业务事实字段。
    scan_packet = {k: v for k, v in packet.items() if k != "forbidden_endpoints"}
    blob = json.dumps(scan_packet, ensure_ascii=False)
    for tok in _FORBIDDEN_TOKENS:
        if tok in blob:
            raise SystemExit(f"[FAIL] forbidden token in packet: {tok!r}")

    out_path = ROOT / ".ai" / "release-gate" / "production_activation_review_packet.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[ok] wrote {out_path} "
        f"(schema={packet['schema_version']}, "
        f"terminal_status={packet['terminal_status']}, "
        f"gate={packet['readiness_gate']['status']}, "
        f"contract.allowed={packet['contract']['activation_allowed_for_human']}, "
        f"sha256={packet['packet_sha256'][:12]}...)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
