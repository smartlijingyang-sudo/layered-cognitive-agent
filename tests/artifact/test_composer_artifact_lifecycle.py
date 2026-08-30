"""Artifact lifecycle integration for Creator-time Composer operations."""

from __future__ import annotations

from cordis import Context

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.mechanisms.composition import PluginFactory
from lca.plugins.providers.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)


def _factory() -> object:
    return object()


def test_mount_activates_and_unmount_retires_artifact() -> None:
    composer = CordisComposer(Context(), invariant_checker=build_default_invariant_checker())
    factory = PluginFactory(
        name="artifact-lifecycle-test",
        factory=_factory,
        plugin_meta={
            "name": "artifact-lifecycle-test",
            "layer": "behavior",
            "implements": ["Plugin"],
            "capabilities": ["tool.test"],
            "side_effects": "none",
            "policy_class": "execute",
            "test_suite": "tests/artifact/test_composer_artifact_lifecycle.py",
        },
    )

    mount = composer.mount(factory, caller_grant=("tool.test",))
    active = composer.artifact_for(factory.name)

    assert mount.context_key == "plugin:artifact-lifecycle-test"
    assert active is not None
    assert active.state is ArtifactState.ACTIVE
    assert active.grants == ("tool.test",)
    assert active.revision_digest

    composer.unmount(factory.name)

    assert composer.artifact_for(factory.name) is None
    retired = composer.retired_artifact_for(factory.name)
    assert retired is not None
    assert retired.state is ArtifactState.RETIRED
    assert retired.revision_digest == active.revision_digest
