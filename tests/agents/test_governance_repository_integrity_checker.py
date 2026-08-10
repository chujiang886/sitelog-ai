"""检查器自检：``scripts/check_governance_repository_integrity.py``（Phase 3.8.31 Task 9）。

一个永远返回"通过"的门禁比没有门禁更糟——它给出安全的错觉，让人停止检查。
所以这里对九条规则逐条做**双向**验证：正例必须放行，反例必须拦下。

其中两条特别重要：

* ``test_total_assertion_ignores_audit_query_counts`` 守的是**误报回归**。
  检查器第一版把 ``assert len(audit.query(category=...)) == 2`` 也当成"硬编码
  枚举总数"，一次扫出 15 处假阳性。那些断言数的是审计事件条数，是各层完全
  正当的行为契约。门禁一旦制造噪音就会被整体忽略，因此这条必须钉死。

* ``test_engineering_approved_negative_declaration_allowed`` 守的是**红线②的
  表达自由**。禁语清单、docstring 里必然要提到 ``engineering_approved``，
  否则无法声明"禁止它"。规则只能拦正向产出，不能拦负向声明。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CHECKER_PATH = PROJECT_ROOT / "scripts" / "check_governance_repository_integrity.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_governance_repository_integrity", _CHECKER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------- #
# 脚手架                                                                        #
# --------------------------------------------------------------------------- #


def _ctx(root: Path, baseline: dict | None = None, ssot: dict | None = None):
    return checker.Context(
        root=root, baseline=baseline or {}, ssot=ssot if ssot is not None else {}
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 规则 1：基线清单可解析                                                         #
# --------------------------------------------------------------------------- #


def test_baseline_missing_is_rejected(tmp_path: Path) -> None:
    ctx = checker.Context(root=tmp_path, baseline_error="No such file")
    assert checker.rule_baseline_parsable(ctx)


def test_baseline_missing_required_field_is_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, baseline={"audit_category_contract": {}})
    violations = checker.rule_baseline_parsable(ctx)
    assert violations and "phase_registry" in violations[0].detail


def test_baseline_complete_passes(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        baseline={"audit_category_contract": {}, "phase_registry": [], "ssot": {}},
    )
    assert checker.rule_baseline_parsable(ctx) == []


# --------------------------------------------------------------------------- #
# 规则 2：阶段登记完整性                                                         #
# --------------------------------------------------------------------------- #


def test_report_without_ssot_entry_is_rejected(tmp_path: Path) -> None:
    """这正是 3.8.27/28/29 三个阶段在 SSOT 中"人间蒸发"的那类缺口。"""
    _write(tmp_path / ".ai/reviews/phase3.8.42_some_layer_report.md", "# x")
    ctx = _ctx(tmp_path, baseline={"ssot": {}}, ssot={})
    violations = checker.rule_phase_registration_complete(ctx)
    assert len(violations) == 1
    assert "phase_3_8_42_status" in violations[0].location


def test_report_with_ssot_entry_passes(tmp_path: Path) -> None:
    _write(tmp_path / ".ai/reviews/phase3.8.42_some_layer_report.md", "# x")
    ctx = _ctx(tmp_path, baseline={"ssot": {}}, ssot={"phase_3_8_42_status": "BUILT"})
    assert checker.rule_phase_registration_complete(ctx) == []


def test_phase_key_override_is_honoured(tmp_path: Path) -> None:
    """3.8.0 的状态键历史上没有编号后缀，靠基线里的 override 声明兼容。"""
    _write(tmp_path / ".ai/reviews/phase3.8.0_operation_report.md", "# x")
    ctx = _ctx(
        tmp_path,
        baseline={"ssot": {"phase_key_overrides": {"0": "phase_3_8_status"}}},
        ssot={"phase_3_8_status": "BUILT"},
    )
    assert checker.rule_phase_registration_complete(ctx) == []


# --------------------------------------------------------------------------- #
# 规则 3：报告路径有效性                                                         #
# --------------------------------------------------------------------------- #


def test_phantom_report_path_is_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, ssot={"phase_x": {"report": ".ai/reviews/nope.md"}})
    violations = checker.rule_ssot_report_paths_exist(ctx)
    assert violations and "nope.md" in violations[0].detail


def test_existing_report_path_passes(tmp_path: Path) -> None:
    _write(tmp_path / ".ai/reviews/real.md", "# real")
    ctx = _ctx(tmp_path, ssot={"phase_x": {"report": ".ai/reviews/real.md"}})
    assert checker.rule_ssot_report_paths_exist(ctx) == []


# --------------------------------------------------------------------------- #
# 规则 4：审计总数断言唯一                                                       #
# --------------------------------------------------------------------------- #

_BASELINE_AUTH = {
    "audit_category_contract": {"authority_file": "tests/authority.py"},
}


def _authority_file(root: Path) -> None:
    _write(
        root / "tests/authority.py",
        "from x import AuditActionCategory\n"
        "def test_total():\n"
        "    members = list(AuditActionCategory.__members__.values())\n"
        "    assert len(members) == 72\n",
    )


def test_stray_total_assertion_is_rejected(tmp_path: Path) -> None:
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/other_layer.py",
        "from x import AuditActionCategory\n"
        "def test_x():\n"
        "    assert len(list(AuditActionCategory)) == 72\n",
    )
    ctx = _ctx(tmp_path, baseline=_BASELINE_AUTH)
    violations = checker.rule_total_assertion_is_unique(ctx)
    assert len(violations) == 1
    assert "tests/other_layer.py:3" == violations[0].location


def test_single_authority_passes(tmp_path: Path) -> None:
    _authority_file(tmp_path)
    ctx = _ctx(tmp_path, baseline=_BASELINE_AUTH)
    assert checker.rule_total_assertion_is_unique(ctx) == []


def test_missing_authority_assertion_is_rejected(tmp_path: Path) -> None:
    """总数一旦没有任何守护者，下一次演进就会无声漂移。"""
    _write(
        tmp_path / "tests/authority.py",
        "from x import AuditActionCategory\nX = AuditActionCategory\n",
    )
    ctx = _ctx(tmp_path, baseline=_BASELINE_AUTH)
    violations = checker.rule_total_assertion_is_unique(ctx)
    assert violations and "失去唯一守护者" in violations[0].detail


def test_total_assertion_ignores_audit_query_counts(tmp_path: Path) -> None:
    """误报回归守卫：审计事件计数不是枚举总数断言。"""
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/layer.py",
        "from x import AuditActionCategory\n"
        "def test_events(audit):\n"
        "    assert len(audit.query(category=AuditActionCategory.AGENT_RISK)) == 2\n"
        "    assert len(audit.query(category=AuditActionCategory.PERMISSION)) == 1\n",
    )
    assert checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH)) == []


def test_bare_members_only_counts_when_bound_to_enum(tmp_path: Path) -> None:
    """别的模块里恰好也叫 ``members`` 的局部变量，不该被误判成审计枚举。"""
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/unrelated.py",
        "from x import AuditActionCategory  # 只是引用了类型\n"
        "def test_team(team):\n"
        "    members = team.roster()\n"
        "    assert len(members) == 5\n",
    )
    assert checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH)) == []


def test_enum_full_set_alias_total_assertion_is_rejected(tmp_path: Path) -> None:
    """真实漏网回归守卫（Phase 3.8.31 Task 11 红线复核发现）。

    规则 4 初版只认 ``members`` 这一个裸变量名，导致
    ``cats = {c.value for c in AuditActionCategory}`` + ``assert len(cats) == 72``
    这种"换个名字"的总数断言整条溜过门禁——它确实活到了红线复核阶段才被人工抓到。
    门禁抓不住的违规，等于没有门禁；此用例把这个形式钉死。
    """
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/aliased_layer.py",
        "from x import AuditActionCategory\n"
        "def test_x():\n"
        "    cats = {c.value for c in AuditActionCategory}\n"
        "    assert len(cats) == 72\n",
    )
    violations = checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH))
    assert len(violations) == 1
    assert violations[0].location == "tests/aliased_layer.py:4"


@pytest.mark.parametrize(
    "binding",
    [
        "    cats = list(AuditActionCategory)\n",
        "    cats = sorted(AuditActionCategory)\n",
        "    cats = [c for c in AuditActionCategory]\n",
        "    cats = AuditActionCategory.__members__\n",
    ],
)
def test_enum_alias_variants_are_all_caught(tmp_path: Path, binding: str) -> None:
    """全集别名的常见写法都要认得，换个构造方式绕不过去。"""
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/aliased_layer.py",
        "from x import AuditActionCategory\n" "def test_x():\n" + binding + "    assert len(cats) == 72\n",
    )
    violations = checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH))
    assert len(violations) == 1


def test_non_enum_alias_is_not_flagged(tmp_path: Path) -> None:
    """误报守卫：同名变量若不是绑定枚举全集，就与总数无关。"""
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/unrelated_alias.py",
        "from x import AuditActionCategory  # 仅类型引用\n"
        "def test_team(team):\n"
        "    cats = team.categories()\n"
        "    assert len(cats) == 3\n",
    )
    assert checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH)) == []


def test_single_member_reference_is_not_an_alias(tmp_path: Path) -> None:
    """误报守卫：引用单个枚举成员不构成"全集别名"。"""
    _authority_file(tmp_path)
    _write(
        tmp_path / "tests/single_member.py",
        "from x import AuditActionCategory\n"
        "def test_x():\n"
        "    cats = AuditActionCategory.GOVERNANCE_TRACE\n"
        "    assert len(cats.value) == 16\n",
    )
    assert checker.rule_total_assertion_is_unique(_ctx(tmp_path, _BASELINE_AUTH)) == []


# --------------------------------------------------------------------------- #
# 规则 5 / 6：总数与必需族（跑真实仓库）                                          #
# --------------------------------------------------------------------------- #


def test_real_repo_audit_total_matches_baseline() -> None:
    baseline = json.loads(
        (
            PROJECT_ROOT / ".ai/baselines/phase3.8_governance_release_baseline.json"
        ).read_text(encoding="utf-8")
    )
    ctx = _ctx(PROJECT_ROOT, baseline=baseline)
    assert checker.rule_audit_total_matches_baseline(ctx) == []
    assert checker.rule_required_audit_families(ctx) == []


def test_wrong_baseline_total_is_rejected() -> None:
    ctx = _ctx(PROJECT_ROOT, baseline={"audit_category_contract": {"total": 999}})
    violations = checker.rule_audit_total_matches_baseline(ctx)
    assert violations and "999" in violations[0].detail


def test_missing_required_family_is_rejected() -> None:
    ctx = _ctx(
        PROJECT_ROOT,
        baseline={
            "audit_category_contract": {
                "required_families": {"ghost": ["NO_SUCH_CATEGORY"]}
            }
        },
    )
    violations = checker.rule_required_audit_families(ctx)
    assert violations and "NO_SUCH_CATEGORY" in violations[0].detail


# --------------------------------------------------------------------------- #
# 规则 7：红线① engineering_enabled                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", ["true", "True", "yes", "1"])
def test_engineering_enabled_true_is_rejected(tmp_path: Path, value: str) -> None:
    _write(tmp_path / "agents/config.yaml", f"engineering:\nengineering_enabled: {value}\n")
    violations = checker.rule_engineering_flag_false(_ctx(tmp_path))
    assert violations, f"engineering_enabled={value} 必须被拦下"


def test_engineering_enabled_false_passes(tmp_path: Path) -> None:
    _write(tmp_path / "agents/config.yaml", "engineering_enabled: false\n")
    assert checker.rule_engineering_flag_false(_ctx(tmp_path)) == []


def test_missing_config_is_rejected(tmp_path: Path) -> None:
    assert checker.rule_engineering_flag_false(_ctx(tmp_path))


def test_real_repo_engineering_flag_is_false() -> None:
    assert checker.rule_engineering_flag_false(_ctx(PROJECT_ROOT)) == []


# --------------------------------------------------------------------------- #
# 规则 8：红线② engineering_approved                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "snippet",
    [
        "def engineering_approved(self):\n    return True\n",
        "engineering_approved = True\n",
        'payload = {"engineering_approved": True}\n',
    ],
)
def test_engineering_approved_emission_is_rejected(tmp_path: Path, snippet: str) -> None:
    _write(tmp_path / "agents/mod.py", snippet)
    violations = checker.rule_no_engineering_approved_emission(_ctx(tmp_path))
    assert violations, f"正向产出必须被拦下：{snippet!r}"


def test_engineering_approved_negative_declaration_allowed(tmp_path: Path) -> None:
    """禁语清单必须能提到这个名字，否则无法声明"禁止它"。"""
    _write(
        tmp_path / "agents/enterprise/forbidden.py",
        'FORBIDDEN = ("engineering_approved", "auto_approve")\n',
    )
    _write(
        tmp_path / "agents/mod.py",
        '"""本模块永不输出 engineering_approved。"""\n'
        'BANNED = ("engineering_approved",)\n',
    )
    assert checker.rule_no_engineering_approved_emission(_ctx(tmp_path)) == []


def test_real_repo_emits_no_engineering_approved() -> None:
    assert checker.rule_no_engineering_approved_emission(_ctx(PROJECT_ROOT)) == []


# --------------------------------------------------------------------------- #
# 规则 9：阶段编号唯一                                                           #
# --------------------------------------------------------------------------- #


def test_conflicting_phase_status_is_rejected(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        baseline={"phase_registry": [{"phase": "3.8.27", "status": "INFRA_BUILT"}]},
        ssot={"phase_3_8_27_status": "SOMETHING_ELSE"},
    )
    violations = checker.rule_phase_numbering_unique(ctx)
    assert violations and "3.8.27" in violations[0].detail


def test_matching_phase_status_passes(tmp_path: Path) -> None:
    ctx = _ctx(
        tmp_path,
        baseline={"phase_registry": [{"phase": "3.8.27", "status": "INFRA_BUILT"}]},
        ssot={"phase_3_8_27_status": "INFRA_BUILT"},
    )
    assert checker.rule_phase_numbering_unique(ctx) == []


# --------------------------------------------------------------------------- #
# 端到端：真实仓库必须整体通过                                                    #
# --------------------------------------------------------------------------- #


def test_main_on_real_repository_exits_zero(capsys: pytest.CaptureFixture) -> None:
    code = checker.main(["--root", str(PROJECT_ROOT)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "治理仓库完整性检查通过" in out


def test_main_reports_failure_with_broken_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """基线缺失时必须以非零码退出——门禁不能因为"读不到"就默认放行。"""
    code = checker.main(
        ["--root", str(tmp_path), "--baseline", str(tmp_path / "missing.json")]
    )
    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_checker_is_read_only() -> None:
    """结构级保证：检查器源码中不得出现任何写文件/删文件调用。"""
    source = _CHECKER_PATH.read_text(encoding="utf-8")
    for banned in (
        "write_text(",
        "unlink(",
        "rmtree(",
        "os.remove",
        "shutil.move",
        'open(', 
    ):
        # ``open(`` 允许出现在 argparse 帮助文本之外的地方吗？不允许——
        # 读文件一律走 Path.read_text，保持"只读"在源码层面可验证。
        assert banned not in source, f"检查器必须只读，但出现了 {banned}"
