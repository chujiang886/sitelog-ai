"""DualTrackRouter 构造 + ProviderRole 解耦（Phase 2.1.6）测试。

覆盖：
- ``build_router_from_config(role=TEXT)`` 走 ``providers.text``；
- ``build_router_from_config(role=VISION)`` 走 ``providers.vision``；
- ``providers.vision`` 缺失时回落 ``providers.text``（向后兼容）；
- ``role=FALLBACK`` 恒为 mock 容灾副轨；
- 旧 ``modality="vision"`` 软开关仍可用（deprecated 兼容别名）；
- 旧 ``track_a``/``track_b`` 键配置仍可被兼容解析（不作新入口）；
- ``build_embedding_provider`` 在 ``provider=disabled`` 时返回 ``None``；
- 路由 strategy / timeout 从 ``router`` 子块读取（验证子块解析不回归）。
"""

from __future__ import annotations

from agents.llm.mock import MockProvider
from agents.llm.openai_compat import OpenAICompatibleProvider
from agents.llm.router import (
    ProviderRole,
    build_embedding_provider,
    build_router_from_config,
    resolve_provider,
)


def _cfg_providers(text_key: str, vision_key: str) -> dict:
    """构造最小 llm 配置：providers.{text,vision,embedding,fallback} 四块。"""

    return {
        "enabled": True,
        "providers": {
            "text": {
                "provider": "openai_compat",
                "base_url": "http://llm",
                "api_key": text_key,
                "model": "m-text",
            },
            "vision": {
                "provider": "openai_compat",
                "base_url": "http://llm",
                "api_key": vision_key,
                "model": "m-vision",
            },
            "embedding": {"provider": "disabled"},
            "fallback": {"provider": "mock"},
        },
        "router": {"strategy": "fastest", "timeout": 30},
    }


def test_role_text_uses_providers_text_block():
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="pending_verification")
    router = build_router_from_config(cfg, role=ProviderRole.TEXT)
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-text"
    # 副轨恒为 fallback=mock
    assert isinstance(router.track_b, MockProvider)


def test_role_vision_uses_providers_vision_block():
    # text 无 key，vision 有真实 key → vision 主轨应为 openai_compat
    cfg = _cfg_providers(text_key="pending_verification", vision_key="sk-real-v")
    router = build_router_from_config(cfg, role=ProviderRole.VISION)
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-vision"
    assert isinstance(router.track_b, MockProvider)


def test_role_vision_falls_back_to_text_when_absent():
    # providers 块无 vision → 回落 providers.text
    cfg = {
        "enabled": True,
        "providers": {
            "text": {
                "provider": "openai_compat",
                "base_url": "http://llm",
                "api_key": "sk-real-a",
                "model": "m-text",
            },
            "fallback": {"provider": "mock"},
        },
        "router": {"strategy": "fastest", "timeout": 30},
    }
    router = build_router_from_config(cfg, role=ProviderRole.VISION)
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-text"


def test_role_fallback_is_always_mock():
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="sk-real-v")
    router = build_router_from_config(cfg, role=ProviderRole.TEXT)
    assert isinstance(router.track_b, MockProvider)


def test_modality_vision_deprecated_alias_maps_to_vision_role():
    # modality= 为 deprecated 兼容别名，应能等价映射到 VISION 角色
    cfg = _cfg_providers(text_key="pending_verification", vision_key="sk-real-v")
    router = build_router_from_config(cfg, modality="vision")
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-vision"


def test_modality_text_deprecated_alias_maps_to_text_role():
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="pending_verification")
    router = build_router_from_config(cfg, modality="text")
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-text"


def test_legacy_track_a_track_b_keys_still_resolved():
    # 旧 track_a / track_b 键配置仍可被兼容解析（不作新入口，但保持可用）
    cfg = {
        "enabled": True,
        "track_a": {
            "provider": "openai_compat",
            "base_url": "http://llm",
            "api_key": "sk-real-a",
            "model": "m-legacy-a",
        },
        "track_b": {"provider": "mock"},
        "router": {"strategy": "fastest", "timeout": 30},
    }
    router = build_router_from_config(cfg, role=ProviderRole.TEXT)
    assert isinstance(router.track_a, OpenAICompatibleProvider)
    assert router.track_a.model == "m-legacy-a"
    assert isinstance(router.track_b, MockProvider)


def test_embedding_provider_disabled_returns_none():
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="sk-real-v")
    assert build_embedding_provider(cfg) is None
    # resolve_provider(EMBEDDING) 同样返回 None
    assert resolve_provider(cfg, ProviderRole.EMBEDDING) is None


def test_router_subblock_strategy_and_timeout_are_read():
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="sk-real-v")
    cfg["router"] = {"strategy": "fallback", "timeout": 15}
    router = build_router_from_config(cfg, role=ProviderRole.VISION)
    assert router.strategy.value == "fallback"
    assert router._timeout == 15.0


def test_provider_role_has_unknown_defensive_member():
    # UNKNOWN 防御状态必须作为枚举成员存在。
    assert ProviderRole.UNKNOWN.value == "unknown"
    assert ProviderRole("unknown") is ProviderRole.UNKNOWN


def test_illegal_role_string_does_not_raise_and_enters_fallback():
    # 非法角色字符串不得抛 ValueError，应安全回落 fallback（mock 容灾）。
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="sk-real-v")
    router = build_router_from_config(cfg, role="not_a_real_role")
    assert router is not None
    # 主轨安全进入 fallback（mock），副轨恒为 mock。
    assert isinstance(router.track_a, MockProvider)
    assert isinstance(router.track_b, MockProvider)


def test_resolve_provider_unknown_role_returns_fallback_provider():
    # resolve_provider 对 UNKNOWN 角色返回 fallback（mock）provider，不抛异常。
    cfg = _cfg_providers(text_key="sk-real-a", vision_key="sk-real-v")
    provider = resolve_provider(cfg, ProviderRole.UNKNOWN)
    assert isinstance(provider, MockProvider)

