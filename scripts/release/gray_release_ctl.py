#!/usr/bin/env python3
"""Gray Release CLI（Phase 3.2 Sprint 3.2.5-F）。

子命令：precheck / enable / disable / rollback / restore。

安全契约（红线）：
- ``enable`` 前必须：启用前快照存在 + 授权存在且生效 + G1-G6 通过；任一不满足
  → 退出码非 0，绝不翻转灰度开关；
- 本 CLI 只操作灰度配置开关，**绝不**翻转 ``engineering_enabled``、**绝不**改
  ``verified.json``、**绝不**输出 ``engineering_approved``；
- 每次操作 append-only 写入 ``release_audit.jsonl``（仅引用，无真实数值）。

默认路径指向仓库内Engineering发布产物；真实运维应通过参数指定临时/专用路径，
避免污染仓库默认文件。本阶段所有命令在仓库默认态下均会因门禁/授权缺失而拒绝。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.engineering.release.controller import (
    DEFAULT_OPERATOR,
    disable_release,
    enable_release,
    restore_release,
    rollback_release,
)
from agents.engineering.release.gate import release_precheck


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gray_release_ctl",
        description="BOIP Engineering 灰度发布控制（默认关闭，须授权+G1-G6）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=None, help="灰度配置路径（默认仓库内 gray_release.json）")
        p.add_argument("--audit-path", default=None, help="审计日志路径（默认仓库内 release_audit.jsonl）")
        p.add_argument("--snapshot-dir", default=None, help="快照目录")
        p.add_argument("--operator", default=DEFAULT_OPERATOR, help="操作人标识（标识符）")

    # precheck
    precheck_p = sub.add_parser("precheck", help="发布前 G1-G6 门禁检查")
    precheck_p.add_argument("--interface", required=True)
    precheck_p.add_argument("--approval-path", default=None)
    precheck_p.add_argument("--thresholds", default=None, help="可选：注入阈值条目 JSON 路径")
    precheck_p.add_argument("--ci-green", action="store_true")
    precheck_p.add_argument("--rollback-ready", action="store_true")
    precheck_p.add_argument("--authorized", action="store_true", help="声明已获 G6 授权，仅检查 G1-G5")
    precheck_p.add_argument("--review-log", default=None)
    precheck_p.add_argument("--operator", default=DEFAULT_OPERATOR)

    # enable
    enable_p = sub.add_parser("enable", help="启用接口灰度（前置：快照+授权+G1-G6）")
    enable_p.add_argument("--interface", required=True)
    enable_p.add_argument("--approval-id", required=True)
    enable_p.add_argument("--approval-path", default=None)
    enable_p.add_argument("--thresholds", default=None)
    enable_p.add_argument("--ci-green", action="store_true")
    enable_p.add_argument("--rollback-ready", action="store_true")
    enable_p.add_argument("--review-log", default=None)
    _add_common(enable_p)

    # disable
    disable_p = sub.add_parser("disable", help="关闭接口灰度")
    disable_p.add_argument("--interface", required=True)
    _add_common(disable_p)

    # rollback
    rollback_p = sub.add_parser("rollback", help="回滚（接口关闭或全局熔断）")
    rollback_p.add_argument("--interface", default=None)
    rollback_p.add_argument("--global", dest="global_", action="store_true")
    _add_common(rollback_p)

    # restore
    restore_p = sub.add_parser("restore", help="从快照恢复灰度配置")
    _add_common(restore_p)

    return parser


def _load_thresholds(path: str | None) -> list[dict] | None:
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("thresholds"), dict):
        return list(raw["thresholds"].values())
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "precheck":
        thresholds = _load_thresholds(getattr(args, "thresholds", None))
        allowed, reasons = release_precheck(
            interface=args.interface,
            thresholds=thresholds,
            ci_green=args.ci_green,
            rollback_ready=args.rollback_ready,
            authorization_present=args.authorized,
            review_log_path=getattr(args, "review_log", None),
        )
        print(json.dumps({"allowed": allowed, "reasons": reasons}, ensure_ascii=False, indent=2))
        return 0 if allowed else 1

    if args.command == "enable":
        result = enable_release(
            interface=args.interface,
            approval_id=args.approval_id,
            config_path=args.config,
            approval_path=args.approval_path,
            audit_path=args.audit_path,
            snapshot_dir=args.snapshot_dir,
            thresholds_path=args.thresholds,
            ci_green=args.ci_green,
            rollback_ready=args.rollback_ready,
            review_log_path=args.review_log,
            operator=args.operator,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    if args.command == "disable":
        result = disable_release(
            interface=args.interface,
            config_path=args.config,
            audit_path=args.audit_path,
            snapshot_dir=args.snapshot_dir,
            operator=args.operator,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    if args.command == "rollback":
        result = rollback_release(
            interface=args.interface,
            global_=args.global_,
            config_path=args.config,
            audit_path=args.audit_path,
            snapshot_dir=args.snapshot_dir,
            operator=args.operator,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    if args.command == "restore":
        result = restore_release(
            config_path=args.config,
            audit_path=args.audit_path,
            snapshot_dir=args.snapshot_dir,
            operator=args.operator,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    parser.error("未知子命令")
    return 2  # 不可达


if __name__ == "__main__":
    raise SystemExit(main())
