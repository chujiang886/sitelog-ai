#!/usr/bin/env python3
"""Phase 3.9.2 CI 受控激活 / RC 冻结门禁（只读，fail-closed）。

本脚本是发布闸门层的**只读** CI 入口：它从 ``--rc-spec`` 描述的发布候选构件清单出发，
在单次 CI 运行中做三道判定，且**不写入任何状态、不部署、不激活、不宣布 GO**：

1. RC 冻结检查（``ReleaseFreezeChecker``）：列出的构件必须真实存在且可读、清单自洽、
   ``engineering_enabled is False``、治理完整性 9/9、RC 状态冻结待人工；
2. 受控激活闸门（``ControlledActivationGate``）：客观检查不得 ``BLOCKED``
   （``READY_FOR_HUMAN_REVIEW`` / ``PENDING_VERIFICATION`` 视为"等待真实人工裁决"，通过）；
3. 红线复核：脚本本身不产出 ``engineering_approved``、不翻转 ``engineering_enabled``。

退出码：
- 0：RC 仍处于冻结态且受控激活闸门未 BLOCKED（即"冻结待人工裁决"，可被主理人接管）；
- 1：冻结漂移 / 闸门 BLOCKED / 治理不完整 / 红线违例 —— 必须修复后才能推进人工裁决。

本脚本**不要求也从不持有真实人工签署**；``human_signoff_roles`` 在 CI 中恒为空，
闸门据此保持 ``PENDING_VERIFICATION``，但整条流水线仍判定为通过（等待真实人工）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

# 允许以仓库根作为 import 根运行（CI checkout 后即仓库根）。
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.enterprise.production_release.release_candidate import (  # noqa: E402
    RCFreezeStatus,
    create_release_candidate,
)
from agents.enterprise.production_release.freeze_manifest import (  # noqa: E402
    generate_rc_freeze_manifest,
)
from agents.enterprise.production_release.freeze_checker import (  # noqa: E402
    ReleaseFreezeChecker,
)
from agents.enterprise.production_release.activation_evidence import (  # noqa: E402
    build_activation_evidence_bundle,
)
from agents.enterprise.production_release.activation_gate import (  # noqa: E402
    ControlledActivationGate,
    ControlledActivationGateStatus,
)
from agents.enterprise.production_release.models import (  # noqa: E402
    EvidenceIntegrityStatus,
)
from agents.config_loader import load_engineering_enabled  # noqa: E402


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _load_spec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3.9.2 CI 受控激活 / RC 冻结门禁（只读）")
    parser.add_argument("--root", default=ROOT, help="项目根目录")
    parser.add_argument(
        "--rc-spec",
        required=True,
        help="发布候选构件清单 JSON（含 rc_id/version/commit_sha/branch/component_specs 等）",
    )
    parser.add_argument(
        "--require-gate-ready",
        action="store_true",
        help="若设置，受控激活闸门必须为 READY_FOR_HUMAN_REVIEW（不允许 PENDING_VERIFICATION）才通过；"
        "默认允许 PENDING_VERIFICATION（CI 不持有真实人工签署）。",
    )
    parser.add_argument(
        "--no-git-check",
        action="store_true",
        help="跳过『Git 工作树干净』判定（本地开发验证用；CI 默认开启以要求冻结态来自干净提交）。",
    )
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    spec = _load_spec(args.rc_spec)

    raw_commit = spec.get("commit_sha", "@git")
    commit_sha = _git("rev-parse", "HEAD") if raw_commit == "@git" else raw_commit
    commit_sha = commit_sha or "<unknown>"
    rc_id = spec["rc_id"]
    version = spec["version"]
    raw_branch = spec.get("branch", "@git")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") if raw_branch == "@git" else raw_branch
    branch = branch or "<unknown>"
    component_specs: Dict[str, str] = spec["component_specs"]

    # —— 1. RC 冻结检查（只读） —— #
    rc = create_release_candidate(
        rc_id=rc_id,
        version=version,
        commit_sha=commit_sha,
        branch=branch,
        component_specs=component_specs,
        root_dir=root,
    )
    manifest = generate_rc_freeze_manifest(rc, root_dir=root)
    checker = ReleaseFreezeChecker(
        root_dir=root, check_git=not args.no_git_check, check_governance=True
    )
    freeze_result = checker.check(rc, manifest)
    frozen = freeze_result.frozen

    # —— 2. 受控激活闸门（只读；CI 不持有真实人工签署） —— #
    evidence = build_activation_evidence_bundle(
        bundle_id=f"aeb-{rc_id}",
        rc_id=rc_id,
        version=version,
        required_evidence_types=spec.get("required_evidence_types", []),
        provided_evidence_types=spec.get("provided_evidence_types", []),
        human_signoff_roles=spec.get("human_signoff_roles", []),
        freeze_manifest_sha256=manifest.manifest_sha256,
        governance_integrity_passed=True,
        rollback_reference_present=spec.get("rollback_reference_present", False),
        recovery_validation_present=spec.get("recovery_validation_present", False),
        integrity_status=EvidenceIntegrityStatus.PENDING,
    )
    gate = ControlledActivationGate(check_governance=True)
    gate_result = gate.evaluate(
        rc=rc, manifest=manifest, freeze_result=freeze_result, evidence_bundle=evidence, root_dir=root
    )
    gate_ok = gate_result.status != ControlledActivationGateStatus.BLOCKED
    if args.require_gate_ready:
        gate_ok = gate_result.status == ControlledActivationGateStatus.READY_FOR_HUMAN_REVIEW

    summary = {
        "rc_id": rc_id,
        "version": version,
        "commit_sha": commit_sha,
        "branch": branch,
        "freeze_status": freeze_result.status.value,
        "freeze_frozen": frozen,
        "freeze_checks": freeze_result.checks,
        "activation_gate_status": gate_result.status.value,
        "activation_gate_ok": gate_ok,
        "activation_gate_missing": gate_result.missing,
        "manifest_sha256": manifest.manifest_sha256,
        "human_signoff_roles": list(evidence.human_signoff_roles),
        # 真实读取 orchestrator.engineering_enabled（缺省 False），如实反映当前开关态。
        # 注意：此处输出的是「开关当前值」而非「是否处于禁用态」，避免历史误标（曾用
        # grep '.*: false' 命中即置 True，导致 JSON 字面显示 engineering_enabled=true 而实为 false）。
        "engineering_enabled": load_engineering_enabled(),
        "engineering_enabled_false_ok": load_engineering_enabled() is False,
    }

    print("Phase 3.9.2 CI 受控激活 / RC 冻结门禁结果：")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    passed = frozen and gate_ok
    if passed:
        print(
            "\n[PASS] RC 冻结态保持且受控激活闸门未 BLOCKED —— 候选处于"
            "RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN，等待真实人工裁决。"
        )
        return 0

    reasons = []
    if not frozen:
        reasons.append("RC 冻结漂移（freeze_status != frozen）")
    if not gate_ok:
        reasons.append(
            f"受控激活闸门 BLOCKED（missing={gate_result.missing}）"
            if not args.require_gate_ready
            else "受控激活闸门未达 READY_FOR_HUMAN_REVIEW"
        )
    print(f"\n[FAIL] 门禁未通过：{'; '.join(reasons)}")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())
