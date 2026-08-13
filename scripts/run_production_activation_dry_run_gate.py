#!/usr/bin/env python3
"""Phase 3.9.8 T15 —— 生产激活干跑 CI 门禁（fail-closed，SIMULATION ONLY）。

本脚本是 CI 中"生产激活干跑"门禁的独立执行体。它**只**驱动隔离沙盒
（agents/enterprise/production_release/simulation.py），断言：

  - production_activated 恒 False（红线④/⑤）
  - real_signoff_count 恒 0（红线③/④）
  - engineering_enabled 恒 False（红线①）
  - 报告状态仅 SIMULATION_PASS / SIMULATION_BLOCKED，绝不含 PRODUCTION_GO /
    engineering_approved（红线②）
  - 负路径矩阵全部 rejected=True（fail-closed 拒绝越权/污染输入）
  - 决策场景矩阵 = 14 条
  - 全过程不写真实 HumanSignoffRegistry / FinalDecisionLedger / Evidence Registry /
    生产审计命名空间（红线③/④/⑧/⑩）

任一断言失败即非零退出（fail-closed），CI 整条流水线失败。

依赖：仅需 pyyaml（audit.py → config_loader 链路）。运行：
    python -m pip install --quiet pyyaml
    python scripts/run_production_activation_dry_run_gate.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 让仓库内 agents 企业包可解析（与 governance_activation_simulation.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[1]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.production_release.simulation import (  # noqa: E402
    ProductionActivationNegativePathMatrix,
    build_decision_scenario_matrix,
    build_simulation_context,
    run_production_activation_dry_run,
)

GATE_SIMULATION_ID = os.environ.get("SIMULATION_GATE_ID", "ci-simulation-gate")
GATE_CANDIDATE_ID = os.environ.get("SIMULATION_GATE_CANDIDATE", "RC-3.9.8-SIM")
EXPECTED_SCENARIO_COUNT = 14

# 报告状态只允许这两个——绝不含 PRODUCTION_GO / engineering_approved（红线②）。
ALLOWED_REPORT_STATUS = {"simulation_pass", "simulation_blocked"}


def _fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[SIMULATION-GATE][FAIL] {message}", flush=True)
    raise SystemExit(1)


def main() -> None:
    print(
        "[SIMULATION-GATE] 启动生产激活干跑门禁（SIMULATION ONLY / NOT PRODUCTION）。",
        flush=True,
    )

    # 1) 完整干跑：只驱动隔离沙盒，ephemeral AuditService(org_id="simulation")。
    audit = AuditService(org_id="simulation")
    try:
        report = run_production_activation_dry_run(
            simulation_id=GATE_SIMULATION_ID,
            candidate_id=GATE_CANDIDATE_ID,
            scenario="production_activation_full_dry_run",
            audit=audit,
        )
    except Exception as e:  # noqa: BLE001
        _fail(f"干跑执行抛出异常（沙盒异常即视为门禁失败）：{type(e).__name__}: {e}")

    payload = report.to_dict()

    # 2) 红线断言（与后端 __post_init__ 同源，CI 再校验一次，fail-closed）。
    if payload.get("production_activated") is not False:
        _fail("production_activated 必须为 False（红线④/⑤）")
    if payload.get("real_signoff_count") != 0:
        _fail("real_signoff_count 必须为 0（红线③/④）")
    if payload.get("engineering_enabled") is not False:
        _fail("engineering_enabled 必须为 False（红线①）")
    if payload.get("status") not in ALLOWED_REPORT_STATUS:
        _fail(f"报告状态非法（应为 {sorted(ALLOWED_REPORT_STATUS)}）：{payload.get('status')}")

    # 3) 负路径矩阵：必须全部 rejected=True。
    ctx = build_simulation_context(
        simulation_id="sim-gate-negative-paths",
        candidate_id=GATE_CANDIDATE_ID,
        scenario="negative-paths",
    )
    neg_results = ProductionActivationNegativePathMatrix().evaluate(context=ctx)
    unguarded = [n.path_id for n in neg_results if not (n.expected_reject and n.rejected)]
    if unguarded:
        _fail(f"存在未被 fail-closed 拒绝的负路径（缺陷）：{unguarded}")
    if len(neg_results) < 10:
        _fail(f"负路径数量不足（应 ≥10）：{len(neg_results)}")

    # 4) 决策场景矩阵：必须 = 14 条。
    scenarios = build_decision_scenario_matrix()
    if len(scenarios) != EXPECTED_SCENARIO_COUNT:
        _fail(f"决策场景数量异常（应={EXPECTED_SCENARIO_COUNT}）：{len(scenarios)}")

    # 5) 污染检查：干跑不得产生任何真实放行语义。
    contamination = payload.get("contamination", {})
    if contamination.get("detected") is True:
        _fail(f"干跑检测到污染信号：{contamination}")

    # 6) 显式输出 SIMULATION_ONLY 声明，便于审计日志核对。
    print(
        "[SIMULATION-GATE][PASS] 生产激活干跑门禁通过（SIMULATION ONLY，未激活生产）。",
        flush=True,
    )
    print(
        f"[SIMULATION-GATE] simulation_id={GATE_SIMULATION_ID} "
        f"status={payload.get('status')} "
        f"engineering_enabled={payload.get('engineering_enabled')} "
        f"production_activated={payload.get('production_activated')} "
        f"real_signoff_count={payload.get('real_signoff_count')} "
        f"scenarios={len(scenarios)} negative_paths={len(neg_results)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
