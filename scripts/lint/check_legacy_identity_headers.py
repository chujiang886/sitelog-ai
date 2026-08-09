#!/usr/bin/env python3
"""静态扫描：禁止遗留身份头 ``x-actor-id`` / ``x-actor-kind`` 的"信任回归"。

Phase 3.8.28 起，治理身份一律由后端从 ``Authorization: Bearer <token>`` 凭据派生，
请求头无法指定责任人。这两个头**只能**出现在两类受控位置：

1. 身份包内部（``backend/app/identity/``、``frontend/src/lib/identity/``）——
   用于定义废止清单（``LEGACY_IDENTITY_HEADERS``）与伪造检测
   （``assert_no_legacy_identity_headers`` / ``IdentityHeaderForgeryError``）；
2. 测试文件（回归哨兵，断言"携带即 400"）。

除此之外——**包括注释与文档**——一律禁止出现该字面量。理由：
Phase 3.8.26 的漏洞正是"在路由里随手读一个客户端自填的头"，而这类回归最早
往往只是"在注释里提一句旧头怎么用"，随后被人照着接回去。把字面量从非授权
位置彻底清零，等于把这条路封死。

用法（被 CI 调用）：
    python scripts/lint/check_legacy_identity_headers.py --root <PROJECT_ROOT>
退出码 0 = 通过；1 = 发现违规。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 大小写不敏感匹配 x-actor-id / x-actor-kind（含各种连字符变体）。
LITERAL = re.compile(r"x-actor-(?:id|kind)", re.IGNORECASE)

# 唯一允许出现字面量的受控目录（身份包内部）。
BLESSED_DIRS = ("backend/app/identity/", "frontend/src/lib/identity/")

# 受扫描约束但允许字面量的源码范围（违规只在这些范围内查找）。
SCAN_ROOTS = ("backend/app", "backend/tests", "frontend/src")

# 测试文件路径识别：tests / __tests__ 目录、test_*.py、*.test.* / *.spec.* 前端文件。
_TEST_RE = re.compile(
    r"(?:^|/)(?:tests|__tests__)/(?:.*/)?[^/]*$"
    r"|/test_.*\.py$"
    r"|\.(?:test|spec)\.(?:ts|tsx)$"
)

_SOURCE_SUFFIXES = (".py", ".ts", ".tsx")


def _is_test(rel: str) -> bool:
    return bool(_TEST_RE.search(rel))


def _scan_file(path: Path, root: Path) -> list[tuple[str, int, str]]:
    rel = str(path.relative_to(root)).replace("\\", "/")
    if any(b in rel for b in BLESSED_DIRS):
        return []
    if _is_test(rel):
        return []
    if not rel.startswith(SCAN_ROOTS):
        return []
    violations: list[tuple[str, int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return violations
    for idx, line in enumerate(text.splitlines(), 1):
        if LITERAL.search(line):
            violations.append((rel, idx, line.strip()[:140]))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="项目根目录")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    violations: list[tuple[str, int, str]] = []
    for suffix in _SOURCE_SUFFIXES:
        for path in root.rglob(f"*{suffix}"):
            if not path.is_file():
                continue
            violations.extend(_scan_file(path, root))

    if violations:
        print(
            "FAIL：发现遗留身份头 x-actor-id / x-actor-kind 出现在非授权位置"
            "（身份包与测试之外）。\n"
            "Phase 3.8.28 起治理身份只能来自 Bearer 凭据，这两个头不得被信任或提及。"
        )
        for rel, idx, snippet in violations:
            print(f"  {rel}:{idx}: {snippet}")
        return 1

    print("OK：未发现遗留身份头信任回归（x-actor-id / x-actor-kind 仅存于身份包与测试）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
