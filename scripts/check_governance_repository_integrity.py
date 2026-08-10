#!/usr/bin/env python3
"""治理仓库完整性检查器（Phase 3.8.31 Task 9）。

本脚本是**只读**门禁：它只读取仓库与基线清单，不写、不删、不改任何文件。

它要解决的问题，来自本阶段 Reality Scan 查出的两类真实事故：

1. **阶段"人间蒸发"**
   Phase 3.8.27 / 3.8.28 / 3.8.29 三个阶段代码与收口报告都已提交进历史，
   但 ``.ai/project_status.json``（SSOT）里**一条登记都没有**。SSOT 于是
   声称仓库停在 3.8.26，实际 HEAD 已经在 3.8.29。这不是笔误——是没有任何
   机制去核对"提交了的阶段"和"登记了的阶段"是否一致。同样的缺口还漏掉了
   3.8.10 ~ 3.8.16 共 7 个阶段。

2. **总数断言脆性导致的长期红灯**
   审计枚举 ``AuditActionCategory`` 的总数被硬编码断言散落在十几个层的测试
   里。3.8.30 新增三类后，``backend/tests/test_governance_persistence_workflow.py``
   里那句 ``== 69`` 就此长期为红，并被 3.8.29 收口报告以"继承债"记录在案。
   一个全局事实被复制成十几份，任何一次演进都必然打破其中若干份。

因此本检查器守九条不变量。每条都对应上面某个已经真实发生过的失效：

1. **基线清单可解析** —— 清单本身就是本检查器的事实来源，先自证。
2. **阶段登记完整性** —— 每个有收口报告的 3.8.x 阶段，SSOT 必须有状态登记。
3. **报告路径有效性** —— SSOT 声称的 ``report`` 文件必须真实存在（防幽灵登记）。
4. **审计总数断言唯一** —— 全仓只允许一处断言枚举总数，且必须在清单指定的权威文件里。
5. **审计总数与基线一致** —— 实际枚举数必须等于基线声明值（新增须显式改基线）。
6. **必需审计族齐备** —— 基线声明的关键审计大类必须都在。
7. **最高红线①：``engineering_enabled`` 为 false**。
8. **最高红线②：源码不得正向产出 ``engineering_approved``**。
9. **阶段编号唯一** —— 一个编号不得对应两个互相冲突的层名。

用法（被 CI 与 local_ci.sh 调用）::

    python scripts/check_governance_repository_integrity.py --root <PROJECT_ROOT>

退出码 0 = 通过；1 = 发现完整性缺口。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DEFAULT_BASELINE = ".ai/baselines/phase3.8_governance_release_baseline.json"

#: 一律跳过的目录（构建产物、依赖、缓存、虚拟环境）。
SKIP_DIR_PARTS: tuple[str, ...] = (
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
    ".next",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
)


# --------------------------------------------------------------------------- #
# 通用工具                                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class Violation:
    """一处完整性缺口。``location`` 尽量给到 ``文件:行号``，便于直接跳转。"""

    location: str
    detail: str
    remedy: str = ""

    def render(self) -> str:
        text = f"  - {self.location}\n      {self.detail}"
        if self.remedy:
            text += f"\n      修复：{self.remedy}"
        return text


@dataclass
class Context:
    """各规则共享的只读上下文，避免重复 IO。"""

    root: Path
    baseline: dict = field(default_factory=dict)
    ssot: dict = field(default_factory=dict)
    baseline_error: str = ""
    ssot_error: str = ""


def _iter_py_files(root: Path):
    """遍历仓库内的 Python 源码，产出 ``(相对 posix 路径, 绝对路径)``。"""
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if any(f"/{part}/" in f"/{rel}" for part in SKIP_DIR_PARTS):
            continue
        yield rel, path


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


# --------------------------------------------------------------------------- #
# 规则 1：基线清单可解析                                                         #
# --------------------------------------------------------------------------- #


def rule_baseline_parsable(ctx: Context) -> list[Violation]:
    if ctx.baseline_error:
        return [
            Violation(
                DEFAULT_BASELINE,
                f"基线清单无法读取或解析：{ctx.baseline_error}",
                "基线清单是本检查器的唯一事实来源，缺失即无法判定任何不变量。",
            )
        ]
    required = ("audit_category_contract", "phase_registry", "ssot")
    missing = [k for k in required if k not in ctx.baseline]
    if missing:
        return [
            Violation(
                DEFAULT_BASELINE,
                f"基线清单缺少必需字段：{', '.join(missing)}",
                "补齐字段后重跑。",
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# 规则 2：阶段登记完整性（收口报告 ⇒ SSOT 状态键）                                #
# --------------------------------------------------------------------------- #

_REPORT_RE = re.compile(r"^phase3\.8\.(\d+)[_.]")


def rule_phase_registration_complete(ctx: Context) -> list[Violation]:
    if ctx.ssot_error or not ctx.baseline:
        return []
    reviews = ctx.root / ".ai" / "reviews"
    if not reviews.is_dir():
        return []

    overrides: dict[str, str] = ctx.baseline.get("ssot", {}).get(
        "phase_key_overrides", {}
    )
    numbers: dict[int, list[str]] = {}
    for report in sorted(reviews.glob("phase3.8*")):
        match = _REPORT_RE.match(report.name)
        if match:
            numbers.setdefault(int(match.group(1)), []).append(report.name)

    violations: list[Violation] = []
    for number in sorted(numbers):
        key = overrides.get(str(number), f"phase_3_8_{number}_status")
        if key not in ctx.ssot:
            reports = "、".join(numbers[number])
            violations.append(
                Violation(
                    f".ai/project_status.json（缺 {key}）",
                    f"Phase 3.8.{number} 已有收口报告（{reports}），但 SSOT 无状态登记。",
                    "在 project_status.json 补登该阶段状态；不得重编号已占用的阶段。",
                )
            )
    return violations


# --------------------------------------------------------------------------- #
# 规则 3：SSOT 声明的报告路径必须存在                                            #
# --------------------------------------------------------------------------- #


def rule_ssot_report_paths_exist(ctx: Context) -> list[Violation]:
    if ctx.ssot_error:
        return []
    violations: list[Violation] = []
    for key, value in ctx.ssot.items():
        if not isinstance(value, dict):
            continue
        report = value.get("report")
        if isinstance(report, str) and report and not (ctx.root / report).exists():
            violations.append(
                Violation(
                    f".ai/project_status.json → {key}.report",
                    f"SSOT 声称存在报告 {report}，但该文件不存在（幽灵登记）。",
                    "补齐报告文件，或修正 SSOT 中的路径——不得让 SSOT 描述不存在的事实。",
                )
            )
    return violations


# --------------------------------------------------------------------------- #
# 规则 4：审计枚举总数断言全仓唯一                                               #
# --------------------------------------------------------------------------- #

_TOTAL_ASSERT_RE = re.compile(r"^\s*assert\s+len\((?P<arg>.+?)\)\s*==\s*(?P<n>\d+)")

#: ``len(...)`` 的参数必须**整体**指向枚举本身，才算"总数断言"。
#:
#: 这条收得很紧是有原因的：``assert len(audit.query(category=AuditActionCategory.X)) == 2``
#: 这类断言在各层测试里大量存在，它数的是**审计事件条数**，是该层完全正当的行为契约，
#: 跟枚举总数毫无关系。若只按"这一行提到了 AuditActionCategory"就判违规，会把十几处
#: 正确的测试误判成缺口——门禁一旦制造噪音，就会被整体忽略。
_ENUM_TOTAL_ARG_RE = re.compile(
    r"^(?:"
    r"members"
    r"|(?:list|set|tuple)\(AuditActionCategory(?:\.__members__"
    r"(?:\.(?:values|keys|items)\(\))?)?\)"
    r"|AuditActionCategory(?:\.__members__(?:\.(?:values|keys|items)\(\))?)?"
    r")$"
)

_MEMBERS_BINDING_RE = re.compile(r"^\s*members\s*(?::[^=]+)?=.*AuditActionCategory")

#: 任意局部变量名 = <枚举全集表达式>，例如 ``cats = {c.value for c in AuditActionCategory}``。
#:
#: Phase 3.8.31 Task 11（红线复核）补强：规则 4 原先只认 ``members`` 这一个裸变量名，
#: 于是 ``cats = {c.value for c in AuditActionCategory}`` + ``assert len(cats) == 72``
#: 整条从门禁下溜走了——真有一处这样的漏网断言活到了红线复核阶段。别名叫什么无关紧要，
#: 只要它绑定的是枚举**全集**，对它取 len 就是在断言总数。故改为：先在文件内解析出所有
#: 「枚举全集别名」，再连同白名单一起判定。
_ENUM_ALIAS_BINDING_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_]\w*)\s*(?::[^=]+)?=\s*(?P<rhs>.+)$"
)

#: 右值必须是**遍历/构造整个枚举**，才认定为全集别名。
#: 命中：``{c.value for c in AuditActionCategory}``、``list(AuditActionCategory)``、
#:       ``AuditActionCategory.__members__``。
#: 不命中：``AuditActionCategory.GOVERNANCE_TRACE``（单成员）、
#:         ``audit.query(category=AuditActionCategory.X)``（查审计条数，是正当契约）。
_ENUM_ALIAS_RHS_RE = re.compile(
    r"(?:for\s+\w+\s+in\s+AuditActionCategory\s*[\}\)\]\s]"
    r"|(?:list|set|tuple|frozenset|sorted)\(\s*AuditActionCategory\s*[\),]"
    r"|AuditActionCategory\.__members__)"
)


def _enum_full_set_aliases(lines: list[str]) -> set[str]:
    """解析出本文件中所有指向"枚举全集"的局部别名。"""
    aliases: set[str] = set()
    for line in lines:
        match = _ENUM_ALIAS_BINDING_RE.match(line)
        if not match:
            continue
        if _ENUM_ALIAS_RHS_RE.search(match.group("rhs")):
            aliases.add(match.group("name"))
    return aliases


def _find_total_assertions(root: Path) -> list[tuple[str, int, int]]:
    """找出所有"断言审计枚举总数"的位置，返回 ``(相对路径, 行号, 断言值)``。"""
    hits: list[tuple[str, int, int]] = []
    for rel, path in _iter_py_files(root):
        lines = _lines(path)
        if not any("AuditActionCategory" in line for line in lines):
            continue
        # 裸变量 ``members`` 只有在本文件确实由枚举赋值时才算数。
        members_is_enum = any(_MEMBERS_BINDING_RE.match(line) for line in lines)
        aliases = _enum_full_set_aliases(lines)
        for index, line in enumerate(lines, start=1):
            match = _TOTAL_ASSERT_RE.match(line)
            if not match:
                continue
            arg = re.sub(r"\s+", "", match.group("arg"))
            is_whitelisted = bool(_ENUM_TOTAL_ARG_RE.match(arg))
            if not is_whitelisted and arg not in aliases:
                continue
            if arg == "members" and not members_is_enum and arg not in aliases:
                continue
            hits.append((rel, index, int(match.group("n"))))
    return hits


def rule_total_assertion_is_unique(ctx: Context) -> list[Violation]:
    if not ctx.baseline:
        return []
    contract = ctx.baseline.get("audit_category_contract", {})
    authority = contract.get("authority_file", "")
    hits = _find_total_assertions(ctx.root)

    violations: list[Violation] = []
    stray = [h for h in hits if h[0] != authority]
    for rel, line_no, value in stray:
        violations.append(
            Violation(
                f"{rel}:{line_no}",
                f"在非权威文件中硬编码审计枚举总数（== {value}）。",
                "改为存在性契约（如 {\"A\", \"B\"} <= set(AuditActionCategory.__members__)）；"
                f"总数权威只保留在 {authority}。",
            )
        )
    if authority and not any(h[0] == authority for h in hits):
        violations.append(
            Violation(
                authority,
                "基线指定的权威文件里找不到审计枚举总数断言——总数已失去唯一守护者。",
                "在权威文件中恢复 assert len(members) == <总数>。",
            )
        )
    return violations


# --------------------------------------------------------------------------- #
# 规则 5 / 6：审计枚举总数与必需族                                               #
# --------------------------------------------------------------------------- #


def _load_audit_members(root: Path) -> tuple[set[str], str]:
    """导入 ``AuditActionCategory`` 并返回成员名集合；失败时返回错误说明。"""
    root_str = str(root)
    inserted = root_str not in sys.path
    if inserted:
        sys.path.insert(0, root_str)
    try:
        from agents.enterprise.audit import AuditActionCategory  # noqa: PLC0415

        return set(AuditActionCategory.__members__), ""
    except Exception as exc:  # pragma: no cover - 环境异常
        return set(), f"{type(exc).__name__}: {exc}"
    finally:
        if inserted and root_str in sys.path:
            sys.path.remove(root_str)


def rule_audit_total_matches_baseline(ctx: Context) -> list[Violation]:
    if not ctx.baseline:
        return []
    contract = ctx.baseline.get("audit_category_contract", {})
    expected = contract.get("total")
    if not isinstance(expected, int):
        return []
    members, error = _load_audit_members(ctx.root)
    if error:
        return [
            Violation(
                "agents/enterprise/audit.py",
                f"无法导入 AuditActionCategory：{error}",
                "先修复导入错误，完整性无法在不可导入的代码上判定。",
            )
        ]
    if len(members) != expected:
        return [
            Violation(
                "agents/enterprise/audit.py",
                f"审计枚举实际 {len(members)} 类，基线声明 {expected} 类。",
                f"若为有意新增，请同步更新 {DEFAULT_BASELINE} 与权威测试——"
                "基线变更必须是显式动作，不允许悄悄漂移。",
            )
        ]
    return []


def rule_required_audit_families(ctx: Context) -> list[Violation]:
    if not ctx.baseline:
        return []
    contract = ctx.baseline.get("audit_category_contract", {})
    required: dict[str, list[str]] = contract.get("required_families", {})
    if not required:
        return []
    members, error = _load_audit_members(ctx.root)
    if error:
        return []
    violations: list[Violation] = []
    for family, names in required.items():
        missing = [n for n in names if n not in members]
        if missing:
            violations.append(
                Violation(
                    f"agents/enterprise/audit.py（族 {family}）",
                    f"基线要求的审计大类缺失：{', '.join(missing)}。",
                    "治理语义缺类等于该链路无法留痕，必须补齐。",
                )
            )
    return violations


# --------------------------------------------------------------------------- #
# 规则 7 / 8：最高红线复核                                                       #
# --------------------------------------------------------------------------- #

_ENGINEERING_ENABLED_RE = re.compile(
    r"^\s*engineering_enabled\s*:\s*(?P<value>\S+)", re.MULTILINE
)


def rule_engineering_flag_false(ctx: Context) -> list[Violation]:
    config = ctx.root / "agents" / "config.yaml"
    if not config.exists():
        return [
            Violation(
                "agents/config.yaml",
                "配置文件不存在，无法确认最高红线①（engineering_enabled 必须为 false）。",
                "恢复配置文件。",
            )
        ]
    text = config.read_text(encoding="utf-8")
    violations: list[Violation] = []
    for match in _ENGINEERING_ENABLED_RE.finditer(text):
        value = match.group("value").strip().rstrip(",").lower()
        if value not in ("false", "no", "off"):
            line_no = text[: match.start()].count("\n") + 1
            violations.append(
                Violation(
                    f"agents/config.yaml:{line_no}",
                    f"engineering_enabled = {value}，违反最高红线①。",
                    "该开关只能由主理人在人类终端显式开启，任何提交置 true 都必须被拦下。",
                )
            )
    return violations


_APPROVED_EMIT_RE = re.compile(
    r"(?:def\s+engineering_approved\b"
    r"|^\s*engineering_approved\s*(?::[^=]+)?=\s*"
    r"|[\"']engineering_approved[\"']\s*:)"
)


def rule_no_engineering_approved_emission(ctx: Context) -> list[Violation]:
    violations: list[Violation] = []
    for subdir in ("agents", "backend/app"):
        base = ctx.root / subdir
        if not base.is_dir():
            continue
        for rel, path in _iter_py_files(base):
            full_rel = f"{subdir}/{rel}"
            if "forbidden" in rel or "/tests/" in f"/{rel}" or rel.startswith("tests/"):
                continue
            for index, line in enumerate(_lines(path), start=1):
                if _APPROVED_EMIT_RE.search(line):
                    violations.append(
                        Violation(
                            f"{full_rel}:{index}",
                            "源码正向产出 engineering_approved，违反最高红线②。",
                            "该字段只允许以负向声明（禁语清单）形式出现，永不作为输出。",
                        )
                    )
    return violations


# --------------------------------------------------------------------------- #
# 规则 9：阶段编号唯一                                                           #
# --------------------------------------------------------------------------- #

_STATUS_KEY_RE = re.compile(r"^phase_3_8_(\d+)_status$")


def rule_phase_numbering_unique(ctx: Context) -> list[Violation]:
    if ctx.ssot_error or not ctx.baseline:
        return []
    registry = {
        str(entry.get("phase")): entry
        for entry in ctx.baseline.get("phase_registry", [])
        if isinstance(entry, dict)
    }
    violations: list[Violation] = []
    for key, value in ctx.ssot.items():
        match = _STATUS_KEY_RE.match(key)
        if not match or not isinstance(value, str):
            continue
        phase = f"3.8.{match.group(1)}"
        entry = registry.get(phase)
        if entry is None:
            continue
        expected = entry.get("status")
        if expected and expected != value:
            violations.append(
                Violation(
                    f".ai/project_status.json → {key}",
                    f"编号 {phase} 的状态与基线登记冲突："
                    f"SSOT = {value}；基线 = {expected}。",
                    "同一编号不得对应两个互相冲突的层；请核对主理人裁决后统一，"
                    "不得重编号已占用的阶段。",
                )
            )
    return violations


# --------------------------------------------------------------------------- #
# 驱动                                                                          #
# --------------------------------------------------------------------------- #

RULES: tuple[tuple[str, Callable[[Context], list[Violation]]], ...] = (
    ("基线清单可解析", rule_baseline_parsable),
    ("阶段登记完整（报告 ⇒ SSOT）", rule_phase_registration_complete),
    ("SSOT 报告路径真实存在", rule_ssot_report_paths_exist),
    ("审计总数断言全仓唯一", rule_total_assertion_is_unique),
    ("审计总数与基线一致", rule_audit_total_matches_baseline),
    ("必需审计族齐备", rule_required_audit_families),
    ("红线①engineering_enabled=false", rule_engineering_flag_false),
    ("红线②不产出 engineering_approved", rule_no_engineering_approved_emission),
    ("阶段编号唯一无冲突", rule_phase_numbering_unique),
)


def _build_context(root: Path, baseline_path: Path) -> Context:
    ctx = Context(root=root)
    try:
        ctx.baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.baseline_error = str(exc)
    try:
        ctx.ssot = json.loads(
            (root / ".ai" / "project_status.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        ctx.ssot_error = str(exc)
    return ctx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="治理仓库完整性检查（只读）")
    parser.add_argument("--root", default=".", help="项目根目录")
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE,
        help=f"发布基线清单路径（默认 {DEFAULT_BASELINE}）",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path

    ctx = _build_context(root, baseline_path)

    print("治理仓库完整性检查（Phase 3.8.31 Task 9，只读）")
    all_violations: list[Violation] = []
    for name, rule in RULES:
        found = rule(ctx)
        status = "FAIL" if found else "ok"
        print(f"  [{status:>4}] {name}（{len(found)} 处）")
        all_violations.extend(found)

    if ctx.ssot_error:
        print(f"\n警告：SSOT 读取失败（{ctx.ssot_error}），相关规则已跳过。")

    if not all_violations:
        print("治理仓库完整性检查通过。")
        return 0

    print("\n发现治理仓库完整性缺口：")
    for violation in all_violations:
        print(violation.render())
    print(
        f"\n共 {len(all_violations)} 处缺口。本检查器只读，不会替你修改任何文件——"
        "SSOT 与仓库事实必须由人确认后手工对齐。"
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())
