"""Phase 3.9.13 —— 双钥匙授权登记簿（T19，HUMAN_AUTHORIZED_APPLY）。

两把钥匙缺一不可：
- Key A（Machine Safety Key）：机器生成，证明 apply 管道处于 plan-only/safe 模式且
  ``engineering_enabled=false``。**机器可生成**。
- Key B（Human Authorization Key）：真人授权，**actor_kind=USER**。AI 不得自行生成
  （``require_human_actor(USER)`` 强制）。

只有两把钥匙同时有效，``HUMAN_AUTHORIZED_APPLY`` 才成立；否则 apply 被禁止。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from agents.enterprise.audit import require_human_actor


@dataclass
class MachineSafetyKey:
    """Key A：机器安全钥匙。"""

    key_id: str
    generated_from_commit: str
    engineering_enabled: bool
    plan_only: bool = True
    hash: str = ""

    def compute_hash(self) -> str:
        body = {
            "key_id": self.key_id,
            "generated_from_commit": self.generated_from_commit,
            "engineering_enabled": self.engineering_enabled,
            "plan_only": self.plan_only,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def is_valid(self) -> bool:
        return (self.engineering_enabled is False) and (self.plan_only is True)


@dataclass
class HumanAuthorizationKey:
    """Key B：真人授权钥匙（actor_kind=USER）。"""

    authorization_id: str
    actor_id: str
    actor_kind: str
    scope: str
    authorized_at: str
    hash: str = ""

    def compute_hash(self) -> str:
        body = {
            "authorization_id": self.authorization_id,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "scope": self.scope,
            "authorized_at": self.authorized_at,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def is_valid(self) -> bool:
        return self.actor_kind == "user"


class AuthorizationRegistryError(ValueError):
    """授权登记簿违例。"""


class ProvisioningAuthorizationRegistry:
    """双钥匙授权登记簿。"""

    def __init__(self) -> None:
        self._machine_key: MachineSafetyKey | None = None
        self._human_key: HumanAuthorizationKey | None = None

    def register_machine_safety_key(
        self, *, key_id: str, generated_from_commit: str, engineering_enabled: bool
    ) -> MachineSafetyKey:
        key = MachineSafetyKey(
            key_id=key_id,
            generated_from_commit=generated_from_commit,
            engineering_enabled=engineering_enabled,
            plan_only=True,
        )
        key.hash = key.compute_hash()
        if not key.is_valid():
            raise AuthorizationRegistryError(
                "Machine Safety Key 无效：engineering_enabled 必须为 False 且 plan_only=true"
            )
        self._machine_key = key
        return key

    def register_human_authorization(
        self,
        *,
        authorization_id: str,
        actor_id: str,
        actor_kind: str,
        scope: str,
        authorized_at: str,
    ) -> HumanAuthorizationKey:
        require_human_actor(actor_kind)
        key = HumanAuthorizationKey(
            authorization_id=authorization_id,
            actor_id=actor_id,
            actor_kind="user",
            scope=scope,
            authorized_at=authorized_at,
        )
        key.hash = key.compute_hash()
        self._human_key = key
        return key

    def machine_key_present(self) -> bool:
        return self._machine_key is not None and self._machine_key.is_valid()

    def human_key_present(self) -> bool:
        return self._human_key is not None and self._human_key.is_valid()

    def is_authorized_for_apply(self) -> bool:
        return self.machine_key_present() and self.human_key_present()

    def combined_status(self) -> dict[str, Any]:
        return {
            "machine_safety_key_present": self.machine_key_present(),
            "human_authorization_key_present": self.human_key_present(),
            "human_authorized_apply": self.is_authorized_for_apply(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_safety_key": (
                self._machine_key.__dict__ if self._machine_key else None
            ),
            "human_authorization_key": (
                self._human_key.__dict__ if self._human_key else None
            ),
            "combined_status": self.combined_status(),
        }


__all__ = [
    "MachineSafetyKey",
    "HumanAuthorizationKey",
    "AuthorizationRegistryError",
    "ProvisioningAuthorizationRegistry",
]
