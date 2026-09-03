"""Substitution gates for simple-memory admission and compaction policies."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.cognition.memory.layered_retrieval_policy import LayeredRetrievalPolicy
from lca.cognition.memory.simple_memory import SimpleMemorySystem
from lca.contracts.capabilities import (
    MEMORY_COMPACTION_POLICY,
    MEMORY_RETRIEVAL_POLICY,
    MEMORY_WRITE_POLICY,
)
from lca.harness.profile.boot import boot_profile
from lca.harness.profile.resolve import resolve_profile

REPO = Path(__file__).resolve().parents[2]


def test_memory_provider_declares_both_policy_dependencies() -> None:
    """The selected provider cannot silently instantiate policy defaults in production."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}
    provider = by_id["lca-memory-provider"]

    assert MEMORY_WRITE_POLICY.key in provider.required_capability_keys
    assert MEMORY_COMPACTION_POLICY.key in provider.required_capability_keys
    assert MEMORY_RETRIEVAL_POLICY.key in provider.required_capability_keys
    assert (
        MEMORY_WRITE_POLICY.key in by_id["lca-memory-write-policy-simple"].provided_capability_keys
    )
    assert (
        MEMORY_COMPACTION_POLICY.key
        in by_id["lca-memory-compaction-policy-simple"].provided_capability_keys
    )
    assert MEMORY_RETRIEVAL_POLICY.key in by_id["lca-retrieval-layered"].provided_capability_keys


def test_booted_memory_service_uses_profile_selected_policy_instances() -> None:
    """The memory factory binds resolved policies once and disallows call-time overrides."""

    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))
    memory_service = ctx.inject("memory")
    memory = memory_service.create()

    assert isinstance(memory, SimpleMemorySystem)
    assert memory.policy is ctx.inject(MEMORY_WRITE_POLICY.key)
    assert memory.compaction is ctx.inject(MEMORY_COMPACTION_POLICY.key)
    assert isinstance(memory.retrieval, LayeredRetrievalPolicy)
    assert ctx.inject(MEMORY_RETRIEVAL_POLICY.key) is LayeredRetrievalPolicy
    with pytest.raises(TypeError, match="selected by the active profile"):
        memory_service.create(policy=object())
    with pytest.raises(TypeError, match="selected by the active profile"):
        memory_service.create(retrieval=object())


def test_memory_provider_does_not_register_the_concrete_class_directly() -> None:
    """Factory closure, rather than constructor defaults, owns production policy injection."""

    source = (REPO / "lca/plugins/memory/memory_provider.py").read_text(encoding="utf-8")
    assert 'register("simple", SimpleMemorySystem)' not in source
    assert "build_simple_memory" in source
