"""Phase 3.9.2 企业生产发布闸门与证据包层 —— RC 冻结清单（RC Freeze Manifest，SHA-256）。

``generate_rc_freeze_manifest(rc, root_dir)``：对 ``rc.components`` 中的每个组件重算 SHA-256，
构建 ``RCFreezeManifest``（只描述），并就其规范化 JSON 计算 ``manifest_sha256``。

红线（T11 / ⑧ / ⑩）：
- 清单**只描述**冻结哈希，不执行部署、不写真实数据；
- 缺失产物文件对应哈希标记为 ``<missing>`` 而非伪造；
- ``manifest_sha256`` 由清单内容本身派生，便于冻结检查器做「清单自洽性」校验。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.enterprise.production_release.package import _sha256_of_file
from agents.enterprise.production_release.release_candidate import (
    RCFreezeComponent,
    ReleaseCandidate,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RCFreezeManifest:
    """RC 冻结清单：记录各组件冻结时刻 SHA-256 与清单自洽哈希。只描述，不部署。"""

    rc_id: str
    version: str
    commit_sha: str
    generated_at: str
    components: List[RCFreezeComponent]
    manifest_sha256: str = ""  # 由本清单规范化内容派生
    note: str = "RC_FREEZE_MANIFEST_ONLY: 描述冻结哈希；不执行部署"

    def to_dict(self) -> Dict[str, object]:
        return {
            "rc_id": self.rc_id,
            "version": self.version,
            "commit_sha": self.commit_sha,
            "generated_at": self.generated_at,
            "components": [c.to_dict() for c in self.components],
            "manifest_sha256": self.manifest_sha256,
            "note": self.note,
        }

    def canonical(self) -> str:
        """规范化 JSON（排除 ``manifest_sha256`` 自引用），用于派生清单哈希。"""
        payload = {
            "rc_id": self.rc_id,
            "version": self.version,
            "commit_sha": self.commit_sha,
            "generated_at": self.generated_at,
            "components": [c.to_dict() for c in self.components],
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def has_missing(self) -> bool:
        """是否存在不可达（``<missing>`` / ``<unreadable>``）组件。"""
        return any(c.sha256 in ("<missing>", "<unreadable>") for c in self.components)


def _manifest_sha256_of(manifest: "RCFreezeManifest") -> str:
    return hashlib.sha256(manifest.canonical().encode("utf-8")).hexdigest()


def generate_rc_freeze_manifest(
    rc: ReleaseCandidate,
    root_dir: str = ".",
) -> RCFreezeManifest:
    """依据 ``rc`` 生成冻结清单：重算各组件 SHA-256 并派生 ``manifest_sha256``。

    注意：本函数重算的是「当前工作树」的组件哈希；冻结检查器会再用同一算法重算并比对，
    二者不一致即判定 DRIFTED。缺文件标 ``<missing>`` / ``<unreadable>``，绝不伪造。
    """

    base = os.path.abspath(root_dir)
    recomputed: List[RCFreezeComponent] = []
    for comp in rc.components:
        full = os.path.join(base, comp.repo_path)
        sha = _sha256_of_file(full)
        recomputed.append(
            RCFreezeComponent(
                name=comp.name,
                repo_path=comp.repo_path,
                sha256=sha,
                present=sha not in ("<missing>", "<unreadable>"),
            )
        )
    draft = RCFreezeManifest(
        rc_id=rc.rc_id,
        version=rc.version,
        commit_sha=rc.commit_sha,
        generated_at=_now(),
        components=recomputed,
    )
    return RCFreezeManifest(
        rc_id=draft.rc_id,
        version=draft.version,
        commit_sha=draft.commit_sha,
        generated_at=draft.generated_at,
        components=draft.components,
        manifest_sha256=_manifest_sha256_of(draft),
    )


__all__ = [
    "RCFreezeManifest",
    "generate_rc_freeze_manifest",
]
