"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— 环境指纹（Task 3）。

``EnvironmentFingerprint`` 对环境身份（kind / name / purpose / 资源声明）做
确定性哈希，使「环境身份」不可被标签伪造：隔离校验比对指纹而非信任 ``kind`` 字符串。

fail-closed 要点：
- 指纹由**全部**身份分量（含资源声明）参与计算；任一分量变化即改变指纹。
- 生产环境的指纹一旦登记，staging 无法「改名」伪装成它（指纹不同即拒绝）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

FINGERPRINT_ALGORITHM = "sha256"


@dataclass(frozen=True)
class EnvironmentFingerprint:
    """环境结构指纹（不可变）。"""

    value: str
    algorithm: str = FINGERPRINT_ALGORITHM
    components: tuple[str, ...] = ()

    def matches(self, other: "EnvironmentFingerprint") -> bool:
        """指纹是否一致（同算法 + 同哈希值）。"""

        return self.algorithm == other.algorithm and self.value == other.value

    def __str__(self) -> str:
        head = self.value[:16]
        return f"{self.algorithm}:{head}…({len(self.components)} components)"


def _canonical_components(
    kind: RuntimeEnvironment,
    name: str,
    purpose: str,
    resources: EnvironmentResources,
) -> tuple[str, ...]:
    """构造参与指纹计算的规范分量元组（顺序固定、取值归一）。"""

    resource_items = tuple(
        f"{k}={resources.__dict__[k]}"
        for k in sorted(resources.__dict__.keys())
    )
    return (
        f"kind={kind.value}",
        f"name={name}",
        f"purpose={purpose}",
        "resources=" + "|".join(resource_items),
    )


def compute_environment_fingerprint(
    kind: RuntimeEnvironment,
    name: str,
    purpose: str,
    resources: EnvironmentResources,
) -> EnvironmentFingerprint:
    """计算环境结构指纹。

    规范分量 → 拼接 → SHA-256。任意身份分量（含资源声明）变化都会导致指纹变化。
    """

    components = _canonical_components(kind, name, purpose, resources)
    payload = "\n".join(components).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return EnvironmentFingerprint(
        value=digest,
        algorithm=FINGERPRINT_ALGORITHM,
        components=components,
    )


def fingerprint_environment(
    *, kind: RuntimeEnvironment, name: str, purpose: str,
    resources: EnvironmentResources | None = None,
) -> EnvironmentFingerprint:
    """便捷构造：从分量直接得到指纹。"""

    return compute_environment_fingerprint(
        kind=kind, name=name, purpose=purpose,
        resources=resources or EnvironmentResources(),
    )


def fingerprints_disjoint(first: Iterable[EnvironmentFingerprint], second: EnvironmentFingerprint) -> bool:
    """判断 ``second`` 是否不在 ``first`` 集合中（用于「staging 指纹 ≠ production 指纹」校验）。"""

    return not any(fp.matches(second) for fp in first)


__all__ = [
    "FINGERPRINT_ALGORITHM",
    "EnvironmentFingerprint",
    "compute_environment_fingerprint",
    "fingerprint_environment",
    "fingerprints_disjoint",
]
