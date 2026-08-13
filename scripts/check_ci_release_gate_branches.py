#!/usr/bin/env python3
"""CI Release Gate 分支覆盖门禁（Phase 3.9.6 T1，只读 / fail-closed）。

背景
----
BOIP 的生产发布闸门（.github/workflows/release-gate.yml）曾只监听
``feat/phase3.9.2-production-release-gate`` 与尚不存在的 ``main``。但自 Phase 3.9.5
起，真实的 RC 冻结基线由 ``feat/phase3.9.5-release-line-reconciliation`` 承载，
Phase 3.9.4-R2 之后的治理层增量落在 ``feat/phase3.9.4-r2-definitive-baseline-freeze``。
结果是：**真实集成载体上的推送根本不触发发布闸门** —— 门禁形同虚设。

本脚本把"发布闸门必须覆盖真实集成分支"这一治理约束变成机器可读、可在 CI 中
fail-closed 执行的检查，防止同类漂移复发。

检查项
------
R1  release-gate.yml 存在且可解析出 on.push.branches 列表；
R2  显式保留长期主干 ``main``（占位，未来落主干时不漏跑）；
R3  所有"真实集成载体分支"（REQUIRED_COVERED_BRANCHES）均被某个 pattern 覆盖；
R4  当前 Git 分支（若可探测）被覆盖 —— 这是最贴近现实的一条；
R5  存在后续 release integration 通配策略（至少一个含 ``*`` 的 pattern），
    保证下一个阶段新建集成分支时门禁自动生效；
R6  历史发布闸门分支仍被覆盖（不破坏既有 CI 契约）；
R7  三个既有 job 仍存在（integrity / rc-freeze-gate / tests），即"不得破坏现有 CI"；
R8  pull_request 触发未被收窄为分支白名单（保持覆盖所有 PR）。

设计约束
--------
* 纯标准库（与 scripts/check_governance_repository_integrity.py 一致），CI 中无需
  安装 PyYAML 即可运行；
* 只读：不修改任何文件、不触碰 Git 状态；
* fail-closed：任一规则失败 → 退出码 1。

本脚本**不**部署、不激活、不宣布 GO，也不代表任何人工签署。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# 治理常量：真实集成载体（人工可审计，不由 AI 静默扩张）
# ---------------------------------------------------------------------------

RELEASE_GATE_WORKFLOW = ".github/workflows/release-gate.yml"

#: 长期主干（当前仓库尚未创建，占位保留）。
TRUNK_BRANCH = "main"

#: 必须被发布闸门覆盖的真实集成载体分支。
#: 顺序即治理语义顺序：RC 冻结载体 → 基线冻结/治理层载体 → 历史发布闸门分支。
REQUIRED_COVERED_BRANCHES: tuple[str, ...] = (
    "feat/phase3.9.5-release-line-reconciliation",
    "feat/phase3.9.4-r2-definitive-baseline-freeze",
    "feat/phase3.9.2-production-release-gate",
)

#: 历史分支（R6）：即便不再是最终集成载体，也不得从门禁中移除。
LEGACY_BRANCHES: tuple[str, ...] = ("feat/phase3.9.2-production-release-gate",)

#: 既有 job（R7）：Phase 3.9.2 建立的三道发布闸门 job，不得删除。
REQUIRED_JOBS: tuple[str, ...] = (
    "release-gate-integrity",
    "rc-freeze-gate",
    "release-gate-tests",
)


# ---------------------------------------------------------------------------
# GitHub Actions 分支 pattern 匹配（* 不跨 /，** 跨 /）
# ---------------------------------------------------------------------------


def branch_pattern_matches(pattern: str, branch: str) -> bool:
    """判断 GitHub Actions 分支过滤 pattern 是否匹配给定分支名。

    语义参考 GitHub 文档（filter pattern cheat sheet）：

    * ``*``  匹配零个或多个字符，但**不跨越** ``/``；
    * ``**`` 匹配零个或多个字符，**可跨越** ``/``；
    * ``?``  匹配单个字符（不跨 ``/``）；
    * 其余字符按字面量处理。

    这里只实现 BOIP 实际使用到的子集，且不支持 ``!`` 取反（若出现取反 pattern，
    调用方应视为不可静态判定并显式失败，而非默默放行）。
    """
    if pattern.startswith("!"):
        raise ValueError(f"negated branch pattern is not supported: {pattern!r}")

    regex_parts: list[str] = ["^"]
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if index + 1 < length and pattern[index + 1] == "*":
                regex_parts.append(".*")
                index += 2
                continue
            regex_parts.append("[^/]*")
            index += 1
            continue
        if char == "?":
            regex_parts.append("[^/]")
            index += 1
            continue
        regex_parts.append(re.escape(char))
        index += 1
    regex_parts.append("$")
    return re.match("".join(regex_parts), branch) is not None


def covering_patterns(patterns: Iterable[str], branch: str) -> list[str]:
    """返回覆盖 ``branch`` 的所有 pattern（可能为空）。"""
    return [p for p in patterns if branch_pattern_matches(p, branch)]


# ---------------------------------------------------------------------------
# 极简 YAML 片段解析（纯标准库，只解析本脚本需要的结构）
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """去掉行尾注释。仅处理未被引号包裹的 ``#``（本工作流不含带 # 的分支名）。"""
    in_single = False
    in_double = False
    for position, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:position]
    return line


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


@dataclass
class ReleaseGateWorkflow:
    """release-gate.yml 的最小结构化视图。"""

    path: Path
    push_branches: list[str] = field(default_factory=list)
    pull_request_present: bool = False
    pull_request_branches: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)


def parse_release_gate_workflow(path: Path) -> ReleaseGateWorkflow:
    """解析工作流中的 on.push.branches / on.pull_request / jobs 顶层键。

    采用缩进敏感的行扫描，不引入第三方依赖。解析失败时返回的字段为空，
    由调用方的规则判定为 FAIL（fail-closed，绝不"解析不出来就当通过"）。
    """
    workflow = ReleaseGateWorkflow(path=path)
    if not path.is_file():
        return workflow

    raw_lines = path.read_text(encoding="utf-8").splitlines()

    section: str | None = None  # None | "on" | "jobs"
    on_subsection: str | None = None  # None | "push" | "pull_request"
    list_owner: str | None = None  # None | "push.branches" | "pull_request.branches"

    for raw in raw_lines:
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue

        indent = _indent_of(line)
        stripped = line.strip()

        # 顶层键（缩进 0）
        if indent == 0 and not stripped.startswith("- "):
            key = stripped.split(":", 1)[0].strip()
            section = key if key in {"on", "jobs"} else None
            on_subsection = None
            list_owner = None
            continue

        if section == "on":
            # on 下的二级键（push: / pull_request: / workflow_dispatch: ...）
            if indent == 2 and not stripped.startswith("- "):
                key = stripped.split(":", 1)[0].strip()
                on_subsection = key
                list_owner = None
                if key == "pull_request":
                    workflow.pull_request_present = True
                continue
            # push/pull_request 下的 branches: 键
            if indent == 4 and not stripped.startswith("- "):
                key = stripped.split(":", 1)[0].strip()
                if key in {"branches", "branches-ignore"} and on_subsection in {
                    "push",
                    "pull_request",
                }:
                    list_owner = f"{on_subsection}.{key}"
                else:
                    list_owner = None
                continue
            # 列表项
            if stripped.startswith("- ") and list_owner:
                value = _unquote(stripped[2:])
                if not value:
                    continue
                if list_owner == "push.branches":
                    workflow.push_branches.append(value)
                elif list_owner == "pull_request.branches":
                    workflow.pull_request_branches.append(value)
                continue
            continue

        if section == "jobs":
            # jobs 下的二级键即 job 名
            if indent == 2 and not stripped.startswith("- ") and stripped.endswith(":"):
                workflow.jobs.append(stripped[:-1].strip())
            continue

    return workflow


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass
class RuleResult:
    rule: str
    passed: bool
    detail: str


@dataclass
class BranchAlignmentResult:
    """CI Release Gate 分支覆盖检查结果（可序列化为报告证据）。"""

    workflow_path: str
    push_branches: list[str]
    current_git_branch: str | None
    rules: list[RuleResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(rule.passed for rule in self.rules)

    def render(self) -> str:
        lines = ["CI Release Gate 分支覆盖门禁（只读 / fail-closed）", ""]
        lines.append(f"workflow      : {self.workflow_path}")
        lines.append(f"current branch: {self.current_git_branch or '<unknown>'}")
        lines.append(f"push branches : {len(self.push_branches)} pattern(s)")
        for pattern in self.push_branches:
            lines.append(f"  - {pattern}")
        lines.append("")
        for rule in self.rules:
            marker = "[ok]  " if rule.passed else "[FAIL]"
            lines.append(f"{marker} {rule.rule}: {rule.detail}")
        lines.append("")
        if self.ok:
            lines.append("[PASS] Release gate covers every real integration branch.")
        else:
            failed = [r.rule for r in self.rules if not r.passed]
            lines.append(f"[FAIL] {len(failed)} rule(s) failed: {', '.join(failed)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 检查主体
# ---------------------------------------------------------------------------


def detect_current_branch(root: Path) -> str | None:
    """探测当前 Git 分支；探测不到返回 None（CI detached HEAD 场景）。"""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    if not branch or branch == "HEAD":
        return None
    return branch


def check_release_gate_branches(root: Path) -> BranchAlignmentResult:
    workflow_path = root / RELEASE_GATE_WORKFLOW
    workflow = parse_release_gate_workflow(workflow_path)
    current_branch = detect_current_branch(root)

    result = BranchAlignmentResult(
        workflow_path=RELEASE_GATE_WORKFLOW,
        push_branches=list(workflow.push_branches),
        current_git_branch=current_branch,
    )
    patterns = workflow.push_branches

    # R1 工作流可解析
    if not workflow_path.is_file():
        result.rules.append(
            RuleResult("R1_workflow_present", False, f"missing {RELEASE_GATE_WORKFLOW}")
        )
        return result
    result.rules.append(
        RuleResult(
            "R1_workflow_parsed",
            bool(patterns),
            f"parsed {len(patterns)} push branch pattern(s)"
            if patterns
            else "no on.push.branches parsed (fail-closed)",
        )
    )
    if not patterns:
        return result

    # R2 主干占位保留
    result.rules.append(
        RuleResult(
            "R2_trunk_declared",
            TRUNK_BRANCH in patterns,
            f"'{TRUNK_BRANCH}' {'declared' if TRUNK_BRANCH in patterns else 'MISSING'}",
        )
    )

    # R3 真实集成载体全覆盖
    uncovered: list[str] = []
    for branch in REQUIRED_COVERED_BRANCHES:
        if not covering_patterns(patterns, branch):
            uncovered.append(branch)
    result.rules.append(
        RuleResult(
            "R3_real_integration_branches_covered",
            not uncovered,
            "all real integration branches covered"
            if not uncovered
            else f"uncovered: {', '.join(uncovered)}",
        )
    )

    # R4 当前分支被覆盖
    if current_branch is None:
        result.rules.append(
            RuleResult(
                "R4_current_branch_covered",
                True,
                "current branch undetectable (detached HEAD) — skipped",
            )
        )
    else:
        matched = covering_patterns(patterns, current_branch)
        result.rules.append(
            RuleResult(
                "R4_current_branch_covered",
                bool(matched),
                f"'{current_branch}' covered by {matched}"
                if matched
                else f"'{current_branch}' NOT covered by any pattern",
            )
        )

    # R5 后续 release integration 通配策略
    wildcard = [p for p in patterns if "*" in p]
    result.rules.append(
        RuleResult(
            "R5_future_integration_wildcard",
            bool(wildcard),
            f"wildcard strategy present: {wildcard}"
            if wildcard
            else "no wildcard pattern — future integration branches would be missed",
        )
    )

    # R6 历史分支未被移除
    dropped = [b for b in LEGACY_BRANCHES if not covering_patterns(patterns, b)]
    result.rules.append(
        RuleResult(
            "R6_legacy_branches_preserved",
            not dropped,
            "legacy release-gate branches preserved"
            if not dropped
            else f"legacy branch coverage dropped: {', '.join(dropped)}",
        )
    )

    # R7 既有 job 未被破坏
    missing_jobs = [j for j in REQUIRED_JOBS if j not in workflow.jobs]
    result.rules.append(
        RuleResult(
            "R7_existing_jobs_intact",
            not missing_jobs,
            f"jobs present: {', '.join(workflow.jobs)}"
            if not missing_jobs
            else f"missing job(s): {', '.join(missing_jobs)}",
        )
    )

    # R8 pull_request 未被收窄
    pr_ok = workflow.pull_request_present and not workflow.pull_request_branches
    result.rules.append(
        RuleResult(
            "R8_pull_request_not_narrowed",
            pr_ok,
            "pull_request trigger covers all target branches"
            if pr_ok
            else (
                "pull_request trigger missing"
                if not workflow.pull_request_present
                else f"pull_request narrowed to {workflow.pull_request_branches}"
            ),
        )
    )

    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the CI release gate covers every real RC / release integration branch."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="BOIP repository root (default: parent of scripts/).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    result = check_release_gate_branches(root)
    print(result.render())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
