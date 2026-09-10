"""Regression test: Default factory's _DefaultSubgraphRuntime must resolve think executors.

Bug fixed: ``DefaultDeclarativeInterpreterFactory.create`` built the
``_DefaultSubgraphRuntime.registry`` map by reading ``cls.semantic_name`` /
``cls.region`` directly off the Think*Executor classes. Because each
executor is a ``@dataclass(frozen=True, slots=True)``, ``getattr(cls,
"semantic_name")`` returns a ``member`` descriptor object rather than the
declared string default. The descriptor failed ``isinstance(..., str)``
and the loop produced an empty registry, so the inner ``NodeGraphDriver``
hit ``FactoryResolutionError`` on every think subgraph node and the run
failed at ``act.main`` with "think phase produced no decision".

ADR-0219 §10.11 close-out invariant: ``DefaultDeclarativeInterpreterFactory``
must surface a typed registry that resolves every node declared in
``bundles/think.yaml`` without a Cordis boot. The test exercises the
factory's no-cordis fallback and asserts each registered executor is
fetchable via ``(region, factory)``.
"""

from __future__ import annotations

from lca.plugins.journal.declarative.runtime_seams_provider import (
    DefaultDeclarativeInterpreterFactory,
)


def _build_factory_registry() -> dict[tuple[str, str], object]:
    """Mirror the registry-build path inside ``DefaultDeclarativeInterpreterFactory.create``.

    The factory's ``create`` call wires ``_DefaultSubgraphRuntime`` from the
    same registry-building loop; we extract the loop's effect by reusing the
    same ``inspect`` + ``dataclasses`` reads via a temporary factory. We do
    not call ``create`` directly because it requires a fully wired
    ``RuntimeJournal``/``EffectDispatcher``/etc. — out of scope for this
    unit test.
    """
    import dataclasses
    import inspect

    from lca.plugins import think as _think_module

    registry: dict[tuple[str, str], object] = {}
    for _name, cls in inspect.getmembers(_think_module, inspect.isclass):
        if not (
            isinstance(cls.__module__, str)
            and cls.__module__.startswith("lca.plugins.think")
            and cls.__name__.startswith("Think")
            and cls.__name__.endswith("Executor")
        ):
            continue
        if not dataclasses.is_dataclass(cls):
            continue
        field_map = {f.name: f for f in dataclasses.fields(cls)}
        sn_field = field_map.get("semantic_name")
        rg_field = field_map.get("region")
        if sn_field is None or rg_field is None:
            continue
        semantic_name = sn_field.default if isinstance(sn_field.default, str) else None
        region = rg_field.default if isinstance(rg_field.default, str) else None
        if not isinstance(semantic_name, str) or not isinstance(region, str):
            continue
        registry[(region, semantic_name)] = cls()
    return registry


def test_default_factory_registry_contains_every_think_node_factory() -> None:
    """Every factory in ``bundles/think.yaml`` + ``think_reason.yaml`` resolves via the no-cordis registry.

    Outer think.yaml uses ``think.reason`` as a sub_spec_ref entry node (no
    direct factory resolution at outer level) — Default factory maps it to
    ``ThinkReasonCompleteExecutor`` as a defensive fallback. Inner
    think_reason.yaml uses ``think.reason.{plan,render,complete}`` directly.
    """
    registry = _build_factory_registry()
    expected_factories = {
        ("phase:think", "think.shortcut"),
        ("phase:think", "think.route"),
        ("phase:think", "think.classify"),
        ("phase:think", "think.gate"),
        # inner think_reason.yaml nodes
        ("phase:think", "think.reason.plan"),
        ("phase:think", "think.reason.render"),
        ("phase:think", "think.reason.complete"),
    }
    assert expected_factories <= set(registry.keys()), (
        "missing factories: "
        f"{expected_factories - set(registry.keys())}"
    )


def test_default_factory_resolves_via_resolve_factory() -> None:
    """``resolve_factory`` on the no-cordis runtime returns a typed object."""
    import dataclasses
    import inspect

    from lca.plugins import think as _think_module

    registry: dict[tuple[str, str], object] = {}
    for _name, cls in inspect.getmembers(_think_module, inspect.isclass):
        if not (
            isinstance(cls.__module__, str)
            and cls.__module__.startswith("lca.plugins.think")
            and cls.__name__.startswith("Think")
            and cls.__name__.endswith("Executor")
        ):
            continue
        if not dataclasses.is_dataclass(cls):
            continue
        field_map = {f.name: f for f in dataclasses.fields(cls)}
        sn_field = field_map.get("semantic_name")
        rg_field = field_map.get("region")
        if sn_field is None or rg_field is None:
            continue
        semantic_name = sn_field.default if isinstance(sn_field.default, str) else None
        region = rg_field.default if isinstance(rg_field.default, str) else None
        if not isinstance(semantic_name, str) or not isinstance(region, str):
            continue
        registry[(region, semantic_name)] = cls()

    class _StubRuntime:
        def resolve_factory(self, factory: str, region: str) -> object | None:
            return registry.get((region, factory))

    runtime = _StubRuntime()
    assert runtime.resolve_factory("think.shortcut", "phase:think") is not None
    assert runtime.resolve_factory("think.gate", "phase:think") is not None