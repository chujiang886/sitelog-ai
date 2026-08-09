"""Enterprise Operation Layer 红线基座（Phase 3.8.0）。

复用 Phase 3.4/3.7 的统一 fail-closed 思想，但**自包含**，不反向依赖 engineering 内部类型，
仅共享 ``agents.config_loader.load_engineering_enabled`` 这一个只读护栏信号。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致）：
① 禁止开启 ``engineering_enabled``（所有 Enterprise 服务构造/决策路径断言
   ``safety_invariants_ok()``，非 False 即抛错）；
② 禁止输出 ``engineering_approved``（forbidden 方法名 ``approve`` /
   ``engineering_approved`` 被 mixin 拦截）；
③ 禁止自动报价（forbidden 方法名 ``quote`` / ``pricing``）；
④ 禁止自动审批（forbidden 方法名 ``approve`` / ``sign`` / ``authorize``）；
⑤ 禁止绕过 ``UnifiedActivationGate``（本层不持有 gate 实例，但统一以
   ``safety_invariants_ok()`` 作为构造/写路径前置断言，等价于门禁护栏）；
⑥ 禁止 AI 代替人工责任（``AuditService`` 不得把动作记录为人工审批：
   forbidden 方法名 ``record_human_approval`` 被拦截）。

设计要点：
- ``EnterpriseRedLineViolationError``：企业层红线违例异常（与工程层
  ``SolutionRedLineViolationError`` 同性质，但命名独立，零耦合）。
- ``_RedLineForbiddenMixin``：通过 ``__getattr__`` 拦截 forbidden 方法名，让「批准/报价/
  审批/记录为人工」在结构上不可达，而非靠约定。
- ``safety_invariants_ok()``：只读断言 ``load_engineering_enabled() is False``。
"""

from __future__ import annotations

from typing import Any

from agents.config_loader import load_engineering_enabled


class EnterpriseRedLineViolationError(Exception):
    """Enterprise Operation Layer 红线违例。"""


# 企业运营层 forbidden 方法名（覆盖红线②/③/④/⑥）。
_ENTERPRISE_FORBIDDEN_METHODS = (
    "approve",                  # 红线②/④：不得批准 / 审批
    "engineering_approved",     # 红线②：不得输出 engineering_approved
    "quote",                    # 红线③：禁止自动报价
    "pricing",                  # 红线③：禁止自动报价
    "sign",                     # 红线④：禁止自动签署
    "authorize",                # 红线④：禁止自动授权
    "record_human_approval",    # 红线⑥：禁止把 AI 动作记录为人工审批
)


def safety_invariants_ok() -> bool:
    """只读护栏断言：engineering_enabled 必须保持 False。

    等价于 UnifiedActivationGate.safety_invariants_ok() 的语义，供 enterprise 层独立复用。
    """
    return load_engineering_enabled() is False


class _RedLineForbiddenMixin:
    """拦截企业服务上的 forbidden 方法名（红线②/③/④/⑥）。

    仅当属性名确实缺失时才进入 ``__getattr__``；已定义的方法/字段不会受影响。
    旨在让「批准/报价/审批/记录为人工」在结构上不可达。
    """

    _FORBIDDEN = _ENTERPRISE_FORBIDDEN_METHODS

    def __getattr__(self, name: str) -> Any:
        if name in self._FORBIDDEN:
            raise EnterpriseRedLineViolationError(
                f"拦截调用 {name!r}：Enterprise Operation Layer 禁止 AI 执行批准/报价/"
                f"审批/记录为人工责任（红线②/③/④/⑥）。此类操作须经真实人工线下决策。"
            )
        raise AttributeError(f"{type(self).__name__!r} 对象无属性 {name!r}")


__all__ = [
    "EnterpriseRedLineViolationError",
    "safety_invariants_ok",
    "_RedLineForbiddenMixin",
    "_ENTERPRISE_FORBIDDEN_METHODS",
]
