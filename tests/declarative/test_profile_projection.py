"""Tests for the immutable Profile projection seam."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, cast

import pytest

from lca.harness.plugin_api import EffectClass, PluginDefinition, PluginKind
from lca.harness.plugin_spec_projection import native_spec_from_declaration
from lca.harness.profile.projection import ResolvedProfileProjection
from lca.harness.profile.resolve import ResolvedPlugin, ResolvedProfile


async def _setup(*_args: object, **_kwargs: object) -> None:
    """Minimal declaration carrier; this fixture never executes setup."""


class TestResolvedProfileProjection:
    def test_build_takes_a_deeply_immutable_snapshot_of_nested_facts(self) -> None:
        control = [{"slot": "act.authorize", "authority": ["cap.approve"]}]
        setup_meta = {"control": control, "owner": {"kind": "unique"}}
        _setup.meta = setup_meta  # type: ignore[attr-defined]

        raw_config: dict[str, Any] = {
            "retry": {"delays": [1, 5]},
            "enabled": True,
        }
        projection = ResolvedProfileProjection.build(_resolved_profile(config=raw_config))
        plugin = projection.plugins[0]

        metadata = projection.metadata_for(plugin)
        configuration = projection.configuration_for(plugin)

        # Mutating the declaration after compilation must not alter the compiled
        # read model.  A projection is a plan-fact snapshot, not a shallow view.
        control[0]["slot"] = "act.execute"
        control[0]["authority"].append("cap.execute")
        raw_config["retry"]["delays"].append(30)
        raw_config["enabled"] = False

        assert metadata["control"][0]["slot"] == "act.authorize"
        assert metadata["control"][0]["authority"] == ["cap.approve"]
        assert configuration["retry"]["delays"] == [1, 5]
        assert configuration["enabled"] is True

        with pytest.raises(TypeError):
            cast("dict[str, object]", metadata["control"][0])["slot"] = "act.execute"
        with pytest.raises(TypeError):
            cast("list[str]", metadata["control"][0]["authority"]).append("cap.execute")
        with pytest.raises(TypeError):
            cast("dict[str, object]", configuration["retry"])["delays"] = ()
        with pytest.raises(TypeError):
            cast("list[int]", configuration["retry"]["delays"]).append(30)


def _resolved_profile(*, config: dict[str, Any]) -> ResolvedProfile:
    definition = PluginDefinition(
        Config=None,
        setup=_setup,
        spec=native_spec_from_declaration(
            plugin_id="projection.fixture",
            config_cls=None,
            provides=("cap.fixture",),
            requires=(),
            implements=(),
            layer="L0",
            kind=PluginKind.PRIMITIVE,
            effects=frozenset({EffectClass.NONE}),
            test_suite="tests/harness/test_profile_projection.py",
            functional_group=None,
            module="tests.fixture.projection",
        ),
        description="projection fixture",
    )
    plugin = ResolvedPlugin(
        id=definition.spec.id,
        module="tests.fixture.projection",
        definition=definition,
        config=config,
        config_sources={},
        disabled=False,
        source="tests/fixture",
        index=0,
    )
    return ResolvedProfile(
        profile_path="tests/fixture.yaml",
        bundles=(),
        plugins=(plugin,),
        dag_edges=(),
        manifest_hash="fixture",
        env_refs=(),
        fallback_policy=MappingProxyType({}),
    )
