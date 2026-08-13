"""Validate the machine-readable production activation review packet (Phase 3.9.6, schema 2.0.0).

Fail-closed: any deviation from the governance contract aborts with a non-zero exit so CI
cannot go green on a tampered, drifted, or non-BUILT_NO_GO packet.

Checks
------
1. schema_version must be 2.x.
2. terminal_status == PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO.
3. engineering_enabled is False (never flipped by AI).
4. contains_real_secret is False.
5. packet_sha256 matches the canonical (timestamp- and hash-excluded) payload — tamper-evident.
6. layer_b section present (Layer A + Layer B both documented, closing the closure-report drift).
7. blockers == 6 (B1-B6) and pending_verification == 6 (PV1-PV6) — 1:1 with the machine gate.
8. No forbidden release tokens (/activate, /deploy-production, PRODUCTION_GO, engineering_approved).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKET_PATH = ROOT / ".ai" / "release-gate" / "production_activation_review_packet.json"

_FORBIDDEN_TOKENS = (
    "/activate",
    "/deploy-production",
    "PRODUCTION_GO",
    "engineering_approved",
)


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    raise SystemExit(f"[FAIL] {msg}")


def _canonical_payload(packet: dict) -> str:
    canonical = {k: v for k, v in packet.items() if k != "packet_sha256"}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    if not PACKET_PATH.exists():
        _fail(f"packet not found: {PACKET_PATH}")

    try:
        packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail(f"packet is not valid JSON: {e}")

    sv = str(packet.get("schema_version", ""))
    if not sv.startswith("2."):
        _fail(f"schema_version must be 2.x, got {sv!r}")

    if packet.get("terminal_status") != "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO":
        _fail(
            f"terminal_status must be BUILT_NO_GO, got {packet.get('terminal_status')!r}"
        )

    if packet.get("engineering_enabled") is not False:
        _fail("engineering_enabled must be False (never flipped by AI)")

    if packet.get("contains_real_secret") is not False:
        _fail("contains_real_secret must be False")

    # 9) 篡改检测：规范哈希比对。
    expect = hashlib.sha256(
        _canonical_payload(packet).encode("utf-8")
    ).hexdigest()
    if packet.get("packet_sha256") != expect:
        _fail("packet_sha256 mismatch — packet tampered or needs regeneration")

    # 10) Layer B 节必须存在（闭合收口报告遗漏 Layer B 的漂移）。
    if "layer_b" not in packet:
        _fail("layer_b section missing (Layer A+B must both be documented)")
    if "operations" not in packet["layer_b"].get("boundary", {}):
        _fail("layer_b.boundary.operations missing")

    # 11) 阻断器 / pending 1:1 对齐机器闸门。
    blockers = packet.get("blockers", [])
    pending = packet.get("pending_verification", [])
    if len(blockers) != 6:
        _fail(f"blockers must be 6 (B1-B6), got {len(blockers)}")
    if len(pending) != 6:
        _fail(f"pending_verification must be 6 (PV1-PV6), got {len(pending)}")

    # 12) 放行词元扫描（fail-closed）：排除"禁止端点声明"字段本身。
    scan_packet = {k: v for k, v in packet.items() if k != "forbidden_endpoints"}
    blob = json.dumps(scan_packet, ensure_ascii=False)
    for tok in _FORBIDDEN_TOKENS:
        if tok in blob:
            _fail(f"forbidden release token present in packet: {tok!r}")

    print(
        f"[ok] packet valid "
        f"(schema={sv}, terminal={packet['terminal_status']}, "
        f"blockers={len(blockers)}, pending={len(pending)}, "
        f"sha256={packet['packet_sha256'][:12]}...)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
