"""Factory-generated composer provider shells stay discoverable and wire the right composer.

RA-008 converged the three near-identical provider modules
(think/brain_provider, perceive/provider, act/body_provider) into one
``_register_composer_plugin(...)`` factory call each. These tests pin the two
things that convergence must not break:

1. the ``@plugin`` discovery mechanism (``definition_from_plugin`` over
   ``module.setup``, exactly what profile resolve consumes) still yields the
   original plugin id / provides key per module;
2. ``setup()`` provides the correct composer instance per plugin id (this was
   previously untested -- only bundle registration items were covered).
"""

from __future__ import annotations

import asyncio
import importlib

from lca.harness.plugin_api import definition_from_plugin
from lca.plugins.composer.act.body_composer import BodyComposer
from lca.plugins.composer.perceive.composer import PerceiveComposer
from lca.plugins.composer.think.brain_composer import BrainComposer

_CASES = (
    (
        "lca.plugins.composer.think.brain_provider",
        "lca-plan-brain-composer",
        "composer.brain",
        BrainComposer,
    ),
    (
        "lca.plugins.composer.act.body_provider",
        "lca-plan-body-composer",
        "composer.body",
        BodyComposer,
    ),
    (
        "lca.plugins.composer.perceive.provider",
        "lca-plan-perceive-composer",
        "composer.perceive",
        PerceiveComposer,
    ),
)


class _RecordingCtx:
    """Minimal PluginContext double: only ``provide`` is exercised by setup."""

    def __init__(self) -> None:
        self.provided: dict[str, object] = {}

    def provide(self, key: str, value: object) -> None:
        self.provided[key] = value


def test_factory_registrations_are_discoverable_with_original_ids() -> None:
    """Discovery still yields the original plugin id and provides key per module."""
    for module_path, plugin_id, provides_key, _composer_cls in _CASES:
        module = importlib.import_module(module_path)
        definition = definition_from_plugin(module.setup, module=module_path)
        assert definition.spec.id == plugin_id
        assert provides_key in definition.provided_capability_keys


def test_setup_provides_correct_composer_instance_per_plugin_id() -> None:
    """setup() provides the matching composer instance under the provides key."""
    for module_path, _plugin_id, provides_key, composer_cls in _CASES:
        module = importlib.import_module(module_path)
        ctx = _RecordingCtx()
        asyncio.run(module.setup.setup(ctx, module.Config()))
        assert provides_key in ctx.provided
        assert isinstance(ctx.provided[provides_key], composer_cls)


def test_observability_descriptors_stay_id_derived() -> None:
    """No information lost: <id>.checked / <id>.served descriptors preserved."""
    for module_path, plugin_id, _provides_key, _composer_cls in _CASES:
        module = importlib.import_module(module_path)
        definition = definition_from_plugin(module.setup, module=module_path)
        assert definition.contract is not None
        descriptors = definition.contract.observability.descriptors
        assert tuple(descriptors) == (f"{plugin_id}.checked", f"{plugin_id}.served")


def test_authority_grants_preserved_per_provider() -> None:
    """perceive keeps context.read; brain/body keep plugin.serve."""
    expected = {
        "lca.plugins.composer.think.brain_provider": ("plugin.serve",),
        "lca.plugins.composer.act.body_provider": ("plugin.serve",),
        "lca.plugins.composer.perceive.provider": ("context.read",),
    }
    for module_path, _plugin_id, _provides_key, _composer_cls in _CASES:
        module = importlib.import_module(module_path)
        definition = definition_from_plugin(module.setup, module=module_path)
        assert definition.contract is not None
        assert tuple(definition.contract.authority.grants) == expected[module_path]
