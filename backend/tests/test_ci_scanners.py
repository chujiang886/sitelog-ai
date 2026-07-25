"""Regression tests for the business-number CI scanner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
SCANNER: Path = PROJECT_ROOT / "scripts" / "lint" / "check_fabrication.py"


def _run_scanner(scan_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the scanner in a subprocess and return its complete result."""

    return subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(scan_root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_scanner_ignores_numbered_design_document_reference(tmp_path: Path) -> None:
    """A numbered Markdown source citation must not look like a business value."""

    sample = tmp_path / "tools.md"
    sample.write_text(
        "| weather | 获取风压数据 | `08_MCP_INTERFACE_DESIGN.md` |\n",
        encoding="utf-8",
    )

    result = _run_scanner(tmp_path)

    assert result.returncode == 0, result.stderr


def test_scanner_rejects_unverified_business_number(tmp_path: Path) -> None:
    """A domain term and numeric value without a source marker must fail."""

    domain_term: str = "风压阈值 "
    numeric_value: str = "2.5"
    (tmp_path / "unsafe.md").write_text(
        domain_term + numeric_value + "\n",
        encoding="utf-8",
    )

    result = _run_scanner(tmp_path)

    assert result.returncode == 1
    assert "unsafe.md" in result.stderr
