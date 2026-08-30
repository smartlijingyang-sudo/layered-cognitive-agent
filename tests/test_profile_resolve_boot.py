"""ADR-0061 — resolve_profile / boot_resolved_profile contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from lca.harness.plugin_api import (
    AuditedPluginContext,
    EffectClass,
    PluginContext,
    PluginDefinition,
    PluginKind,
    UndeclaredInteractionError,
)
from lca.harness.plugin_spec_projection import native_spec_from_declaration
from lca.harness.profile.boot import (
    _boot_plugin,
    boot_entries,
    boot_profile,
    boot_resolved_profile,
    load_profile_entries,
)
from lca.harness.profile.boot_products import (
    compiled_plan_from_scope,
    profile_boot_products_from_scope,
    resolved_profile_from_scope,
)
from lca.harness.profile.resolve import (
    ProfileResolveError,
    dump_resolved,
    resolve_entries,
    resolve_profile,
)

DEFAULT = Path("profiles/web-standard.yaml")


def test_resolve_default_profile_is_stable() -> None:
    a = resolve_profile(DEFAULT)
    b = resolve_profile(DEFAULT)
    assert a.manifest_hash == b.manifest_hash
    assert len(a.plugins) >= 40
    assert any(e[0] == "perceive" and e[1] == "sensor.clock" for e in a.dag_edges)


def test_resolved_profile_is_a_frozen_resolution_fact() -> None:
    """Profile 解析产物不得反向持有计划编译策略或无类型捷径。"""

    resolved = resolve_profile(DEFAULT)
    source = Path("lca/harness/profile/resolve.py").read_text(encoding="utf-8")

    assert not hasattr(resolved, "compile_plan")
    assert "harness.profile.plan_compiler" not in source


def test_plugin_definition_with_config_preserves_manifest_declarations() -> None:
    """Immutable config enrichment must not erase declaration metadata."""

    async def setup(_ctx: PluginContext, _config: BaseModel) -> None:
        return None

    class Config(BaseModel):
        enabled: bool = True

    definition = PluginDefinition(
        Config=None,
        setup=setup,
        spec=native_spec_from_declaration(
            plugin_id="test.definition-enrichment",
            config_cls=None,
            provides=("provided",),
            requires=("required",),
            implements=("Contract",),
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            effects=frozenset({EffectClass.NONE}),
            test_suite=__name__,
            functional_group=None,
            module=__name__,
        ),
        description="preserve declarations",
        relations=({"kind": "requires", "target": "required"},),
    )

    enriched = definition.with_config(Config)

    assert enriched.Config is Config
    assert enriched.spec.configuration.schema == f"{Config.__module__}.{Config.__name__}"
    assert enriched.spec.provides == definition.spec.provides
    assert enriched.relations == definition.relations
    assert enriched.setup is definition.setup
    assert enriched.provided_capability_keys == definition.provided_capability_keys


def test_resolve_orders_perceive_before_sensors() -> None:
    resolved = resolve_profile(DEFAULT)
    ids = [p.id for p in resolved.plugins if not p.disabled]
    assert ids.index("perceive") < ids.index("sensor.clock")
    assert ids.index("gates") < ids.index("gate.repeat-tool-call")
    assert ids.index("lca-reasoner-prompt") < ids.index("lca-brain-simple")


def test_programmatic_entries_reuse_profile_resolve_semantics() -> None:
    """The compatibility input must expose the same immutable plugin graph."""

    resolved = resolve_profile(DEFAULT)
    programmatic = resolve_entries(load_profile_entries(DEFAULT))

    assert [plugin.id for plugin in programmatic.plugins] == [
        plugin.id for plugin in resolved.plugins
    ]
    assert programmatic.dag_edges == resolved.dag_edges
    assert all(
        plugin.source.startswith("<programmatic entries>") for plugin in programmatic.plugins
    )


def test_load_profile_entries_stays_on_the_input_adapter_side_of_resolve(
    tmp_path: Path,
) -> None:
    """Fixture entries preserve source shape without importing a plugin module."""

    bundle = tmp_path / "fixture.yaml"
    bundle.write_text(
        "entries:\n"
        "  - id: fixture.invalid\n"
        "    name: fixture_invalid\n"
        "    $module: fixture_plugins.not_importable\n"
        "    config:\n"
        "      nested:\n"
        "        from_bundle: true\n"
    )
    profile = tmp_path / "fixture-profile.yaml"
    profile.write_text(
        "bundles:\n"
        "  - fixture.yaml\n"
        "patch:\n"
        "  - id: fixture.invalid\n"
        "    config:\n"
        "      nested:\n"
        "        from_profile: true\n"
    )

    entries = load_profile_entries(profile)

    assert entries == [
        {
            "id": "fixture.invalid",
            "name": "fixture_invalid",
            "$module": "fixture_plugins.not_importable",
            "config": {"nested": {"from_bundle": True, "from_profile": True}},
        }
    ]
    assert not any(key.startswith("_") for key in entries[0])
    entries[0]["config"]["nested"]["from_profile"] = False
    assert load_profile_entries(profile)[0]["config"]["nested"]["from_profile"] is True

    with pytest.raises(ModuleNotFoundError, match="fixture_plugins"):
        resolve_entries(entries)


def test_programmatic_entries_fail_for_missing_requires_during_resolve() -> None:
    """A fixture cannot defer a malformed Manifest graph until a later run."""

    entries = [
        entry for entry in load_profile_entries(DEFAULT) if entry["id"] != "lca-memory-service"
    ]

    with pytest.raises(ProfileResolveError, match="memory"):
        resolve_entries(entries)


def test_dump_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-value-should-not-leak")
    resolved = resolve_profile(DEFAULT)
    dumped = dump_resolved(resolved, redact=True)
    blob = str(dumped)
    assert "sk-secret-value-should-not-leak" not in blob
    resolver = next(p for p in dumped["plugins"] if p["id"] == "lca-llm-resolver")
    assert resolver["config"].get("api_key") in {None, "***"}


def test_disable_memory_fails_at_resolve(tmp_path: Path) -> None:
    profile = tmp_path / "no-memory.yaml"
    profile.write_text(
        "bundles:\n"
        "  - bundles/base.yaml\n"
        "  - bundles/web-app.yaml\n"
        "patch:\n"
        "  - id: lca-memory-service\n"
        "    disabled: true\n"
    )
    with pytest.raises(ProfileResolveError, match="memory"):
        resolve_profile(profile)


def test_unknown_config_field_fails(tmp_path: Path) -> None:
    profile = tmp_path / "bad-config.yaml"
    profile.write_text(
        "bundles:\n"
        "  - bundles/base.yaml\n"
        "  - bundles/web-app.yaml\n"
        "patch:\n"
        "  - id: gate.repeat-tool-call\n"
        "    config:\n"
        "      not_a_real_field: 1\n"
    )
    with pytest.raises(ProfileResolveError, match=r"gate\.repeat-tool-call"):
        resolve_profile(profile)


def test_audited_context_hides_raw_container() -> None:
    definition = resolve_profile(DEFAULT).plugins[0].definition
    context = AuditedPluginContext(object(), definition)

    with pytest.raises(AttributeError):
        _ = context._inner  # type: ignore[attr-defined]


def test_audited_context_uses_manifest_declarations_as_one_authorization_seam() -> None:
    """Every audited interaction reports the same declaration-oriented contract."""

    async def setup(_ctx: PluginContext, _config: BaseModel) -> None:
        return None

    definition = PluginDefinition(
        Config=None,
        setup=setup,
        spec=native_spec_from_declaration(
            plugin_id="test.audited-seam",
            config_cls=None,
            provides=("provided",),
            requires=("required",),
            implements=(),
            layer="L0",
            kind=PluginKind.PRIMITIVE,
            effects=frozenset({EffectClass.NONE}),
            test_suite=__name__,
            functional_group=None,
            module=__name__,
        ),
        description="",
    )
    context = AuditedPluginContext(object(), definition)

    with pytest.raises(UndeclaredInteractionError, match=r"provide\('missing'\).*provides"):
        context.provide("missing", object())
    with pytest.raises(UndeclaredInteractionError, match=r"require\('missing'\).*requires"):
        context.require("missing")
    assert not hasattr(context, "inject")


def test_boot_default_profile() -> None:
    ctx = asyncio.run(boot_profile(DEFAULT))
    perceive = ctx.inject("perceive")
    assert [e.id for e in perceive.members()][:2] == ["clock", "workspace-artifacts"]
    gates = ctx.inject("gates")
    assert gates.create("repeat-tool-call") is not None
    brains = ctx.inject("brains")
    assert "default" in brains


def test_boot_resolved_matches_facade() -> None:
    resolved = resolve_profile(DEFAULT)
    ctx = asyncio.run(boot_resolved_profile(resolved))
    assert resolved_profile_from_scope(ctx) is resolved


def test_boot_resolved_preflights_products_before_plugin_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected runtime plan must not enter the Fiber lifecycle seam."""

    events: list[str] = []

    def reject_preflight(_resolved: object) -> object:
        events.append("compile")
        raise ProfileResolveError("preflight rejected")

    async def unexpected_boot(*_args: object, **_kwargs: object) -> object:
        events.append("boot")
        raise AssertionError("plugin lifecycle must not start after preflight failure")

    monkeypatch.setattr(
        "lca.harness.profile.boot.compile_profile_boot_products",
        reject_preflight,
    )
    monkeypatch.setattr("lca.harness.profile.boot._boot_context", unexpected_boot)

    with pytest.raises(ProfileResolveError, match="preflight rejected"):
        asyncio.run(boot_resolved_profile(resolve_profile(DEFAULT)))

    assert events == ["compile"]


def test_boot_entrances_converge_on_one_audited_sequence() -> None:
    """Resolved and programmatic input adapters must not duplicate Fiber boot semantics."""

    source = Path("lca/harness/profile/boot.py").read_text(encoding="utf-8")

    assert source.count("return await _boot_context(") == 2
    assert source.count("await _boot_plugin(") == 1


def test_fiber_boot_executes_audited_setup_once_and_owns_its_disposer() -> None:
    """Fiber is the sole lifecycle owner; boot must not call setup a second time."""

    events: list[str] = []

    async def setup(_ctx: PluginContext, _config: BaseModel) -> None:
        events.append("setup")
        return cast("None", lambda: events.append("dispose"))

    definition = PluginDefinition(
        Config=None,
        setup=setup,
        spec=native_spec_from_declaration(
            plugin_id="test.single-fiber-lifecycle",
            config_cls=None,
            provides=(),
            requires=(),
            implements=(),
            layer="L0",
            kind=PluginKind.PRIMITIVE,
            effects=frozenset({EffectClass.NONE}),
            test_suite=__name__,
            functional_group=None,
            module=__name__,
        ),
        description="Verify one Fiber owns one audited setup execution.",
    )

    async def run() -> None:
        from cordis import Context

        ctx = Context()
        await _boot_plugin(ctx, definition, {})
        assert events == ["setup"]
        await ctx.dispose()

    asyncio.run(run())
    assert events == ["setup", "dispose"]


def test_boot_caches_the_single_validated_runnable_plan() -> None:
    """Every Agent from a production scope must bind the one boot-time plan."""

    ctx = asyncio.run(boot_profile(DEFAULT))

    products = profile_boot_products_from_scope(ctx)
    assert products is not None
    assert products.resolved_profile is resolved_profile_from_scope(ctx)
    assert products.compiled_run_plan is not None
    assert compiled_plan_from_scope(ctx) is products.compiled_run_plan
    assert compiled_plan_from_scope(ctx) is products.compiled_run_plan
    assert "entries" not in ctx.__dict__


def test_programmatic_boot_attaches_resolved_profile_without_a_compiled_plan() -> None:
    """Fixture boot shares the inspection seam and leaves runtime closure to require()."""

    ctx = asyncio.run(boot_entries(load_profile_entries("profiles/test-minimal.yaml")))

    products = profile_boot_products_from_scope(ctx)
    assert products is not None
    assert products.resolved_profile is resolved_profile_from_scope(ctx)
    assert products.compiled_run_plan is None
    assert "entries" not in ctx.__dict__


def test_boot_test_default_profile_allows_an_inspectable_non_runnable_plan() -> None:
    """Explicit test defaults may boot a partial plugin fixture without production phases."""

    ctx = asyncio.run(boot_profile("profiles/test-minimal.yaml"))

    products = profile_boot_products_from_scope(ctx)
    assert products is not None
    assert products.compiled_run_plan is not None
    assert products.compiled_run_plan.phase_bindings == ()
