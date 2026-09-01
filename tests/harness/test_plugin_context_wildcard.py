"""Wildcard capability require + collection for AuditedPluginContext."""

from __future__ import annotations

from typing import Any

import pytest

from lca.harness.plugin_api import (
    AuditedPluginContext,
    EffectClass,
    PluginDefinition,
    PluginKind,
    UndeclaredInteractionError,
)
from lca.harness.plugin_context import collect_context_bindings, requirement_covers_key
from lca.harness.plugin_spec_projection import native_spec_from_declaration


class _FakeCarrier:
    """Minimal Cordis-shaped carrier with ``own_bindings`` + parent chain."""

    def __init__(
        self,
        bindings: dict[str, Any] | None = None,
        *,
        parent: _FakeCarrier | None = None,
    ) -> None:
        self.own_bindings: dict[str, Any] = dict(bindings or {})
        self.parent = parent

    def provide(self, key: str, value: object, **kwargs: object) -> None:
        del kwargs
        self.own_bindings[key] = value

    def inject(self, key: str) -> Any:
        node: _FakeCarrier | None = self
        while node is not None:
            if key in node.own_bindings:
                return node.own_bindings[key]
            node = node.parent
        raise KeyError(key)


def _definition(
    *, requires: tuple[str, ...], provides: tuple[str, ...] = ()
) -> PluginDefinition[Any]:
    async def setup(_ctx: object, _config: object) -> None:
        return None

    return PluginDefinition(
        Config=None,
        setup=setup,
        spec=native_spec_from_declaration(
            plugin_id="test.wildcard",
            config_cls=None,
            provides=provides,
            requires=requires,
            implements=(),
            layer="L1",
            kind=PluginKind.SEAM,
            effects=frozenset({EffectClass.NONE}),
            test_suite=__name__,
            functional_group=None,
            module=__name__,
        ),
        description="",
    )


def test_requirement_covers_key_exact_and_wildcard() -> None:
    assert requirement_covers_key("emit_pipeline", "emit_pipeline")
    assert requirement_covers_key("field_producer.*", "field_producer.source")
    assert requirement_covers_key("field_producer.*", "field_producer.exception.builtin")
    assert not requirement_covers_key("field_producer.*", "deriver.anomaly")
    assert not requirement_covers_key("field_producer.*", "field_producer")


def test_collect_context_bindings_walks_parent_chain_child_wins() -> None:
    parent = _FakeCarrier({"a": 1, "shared": "parent"})
    child = _FakeCarrier({"b": 2, "shared": "child"}, parent=parent)

    bindings = collect_context_bindings(child)
    assert bindings == {"a": 1, "b": 2, "shared": "child"}


def test_require_allows_concrete_key_under_wildcard_declaration() -> None:
    parent = _FakeCarrier({"field_producer.source": object()})
    child = _FakeCarrier(parent=parent)
    ctx = AuditedPluginContext(child, _definition(requires=("field_producer.*",)))

    value = ctx.require("field_producer.source")
    assert value is parent.own_bindings["field_producer.source"]
    assert "field_producer.source" in ctx.required


def test_require_still_rejects_undeclared_exact_keys() -> None:
    ctx = AuditedPluginContext(
        _FakeCarrier(),
        _definition(requires=("field_producer.*",)),
    )
    with pytest.raises(UndeclaredInteractionError, match=r"require\('deriver\.anomaly'\)"):
        ctx.require("deriver.anomaly")


def test_require_matching_collects_prefix_keys() -> None:
    parent = _FakeCarrier(
        {
            "field_producer.source": "src",
            "deriver.anomaly": "skip-me",
        }
    )
    child = _FakeCarrier({"field_producer.runtime": "rt"}, parent=parent)
    ctx = AuditedPluginContext(
        child,
        _definition(requires=("field_producer.*", "deriver.anomaly")),
    )

    matched = ctx.require_matching("field_producer.")
    assert matched == {
        "field_producer.source": "src",
        "field_producer.runtime": "rt",
    }
    assert "field_producer.source" in ctx.required
    assert "field_producer.runtime" in ctx.required


def test_require_matching_requires_declared_wildcard() -> None:
    ctx = AuditedPluginContext(
        _FakeCarrier({"field_producer.source": object()}),
        _definition(requires=("deriver.anomaly",)),
    )
    with pytest.raises(UndeclaredInteractionError, match=r"field_producer\.\*"):
        ctx.require_matching("field_producer.")


def test_require_matching_rejects_prefix_without_trailing_dot() -> None:
    ctx = AuditedPluginContext(
        _FakeCarrier(),
        _definition(requires=("field_producer.*",)),
    )
    with pytest.raises(ValueError, match=r"must end with '\.'"):
        ctx.require_matching("field_producer")


def test_soft_get_returns_optional_without_audit() -> None:
    carrier = _FakeCarrier({"step_tree": "tree", "narrative": "nar"})
    ctx = AuditedPluginContext(carrier, _definition(requires=(), provides=()))

    assert ctx.soft_get("step_tree") == "tree"
    assert ctx.soft_get("missing") is None
    assert ctx.required == set()
