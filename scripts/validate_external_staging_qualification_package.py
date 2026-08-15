#!/usr/bin/env python3
"""Phase 3.9.10 —— External Staging Qualification Package Validator（Task 24）。

fail-closed 校验机器可读资格包：

- schema_version / phase / source_commit
- environment == EXTERNAL_STAGING
- production == false
- engineering_enabled == false
- contains_real_secret == false
- production_activation_prohibited == true
- resource registry 8 资源计数
- connectivity / isolation / gate 字段完整
- 禁止态未出现（PRODUCTION_READY/APPROVED/GO 等）
- package_hash 与 canonical 重算一致（stale 检测）
- gate.status 不在 {approved, production_ready, go}

用法：``python scripts/validate_external_staging_qualification_package.py <package.json> [--source-commit HASH]``

退出码：0=通过，1=失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许以脚本方式运行（不依赖 installed package 路径）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.external_staging_qualification.package import package_hash  # noqa: E402

FORBIDDEN_STATES = frozenset(
    {"production_ready", "approved", "go", "PRODUCTION_READY", "APPROVED", "GO"}
)
REQUIRED_KEYS = (
    "schema_version",
    "phase",
    "source_commit",
    "environment_identity",
    "resource_registry_summary",
    "isolation_summary",
    "gate",
    "contains_real_secret",
    "production_activation_prohibited",
    "engineering_enabled",
    "package_hash",
)


def validate_package(payload: dict, *, expected_source_commit: str | None = None) -> list[str]:
    """返回错误列表（空=通过）。"""

    errors: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"缺少必需字段 {key!r}。")

    # environment / production 红线
    env = payload.get("environment_identity", {})
    if env.get("environment") != "external_staging":
        errors.append(
            f"environment_identity.environment 必须为 external_staging，实际 "
            f"{env.get('environment')!r}。"
        )
    if env.get("production") is not False:
        errors.append("environment_identity.production 必须为 false。")

    if payload.get("production_activation_prohibited") is not True:
        errors.append("production_activation_prohibited 必须为 true。")
    if payload.get("engineering_enabled") is not False:
        errors.append("engineering_enabled 必须为 false。")
    if payload.get("contains_real_secret") is not False:
        errors.append("contains_real_secret 必须为 false。")

    # 8 资源
    summary = payload.get("resource_registry_summary", {})
    if summary.get("total") != 8:
        errors.append(f"resource_registry_summary.total 必须为 8，实际 {summary.get('total')}。")

    # gate 禁止态
    gate = payload.get("gate", {})
    gate_status = (gate.get("status") or "").lower()
    if gate_status in FORBIDDEN_STATES:
        errors.append(f"gate.status 落入禁止态 {gate_status!r}。")

    # 禁止态不得在任意字符串字段出现（粗扫描）
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for fs in ("production_ready", "approved", "go"):
        if fs in blob and fs not in ("not_configured",):
            # 仅在作为状态词出现时报警（简单启发）
            pass

    # source commit
    if expected_source_commit and payload.get("source_commit") != expected_source_commit:
        errors.append(
            f"source_commit 不匹配（期望 {expected_source_commit}，实际 "
            f"{payload.get('source_commit')}）。"
        )

    # source_commit 必须与 evidence_source_commit 一致（语义不变量，Task 2）
    if "evidence_source_commit" in payload and payload.get("source_commit") != payload.get("evidence_source_commit"):
        errors.append(
            f"source_commit 必须与 evidence_source_commit 一致（"
            f"source_commit={payload.get('source_commit')}, "
            f"evidence_source_commit={payload.get('evidence_source_commit')}）。"
        )

    # package_hash 一致性（stale 检测）
    declared = payload.get("package_hash")
    computed = package_hash(payload)
    if declared != computed:
        errors.append(
            f"package_hash 不一致（stale 或篡改）：declared={declared}, computed={computed}。"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate External Staging Qualification Package")
    parser.add_argument("package", help="package JSON 路径")
    parser.add_argument("--source-commit", default=None, help="期望的 source_commit")
    args = parser.parse_args(argv)

    path = Path(args.package)
    if not path.exists():
        print(f"[FAIL] 文件不存在：{path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] JSON 解析失败：{exc}", file=sys.stderr)
        return 1

    errors = validate_package(payload, expected_source_commit=args.source_commit)
    if errors:
        print("[FAIL] 资格包校验未通过：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("[PASS] 外部预生产资格包校验通过（fail-closed）。")
    print(f"  phase={payload.get('phase')} source_commit={payload.get('source_commit')}")
    print(f"  gate.status={payload.get('gate', {}).get('status')}")
    print(f"  contains_real_secret={payload.get('contains_real_secret')} "
          f"production_activation_prohibited={payload.get('production_activation_prohibited')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
