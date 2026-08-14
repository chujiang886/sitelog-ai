#!/usr/bin/env python3
"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— CI Gate 入口（Task 41）。

供 CI 调用：运行 Validation Gate + 构建证据包 + fail-closed 扫描。
- 任意校验失败 / production 泄漏 / 终端态非法 → 退出码 1（fail-closed）。
- 全部通过 → 退出码 0，并打印证据包哈希与终端态。

不执行任何真实动作（不连接、不部署、不修改状态）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 将 BOIP 仓库根加入 sys.path，使 agents 包可导入（脚本位于 scripts/ 下）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.gate import StagingValidationGate
from agents.staging_runtime.packet import (
    build_staging_packet,
    validate_packet,
    StagingPacketScanner,
)


def main() -> int:
    identity = load_staging_identity()
    gate = StagingValidationGate(identity).run()

    if not gate.passed:
        failed = [c.name for c in gate.checks if not c.passed]
        print(f"[GATE] FAIL: checks not passed: {failed}", file=sys.stderr)
        return 1

    packet = build_staging_packet(identity)
    packet_data = packet.to_dict()

    verdict = validate_packet(packet_data)
    if not verdict.valid:
        print(f"[PACKET] INVALID: {verdict.errors}", file=sys.stderr)
        return 1

    scan = StagingPacketScanner().scan(packet)
    if not scan.certifiable:
        print(f"[SCANNER] REFUSED: {scan.findings}", file=sys.stderr)
        return 1

    print(json.dumps({
        "terminal_state": gate.terminal_state,
        "environment": gate.environment,
        "is_production": gate.is_production,
        "gate_passed": gate.passed,
        "external_pending": gate.external_pending,
        "human_verification_required": gate.human_verification_required,
        "evidence_hash": gate.evidence_hash,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
