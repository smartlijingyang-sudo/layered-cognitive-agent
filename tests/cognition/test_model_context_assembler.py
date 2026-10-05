"""Direct unit tests for DefaultModelContextAssembler (ADR-0191/0193 assembler seam).

tests/cognition/test_model_context_parity.py pins the happy path
(Session fold -> identical messages + system + config). This file pins the
header-robustness behaviors: missing header, Mapping vs attribute headers,
tools filtering, and system/config normalization. The assembler is the
"assemble" link of dispatch -> assemble -> run; these invariants must not
silently change (header shape shifts with session backends).
"""

from __future__ import annotations

from types import SimpleNamespace

from lca.infrastructure.session.context.model_context_assembler import (
    DefaultModelContextAssembler,
    default_model_context_assembler,
)


class _StubSession:
    """Minimal SessionReader: derive_messages + request_header only."""

    def __init__(self, header, messages=None):
        self._header = header
        self._messages = [{"role": "user", "content": "hi"}] if messages is None else messages

    def derive_messages(self):
        return list(self._messages)

    def request_header(self):
        return self._header


def _assemble(header, **kwargs):
    return DefaultModelContextAssembler().assemble(_StubSession(header, **kwargs), step=1)


def test_header_none_yields_empty_header_fields() -> None:
    req = _assemble(None)
    assert req.messages == [{"role": "user", "content": "hi"}]
    assert req.tools == ()
    assert req.config is None
    assert req.system is None


def test_mapping_header_tools_become_tuple_of_dicts() -> None:
    src_tool = {"name": "search", "description": "web"}
    req = _assemble({"tools": [src_tool], "config": {"model": "m"}, "system": "sys"})
    assert req.tools == ({"name": "search", "description": "web"},)
    assert isinstance(req.tools, tuple)
    # dict(item) copy: source mutation must not leak into the request
    src_tool["name"] = "mutated"
    assert req.tools[0]["name"] == "search"


def test_mapping_header_tools_tuple_input_and_non_mapping_items_filtered() -> None:
    req = _assemble({"tools": ({"name": "a"}, "not-a-mapping", 42, None)})
    assert req.tools == ({"name": "a"},)


def test_mapping_header_non_sequence_tools_yields_empty_tuple() -> None:
    for bad in ("a-string", {"not": "a-list"}, 123):
        req = _assemble({"tools": bad})
        assert req.tools == ()


def test_attribute_header_read_via_getattr() -> None:
    header = SimpleNamespace(tools=[{"name": "t"}], config={"k": "v"}, system="s")
    req = _assemble(header)
    assert req.tools == ({"name": "t"},)
    assert req.config == {"k": "v"}
    assert req.system == "s"


def test_attribute_header_missing_fields_default_to_empty() -> None:
    req = _assemble(SimpleNamespace())
    assert req.tools == ()
    assert req.config is None
    assert req.system is None


def test_config_non_mapping_yields_none() -> None:
    req = _assemble({"config": "should-be-a-mapping"})
    assert req.config is None


def test_system_empty_string_yields_none() -> None:
    req = _assemble({"system": ""})
    assert req.system is None


def test_system_non_string_yields_none() -> None:
    req = _assemble({"system": {"text": "sys"}})
    assert req.system is None


def test_step_is_reserved_and_does_not_change_output() -> None:
    session = _StubSession({"system": "s"})
    assembler = DefaultModelContextAssembler()
    first = assembler.assemble(session, step=1)
    second = assembler.assemble(session, step=99)
    assert first == second


def test_factory_returns_working_assembler() -> None:
    req = default_model_context_assembler().assemble(_StubSession(None), step=1)
    assert req.messages == [{"role": "user", "content": "hi"}]
    assert req.tools == ()
