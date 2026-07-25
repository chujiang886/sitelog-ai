"""Verify the BaseAgent ABC contract and Phase 0 helper methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
    Evidence,
)


class _SampleAgent(BaseAgent):
    """Minimal concrete Agent used to exercise the ABC contract."""

    def __init__(self) -> None:
        super().__init__(
            name="sample",
            description="Sample agent for BaseAgent contract tests",
            version="0.0.1",
        )

    @property
    def tools(self) -> tuple[str, ...]:
        return ("noop",)

    async def invoke(self, context: AgentContext) -> AgentResult:
        self._validate_input(context)
        evidence = (
            self._emit_evidence(source="invoke", content={"rid": context.request_id}),
        )
        return AgentResult(success=True, data={"echo": dict(context.input_data)}, evidence=evidence)


def test_base_agent_rejects_empty_name() -> None:
    """A subclass with an empty name must surface ``ValueError``."""

    class _Stub(BaseAgent):
        @property
        def tools(self):
            return ()

        async def invoke(self, context):
            return AgentResult(success=True)

    with pytest.raises(ValueError):
        _Stub(name="", description="desc", version="0.0.1")


def test_base_agent_requires_abstract_members() -> None:
    """A subclass that forgets either abstract member must fail to instantiate."""

    class _MissingInvoke(BaseAgent):
        @property
        def tools(self):
            return ()

    class _MissingTools(BaseAgent):
        async def invoke(self, context):
            return AgentResult(success=True)

    with pytest.raises(TypeError):
        _MissingInvoke("ok", "ok", "0.0.1")
    with pytest.raises(TypeError):
        _MissingTools("ok", "ok", "0.0.1")


def test_sample_agent_exposes_identity_metadata() -> None:
    """The helper must surface name/description/version and declared tools."""

    agent = _SampleAgent()
    assert agent.name == "sample"
    assert agent.description
    assert agent.version == "0.0.1"
    assert agent.tools == ("noop",)


def test_helper_load_prompt_reads_sibling_file(tmp_path: Path) -> None:
    """_load_prompt must read the sibling prompt.md when one exists."""

    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("# sample prompt\nbody", encoding="utf-8")
    agent = _SampleAgent()
    body = agent._load_prompt(base_dir=tmp_path)
    assert "sample prompt" in body


def test_helper_load_prompt_missing_raises(tmp_path: Path) -> None:
    """Missing prompt files must raise a descriptive FileNotFoundError."""

    agent = _SampleAgent()
    with pytest.raises(FileNotFoundError):
        agent._load_prompt(base_dir=tmp_path)


def test_helper_validate_input_rejects_empty_request_id() -> None:
    """_validate_input must refuse empty request_id values."""

    agent = _SampleAgent()
    with pytest.raises(ValueError):
        agent._validate_input(AgentContext(request_id="   "))


def test_helper_emit_evidence_uses_agent_prefix() -> None:
    """_emit_evidence must prefix the source with the Agent name."""

    agent = _SampleAgent()
    evidence: Evidence = agent._emit_evidence(source="x")
    assert evidence.source.startswith("sample.")
    assert evidence.confidence == "pending_verification"


def test_placeholder_result_helper_builds_envelope() -> None:
    """_placeholder_result must produce a well-formed AgentResult."""

    agent = _SampleAgent()
    result = agent._placeholder_result(status="ok", extra={"k": 1})
    assert result.success is True
    assert result.data["agent"] == "sample"
    envelope = result.to_envelope()
    assert envelope["success"] is True
    assert envelope["data"]["agent"] == "sample"
    assert envelope["data"]["status"] == "ok"


def test_agent_context_with_input_merges() -> None:
    """with_input must merge extra keys without mutating the source context."""

    ctx = AgentContext(request_id="req-1", input_data={"a": 1})
    new_ctx = ctx.with_input({"b": 2})
    assert new_ctx.input_data == {"a": 1, "b": 2}
    # Original context remains frozen
    assert ctx.input_data == {"a": 1}


def test_evidence_to_dict_is_json_safe() -> None:
    """Evidence.to_dict must drop the MappingProxyType guard."""

    evidence = Evidence(
        source="x",
        observed_at="now",
        confidence="pending_verification",
        content={"a": 1},
    )
    snapshot = evidence.to_dict()
    assert snapshot == {
        "source": "x",
        "observed_at": "now",
        "confidence": "pending_verification",
        "content": {"a": 1},
    }