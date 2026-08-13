#!/usr/bin/env python3
"""收口提交完整性门禁（Phase 3.9.6 T2，只读 / fail-closed）。

目的
----
阶段收口最容易出现的治理漂移是：**报告写完了，但没有进入真实版本历史**
（未 `git add`、只存在于工作树、或与 HEAD 版本不一致）。此时文档声称"已收口"，
Git 却无法为其作证 —— 一旦换机器、换分支或回滚，收口证据即凭空消失。

本脚本把"收口产物必须已进入真实 Git 历史"变成机器可读、可在 CI fail-closed
执行的检查，并输出结构化的 ``ClosureCommitIntegrityResult`` 作为报告证据。

检查对象（五类收口产物）
------------------------
report    阶段收口报告（3.9.2 RC 冻结 / 3.9.4-R1 / 3.9.4-R2 / 3.9.5）
ssot      .ai/project_status.json（单一事实来源）
roadmap   .ai/roadmap_v8.md
baseline  治理发布基线 + Audit 类目 Ledger（JSON SSOT）
manifest  RC 冻结清单 + RC 规格

对每个产物核验
--------------
* tracked        —— `git ls-files` 可见（已进入索引 / 版本历史）；
* committed      —— 能定位到最后一次修改它的真实 commit（`git log -1`）；
* clean          —— 工作树内容与 HEAD 一致（无未提交改动）。

以及全局
--------
* working_tree_clean —— `git status --porcelain` 为空；
* git_head           —— 当前 HEAD 完整 SHA + 分支 + subject。

fail-closed：任一产物缺失 / 未跟踪 / 无提交 / 脏，或工作树不清洁 → 退出码 1。
本脚本**不**提交、不修改任何文件，也不代表任何人工签署。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# 治理常量：收口产物清单（人工可审计）
# ---------------------------------------------------------------------------

#: category -> 相对仓库根的产物路径元组。
CLOSURE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "report": (
        ".ai/reviews/phase3.9.2_release_candidate_freeze_activation_gate_closure_report.md",
        ".ai/reviews/phase3.9.4_r1_final_evidence_quality_closure_report.md",
        ".ai/reviews/phase3.9.4_r2_definitive_baseline_freeze_report.md",
        ".ai/reviews/phase3.9.5_release_line_reconciliation_closure_report.md",
    ),
    "ssot": (".ai/project_status.json",),
    "roadmap": (".ai/roadmap_v8.md",),
    "baseline": (
        ".ai/baselines/phase3.8_governance_release_baseline.json",
        ".ai/baselines/audit_action_category_ledger.json",
    ),
    "manifest": (
        ".ai/release-gate/rc-freeze-manifest.3.9.2.json",
        ".ai/release-gate/rc-spec.3.9.2.json",
    ),
    "boundary_ledger": (".ai/PHASE_BOUNDARY_LEDGER.md",),
}


# ---------------------------------------------------------------------------
# Git 只读工具
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> tuple[int, str]:
    """执行只读 git 命令，返回 (returncode, stdout.strip())。"""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境异常
        return 1, f"<git invocation failed: {exc}>"
    return completed.returncode, completed.stdout.strip()


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass
class ArtifactCommitRecord:
    """单个收口产物的版本历史证据。"""

    category: str
    path: str
    exists: bool
    tracked: bool
    committed: bool
    clean: bool
    last_commit: str | None = None
    last_commit_subject: str | None = None

    @property
    def ok(self) -> bool:
        return self.exists and self.tracked and self.committed and self.clean

    @property
    def failure_reason(self) -> str | None:
        if not self.exists:
            return "file missing from working tree"
        if not self.tracked:
            return "NOT tracked by git (never committed)"
        if not self.committed:
            return "no commit found touching this path"
        if not self.clean:
            return "uncommitted modification vs HEAD"
        return None


@dataclass
class ClosureCommitIntegrityResult:
    """T2 要求的结构化结果对象。

    五个 ``*_tracked`` 布尔字段按 category 聚合（该类全部产物 ok 才为 True），
    另附 ``artifacts`` 明细供收口报告逐条引用。
    """

    git_head: str
    git_head_short: str
    git_branch: str
    git_head_subject: str
    working_tree_clean: bool
    report_tracked: bool
    ssot_tracked: bool
    roadmap_tracked: bool
    baseline_tracked: bool
    manifest_tracked: bool
    boundary_ledger_tracked: bool
    artifacts: list[ArtifactCommitRecord] = field(default_factory=list)
    dirty_entries: list[str] = field(default_factory=list)

    @property
    def all_tracked(self) -> bool:
        return all(
            (
                self.report_tracked,
                self.ssot_tracked,
                self.roadmap_tracked,
                self.baseline_tracked,
                self.manifest_tracked,
                self.boundary_ledger_tracked,
            )
        )

    @property
    def ok(self) -> bool:
        return self.all_tracked and self.working_tree_clean

    def to_json(self) -> str:
        payload = {
            "artifact": "ClosureCommitIntegrityResult",
            "git_head": self.git_head,
            "git_head_short": self.git_head_short,
            "git_branch": self.git_branch,
            "git_head_subject": self.git_head_subject,
            "working_tree_clean": self.working_tree_clean,
            "report_tracked": self.report_tracked,
            "ssot_tracked": self.ssot_tracked,
            "roadmap_tracked": self.roadmap_tracked,
            "baseline_tracked": self.baseline_tracked,
            "manifest_tracked": self.manifest_tracked,
            "boundary_ledger_tracked": self.boundary_ledger_tracked,
            "all_tracked": self.all_tracked,
            "ok": self.ok,
            "dirty_entries": self.dirty_entries,
            "artifacts": [asdict(a) for a in self.artifacts],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def render(self) -> str:
        lines = ["ClosureCommitIntegrityResult（收口产物版本历史核验，只读 / fail-closed）", ""]
        lines.append(f"git_head            : {self.git_head}")
        lines.append(f"git_branch          : {self.git_branch}")
        lines.append(f"git_head_subject    : {self.git_head_subject}")
        lines.append(f"working_tree_clean  : {self.working_tree_clean}")
        if self.dirty_entries:
            for entry in self.dirty_entries:
                lines.append(f"    dirty> {entry}")
        lines.append("")
        for flag_name in (
            "report_tracked",
            "ssot_tracked",
            "roadmap_tracked",
            "baseline_tracked",
            "manifest_tracked",
            "boundary_ledger_tracked",
        ):
            value = getattr(self, flag_name)
            lines.append(f"{'[ok]  ' if value else '[FAIL]'} {flag_name} = {value}")
        lines.append("")
        lines.append("产物明细：")
        for record in self.artifacts:
            marker = "[ok]  " if record.ok else "[FAIL]"
            commit = record.last_commit[:7] if record.last_commit else "-------"
            subject = record.last_commit_subject or ""
            if len(subject) > 62:
                subject = subject[:59] + "..."
            lines.append(f"  {marker} {commit}  {record.path}")
            if subject:
                lines.append(f"           └ {subject}")
            reason = record.failure_reason
            if reason:
                lines.append(f"           └ REASON: {reason}")
        lines.append("")
        if self.ok:
            lines.append(
                "[PASS] 全部收口产物已进入真实版本历史，且工作树清洁。"
            )
        else:
            lines.append(
                "[FAIL] 存在未进入真实版本历史的收口产物或未提交改动（fail-closed）。"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 检查主体
# ---------------------------------------------------------------------------


def _inspect_artifact(root: Path, category: str, rel_path: str) -> ArtifactCommitRecord:
    absolute = root / rel_path
    exists = absolute.is_file()

    code, tracked_out = _git(root, "ls-files", "--error-unmatch", "--", rel_path)
    tracked = code == 0 and bool(tracked_out)

    last_commit: str | None = None
    last_subject: str | None = None
    if tracked:
        code, out = _git(root, "log", "-1", "--format=%H%x1f%s", "--", rel_path)
        if code == 0 and out:
            parts = out.split("\x1f", 1)
            last_commit = parts[0].strip() or None
            last_subject = parts[1].strip() if len(parts) > 1 else None
    committed = last_commit is not None

    # clean：该路径相对 HEAD 无差异（同时覆盖已暂存与未暂存改动）
    clean = False
    if tracked:
        code, out = _git(root, "status", "--porcelain", "--", rel_path)
        clean = code == 0 and not out.strip()

    return ArtifactCommitRecord(
        category=category,
        path=rel_path,
        exists=exists,
        tracked=tracked,
        committed=committed,
        clean=clean,
        last_commit=last_commit,
        last_commit_subject=last_subject,
    )


def check_closure_commit_integrity(root: Path) -> ClosureCommitIntegrityResult:
    _, head_full = _git(root, "rev-parse", "HEAD")
    _, head_short = _git(root, "rev-parse", "--short", "HEAD")
    _, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _, head_subject = _git(root, "log", "-1", "--format=%s")

    code, status_out = _git(root, "status", "--porcelain")
    dirty_entries = [line for line in status_out.splitlines() if line.strip()]
    working_tree_clean = code == 0 and not dirty_entries

    artifacts: list[ArtifactCommitRecord] = []
    for category, paths in CLOSURE_ARTIFACTS.items():
        for rel_path in paths:
            artifacts.append(_inspect_artifact(root, category, rel_path))

    def _category_ok(category: str) -> bool:
        records = [a for a in artifacts if a.category == category]
        return bool(records) and all(a.ok for a in records)

    return ClosureCommitIntegrityResult(
        git_head=head_full,
        git_head_short=head_short,
        git_branch=branch,
        git_head_subject=head_subject,
        working_tree_clean=working_tree_clean,
        report_tracked=_category_ok("report"),
        ssot_tracked=_category_ok("ssot"),
        roadmap_tracked=_category_ok("roadmap"),
        baseline_tracked=_category_ok("baseline"),
        manifest_tracked=_category_ok("manifest"),
        boundary_ledger_tracked=_category_ok("boundary_ledger"),
        artifacts=artifacts,
        dirty_entries=dirty_entries,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify every closure artifact entered real Git history (read-only)."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="BOIP repository root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit ClosureCommitIntegrityResult as JSON instead of a human report.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Do not fail on an unclean working tree (still reported). Use only while "
            "a phase is mid-flight; CI must run WITHOUT this flag."
        ),
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    result = check_closure_commit_integrity(root)

    if args.json:
        print(result.to_json())
    else:
        print(result.render())

    if args.allow_dirty:
        return 0 if result.all_tracked else 1
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
