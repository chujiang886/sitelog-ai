"""Phase 3.9.14 —— IaC 可执行性 fail-closed 测试（T44 覆盖）。

断言：
- 工具链已安装（第一优先级交付物）；
- 8(+network) 模块均 count=0 骨架（无真实资源）；
- HCL 语法有效（terraform fmt -check 离线通过）；
- ``real_apply_allowed`` / ``real_execution_allowed`` 恒 False；
- ``contains_real_resource`` 恒 False；
- 整体 ``executable = True``，verdict = EXECUTABLE_READY_FOR_HUMAN_APPLY。

本测试不 skip / xfail / ignore 任何失败：若工具链缺失或模块不再可执行，测试必须响亮地失败。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.external_staging_runtime.iac_executor import execute
from agents.external_staging_runtime.iac_readiness import IaCExecutableReadinessAuditor

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STAGING_DIR = _REPO_ROOT / "infrastructure" / "staging"


def test_toolchain_installed_first_priority():
    """第一优先级：Terraform/OpenTofu 必须已安装。"""
    rep = execute(_STAGING_DIR)
    assert rep.toolchain.available is True, (
        "IaC 工具链未安装 —— 3.9.14 第一优先级要求安装 Terraform/OpenTofu。"
        "请先在受管目录 /Users/chujiangai/.workbuddy/binaries/iac/bin/ 安装。"
    )
    assert rep.toolchain.flavour in ("terraform", "tofu")


def test_all_modules_count_zero_no_real_resources():
    """全部资源块均为 count=0 占位，无真实资源。"""
    rep = execute(_STAGING_DIR)
    assert rep.all_count_zero is True
    assert rep.contains_real_resource is False


def test_hcl_syntax_valid_offline():
    """Offline HCL 语法有效（terraform fmt -check 通过，无需 provider）。"""
    rep = execute(_STAGING_DIR)
    assert rep.fmt_syntax_valid is True


def test_real_apply_never_allowed_fail_closed():
    """fail-closed：绝不允许 apply / 真实执行 / 含真实资源。"""
    rep = execute(_STAGING_DIR)
    assert rep.real_apply_allowed is False
    assert rep.real_execution_allowed is False
    assert rep.contains_real_resource is False


def test_iac_executable_verdict():
    """整体可执行，verdict 正确。"""
    rep = execute(_STAGING_DIR)
    assert rep.executable is True
    assert rep.verdict == "EXECUTABLE_READY_FOR_HUMAN_APPLY"


def test_readiness_auditor_executable_matrix():
    """IaCExecutableReadinessAuditor 聚合：9 模块全 intentional_skeleton + executable。"""
    aud = IaCExecutableReadinessAuditor(_STAGING_DIR).audit_all()
    assert aud["module_count"] == 9
    assert aud["blocking_count"] == 0
    assert aud["real_apply_allowed"] is False
    assert aud["contains_real_resource"] is False
    assert aud["executable"] is True
    assert aud["verdict"] == "EXECUTABLE_READY_FOR_HUMAN_APPLY"
    for m in aud["modules"]:
        assert m["classification"] == "intentional_skeleton", f"模块 {m['module']} 非骨架：{m['detail']}"
        assert m["executable"] is True
    # 工具链真实校验信息存在
    assert aud["toolchain"]["available"] is True
