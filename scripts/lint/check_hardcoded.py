#!/usr/bin/env python3
"""Detect hard-coded business thresholds, brands, and model identifiers."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

RED: str = "\033[31m"
GREEN: str = "\033[32m"
RESET: str = "\033[0m"
SCANNED_SUFFIXES: frozenset[str] = frozenset({".js", ".py", ".ts", ".tsx"})
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset(
    {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules", "tests"}
)
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "business threshold",
        re.compile(
            r"\b(?:threshold|business_limit|risk_limit|min_business|max_business)\w*\s*[:=]\s*-?\d+(?:\.\d+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "brand",
        re.compile(r"[\"']?(?:brand|品牌)[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", re.IGNORECASE),
    ),
    (
        "model",
        re.compile(r"[\"']?(?:model|型号)[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", re.IGNORECASE),
    ),
)
ALLOW_MARKERS: tuple[str, ...] = ("pending_verification", "# infrastructure-config")


@dataclass(frozen=True, slots=True)
class Finding:
    """One hard-coded business configuration finding."""

    path: Path
    line_number: int
    category: str
    line: str


def iter_source_files(root: Path) -> Iterable[Path]:
    """Yield supported source files outside generated directories."""

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def scan_file(path: Path) -> list[Finding]:
    """Inspect a source file for forbidden hard-coded business configuration."""

    findings: list[Finding] = []
    try:
        lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings

    for line_number, line in enumerate(lines, start=1):
        normalized_line: str = line.lower()
        if any(marker in normalized_line for marker in ALLOW_MARKERS):
            continue
        for category, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        path=path,
                        line_number=line_number,
                        category=category,
                        line=line.strip(),
                    )
                )
    return findings


def parse_args() -> argparse.Namespace:
    """Parse the optional scan root."""

    default_root: Path = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    return parser.parse_args()


def main() -> int:
    """Run the scan and return nonzero when review is required."""

    args: argparse.Namespace = parse_args()
    root: Path = args.root.resolve()
    findings: list[Finding] = []
    for path in iter_source_files(root):
        findings.extend(scan_file(path))

    if findings:
        print(f"{RED}发现硬编码业务配置：{len(findings)} 项{RESET}", file=sys.stderr)
        for finding in findings:
            relative_path: Path = finding.path.relative_to(root)
            print(
                f"{RED}{relative_path}:{finding.line_number} [{finding.category}] "
                f"{finding.line}{RESET}",
                file=sys.stderr,
            )
        return 1

    print(f"{GREEN}硬编码扫描通过：未发现业务阈值、品牌或型号。{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
