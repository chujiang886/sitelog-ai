#!/usr/bin/env python3
"""Reject unverified business numbers and leaked key fingerprints in repo.

T07 起额外承担指纹扫描：
- 仅扫描 markdown 文件；
- 发现 FABRICATED_KEYS 中 12+ 字符子串（与真实 key 指纹重叠足够长）即报错；
- 永远不扫描 .env / .env.*（避免读取本地凭证）。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

RED: str = "\033[31m"
GREEN: str = "\033[32m"
YELLOW: str = "\033[33m"
RESET: str = "\033[0m"
PENDING_MARKER: str = "pending_verification"

# 业务数字扫描：覆盖所有支持的文件后缀
SCANNED_SUFFIXES: frozenset[str] = frozenset(
    {".js", ".json", ".md", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
)
# 指纹扫描：仅 markdown（人眼最容易泄露 key 的地方）
FINGERPRINT_SUFFIXES: frozenset[str] = frozenset({".md"})
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset(
    {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules"}
)
EXCLUDED_FILE_NAMES: frozenset[str] = frozenset({".env"})

# T07 接入真实 LLM 后登记的敏感 key 指纹黑名单。
# FABRICATED_KEYS 中的任一子串若在 markdown 中被命中，且长度 >= FINGERPRINT_MIN_LENGTH，
# 即视为凭证泄露，立刻报错。
#
# 当前登记：
#   - "sk-sp-D.LYXXH"（12 字符）：track_a DashScope key 指纹前 12 字符
#   - "bi8"（4 字符）：同一 key 指纹后 4 字符（保留以备未来补 12+ 字符规则）
#
# 注意：黑名单只登记"短指纹 + 文档化用途"，绝对禁止把完整 key / 长指纹放进本文件。
FABRICATED_KEYS: tuple[str, ...] = (
    "sk-sp-D.LYXXH",
    "bi8",
)
FINGERPRINT_MIN_LENGTH: int = 12  # markdown 中出现 12+ 字符的重叠子串即触发

BUSINESS_TERMS: tuple[str, ...] = (
    "wind[_ -]?pressure",
    "风压",
    "floor[_ -]?(?:level|range|threshold)",
    "楼层",
    "wall[_ -]?thickness",
    "壁厚",
    "score[_ -]?weight",
    "评分权重",
    "service[_ -]?life",
    "使用寿命",
    "corrosion[_ -]?(?:level|threshold)",
    "防腐等级",
)
NUMBER_PATTERN: re.Pattern[str] = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:\s*%)?")
TERM_PATTERN: re.Pattern[str] = re.compile("|".join(BUSINESS_TERMS), re.IGNORECASE)
DOCUMENT_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"`\d{2}_[A-Z0-9_]+\.md`",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One line containing a business number without verification status."""

    path: Path
    line_number: int
    line: str


@dataclass(frozen=True, slots=True)
class FingerprintFinding:
    """One markdown line containing a leaked key fingerprint substring."""

    path: Path
    line_number: int
    matched_substring: str
    line: str


def iter_source_files(root: Path) -> Iterable[Path]:
    """Yield deterministic, supported files while skipping generated content."""

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        yield path


def iter_markdown_files(root: Path) -> Iterable[Path]:
    """Yield markdown files for fingerprint scanning (skip .env by extension and name)."""

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in FINGERPRINT_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        # 双重保险：即便有人手贱把 .env 写成 .md（极不可能）也跳过本脚本自身
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        yield path


def scan_file(path: Path) -> list[Finding]:
    """Return unverified business-number findings from a UTF-8 text file."""

    findings: list[Finding] = []
    try:
        lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings

    for line_number, line in enumerate(lines, start=1):
        if PENDING_MARKER in line.lower():
            continue
        scan_line: str = DOCUMENT_REFERENCE_PATTERN.sub("", line)
        if TERM_PATTERN.search(scan_line) and NUMBER_PATTERN.search(scan_line):
            findings.append(Finding(path=path, line_number=line_number, line=line.strip()))
    return findings


def scan_markdown_for_fingerprints(path: Path) -> list[FingerprintFinding]:
    """Return markdown lines that contain >= FINGERPRINT_MIN_LENGTH chars from FABRICATED_KEYS."""

    findings: list[FingerprintFinding] = []
    try:
        lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings

    long_markers: tuple[str, ...] = tuple(
        marker for marker in FABRICATED_KEYS if len(marker) >= FINGERPRINT_MIN_LENGTH
    )
    if not long_markers:
        return findings

    for line_number, line in enumerate(lines, start=1):
        for marker in long_markers:
            if marker in line:
                findings.append(
                    FingerprintFinding(
                        path=path,
                        line_number=line_number,
                        matched_substring=marker,
                        line=line.strip(),
                    )
                )
                break  # 一行只报一次，避免刷屏
    return findings


def parse_args() -> argparse.Namespace:
    """Parse the optional scan root."""

    default_root: Path = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    return parser.parse_args()


def main() -> int:
    """Scan repository files and return a CI-compatible exit status."""

    args: argparse.Namespace = parse_args()
    root: Path = args.root.resolve()
    findings: list[Finding] = []
    for path in iter_source_files(root):
        findings.extend(scan_file(path))

    fingerprint_findings: list[FingerprintFinding] = []
    for path in iter_markdown_files(root):
        fingerprint_findings.extend(scan_markdown_for_fingerprints(path))

    exit_code: int = 0

    if findings:
        print(f"{RED}发现未标记的业务数字：{len(findings)} 项{RESET}", file=sys.stderr)
        for finding in findings:
            relative_path: Path = finding.path.relative_to(root)
            print(
                f"{RED}{relative_path}:{finding.line_number}: {finding.line}{RESET}",
                file=sys.stderr,
            )
        print(
            f"{RED}请补充可靠来源，或明确标记 {PENDING_MARKER}。{RESET}",
            file=sys.stderr,
        )
        exit_code = 1

    if fingerprint_findings:
        print(
            f"{RED}发现敏感 key 指纹泄露：{len(fingerprint_findings)} 项{RESET}",
            file=sys.stderr,
        )
        for finding in fingerprint_findings:
            relative_path: Path = finding.path.relative_to(root)
            print(
                f"{RED}{relative_path}:{finding.line_number}: 命中子串 "
                f"{finding.matched_substring!r} | {finding.line}{RESET}",
                file=sys.stderr,
            )
        print(
            f"{RED}请立即从 markdown / 报告中删除敏感 key 内容，"
            f"key 仅允许保存在 .env（已 .gitignore）。{RESET}",
            file=sys.stderr,
        )
        exit_code = 1

    if exit_code == 0:
        print(f"{GREEN}业务数字 + key 指纹扫描通过：未发现未验证数值或凭证泄露。{RESET}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())