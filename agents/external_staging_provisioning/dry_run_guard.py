"""Phase 3.9.12 —— Dry-run Guard（Task 18）。

对 IaC 模板与 8 资源适配器执行 fail-closed 干跑校验：

1. **凭据泄漏扫描**：扫描 ``infrastructure/staging/*.tf``，确保无明文 Secret /
   access_key / token 落入（复用 ``credential_scanner.assert_no_credential_leak``）。
2. **占位自检**：确认真实数据型资源模块（database / secret_provider / object_storage /
   deployment_target）均含 ``count = 0`` 占位，使 ``tofu plan`` 不落真实资源——
   AI 永不代开真实资源。
3. **默认 provider 非 production**：默认 ``tencentcloud``，aws/alibabacloud 覆写为注释。
4. **适配器契约测试**：复用 3.9.11 的 8 资源 Fake Adapter 契约测试，确认全部诚实
   PENDING（无真实执行宣称）。

任何一项失败即 fail-closed 阻断（``DryRunGuardError``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_execution.adapters import (
    AdapterProbeResult,
    adapters_contract_test_all_pass,
    assert_no_real_execution_claimed,
    probe_all,
)

# 含真实数据、必须 count=0 占位的资源模块（避免 AI 代开真实资源）。
_REAL_DATA_IAC_MODULES = (
    "infrastructure/staging/database.tf",
    "infrastructure/staging/secret_provider.tf",
    "infrastructure/staging/object_storage.tf",
    "infrastructure/staging/deployment_target.tf",
)

# 默认 provider（禁止 production/aws/alibabacloud 作为默认激活 provider）。
_DEFAULT_PROVIDER = "tencentcloud"


class DryRunGuardError(ValueError):
    """干跑校验失败（fail-closed 阻断）。"""


@dataclass
class IaCScanResult:
    """IaC 目录扫描结果。"""

    iac_dir: str
    scanned_files: tuple[str, ...] = field(default_factory=tuple)
    credential_leak_hits: tuple[str, ...] = field(default_factory=tuple)
    count_zero_modules: tuple[str, ...] = field(default_factory=tuple)
    default_provider: str = ""
    provider_ok: bool = False
    all_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "iac_dir": self.iac_dir,
            "scanned_files": list(self.scanned_files),
            "credential_leak_hits": list(self.credential_leak_hits),
            "count_zero_modules": list(self.count_zero_modules),
            "default_provider": self.default_provider,
            "provider_ok": self.provider_ok,
            "all_ok": self.all_ok,
        }


def scan_iac_directory(iac_dir: str | Path) -> IaCScanResult:
    """扫描 IaC 目录（fail-closed）。"""

    root = Path(iac_dir)
    tf_files = sorted(root.glob("*.tf"))
    scanned: list[str] = []
    leak_hits: list[str] = []
    count_zero: list[str] = []
    default_provider = ""

    for tf in tf_files:
        text = tf.read_text(encoding="utf-8")
        scanned.append(tf.name)
        # 1) 凭据泄漏扫描
        try:
            assert_no_credential_leak(text=text)
        except CredentialLeakError as exc:
            leak_hits.append(f"{tf.name}: {exc}")
        # 2) count=0 占位自检（仅真实数据型模块）
        rel = f"infrastructure/staging/{tf.name}"
        if rel in _REAL_DATA_IAC_MODULES:
            if "count" in text and "0" in text:
                count_zero.append(rel)
        # 3) 默认 provider（从 main.tf 推断）
        if tf.name == "main.tf":
            if 'provider "tencentcloud"' in text:
                default_provider = "tencentcloud"
            elif 'provider "aws"' in text:
                default_provider = "aws"
            elif 'provider "alibabacloud"' in text:
                default_provider = "alibabacloud"

    provider_ok = default_provider == _DEFAULT_PROVIDER
    all_ok = (
        not leak_hits
        and len(count_zero) == len(_REAL_DATA_IAC_MODULES)
        and provider_ok
    )
    return IaCScanResult(
        iac_dir=str(root),
        scanned_files=tuple(scanned),
        credential_leak_hits=tuple(leak_hits),
        count_zero_modules=tuple(count_zero),
        default_provider=default_provider,
        provider_ok=provider_ok,
        all_ok=all_ok,
    )


def assert_iac_holds_no_real_provisioning(iac_dir: str | Path) -> None:
    """断言 IaC 模板不代开真实资源（fail-closed）。"""

    result = scan_iac_directory(iac_dir)
    if result.credential_leak_hits:
        raise DryRunGuardError(
            "IaC 凭据泄漏：" + "; ".join(result.credential_leak_hits)
        )
    missing = [
        m for m in _REAL_DATA_IAC_MODULES if m not in result.count_zero_modules
    ]
    if missing:
        raise DryRunGuardError(
            f"以下真实数据型模块缺少 count=0 占位（AI 不得代开真实资源）：{missing}"
        )
    if not result.provider_ok:
        raise DryRunGuardError(
            f"默认 provider={result.default_provider!r} 非 {_DEFAULT_PROVIDER!r}（禁 production/aws/alibabacloud 默认激活）。"
        )


class IacDryRunGuard:
    """外部预生产供给干跑闸门（fail-closed 评估器）。"""

    def __init__(self, iac_dir: str | Path | None = None) -> None:
        if iac_dir is None:
            repo_root = Path(__file__).resolve().parents[2]
            iac_dir = repo_root / "infrastructure" / "staging"
        self.iac_dir = Path(iac_dir)

    def evaluate(self) -> IaCScanResult:
        """执行组合干跑校验：IaC 扫描 + 适配器契约测试。"""

        # IaC 扫描（含 count=0 / provider / 凭据 校验）
        iac_result = scan_iac_directory(self.iac_dir)
        if not iac_result.all_ok:
            raise DryRunGuardError(
                "IaC 干跑校验未通过："
                + ("凭据泄漏；" if iac_result.credential_leak_hits else "")
                + (
                    f"缺少 count=0 模块({len(iac_result.count_zero_modules)}/{len(_REAL_DATA_IAC_MODULES)})；"
                    if len(iac_result.count_zero_modules) != len(_REAL_DATA_IAC_MODULES)
                    else ""
                )
                + (f"默认 provider={iac_result.default_provider!r}；" if not iac_result.provider_ok else "")
            )

        # 适配器契约测试（8 资源诚实 PENDING，无真实执行宣称）
        probe_results: list[AdapterProbeResult] = probe_all()
        assert_no_real_execution_claimed(probe_results)
        if not adapters_contract_test_all_pass():
            raise DryRunGuardError("8 资源 Fake Adapter 契约测试未全通过（代码路径不自洽）。")

        return iac_result


__all__ = [
    "DryRunGuardError",
    "IaCScanResult",
    "scan_iac_directory",
    "assert_iac_holds_no_real_provisioning",
    "IacDryRunGuard",
]
