"""计划绑定能力解析适配器的接缝测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.perceive.capability_plan import ProviderBinding
from lca.plugins.composer.composition.capability_resolution import (
    CapabilityResolutionError,
    ScopeCapabilityResolver,
)


class _RecordingScope:
    """记录 lookup 顺序的最小已启动 scope 替身。"""

    def __init__(self, capabilities: dict[str, object]) -> None:
        self._capabilities = capabilities
        self.lookups: list[str] = []

    def inject(self, key: str) -> object:
        self.lookups.append(key)
        if key not in self._capabilities:
            raise KeyError(key)
        return self._capabilities[key]


def test_provider_binding_resolves_through_its_explicit_scope_key() -> None:
    """Provider binding exposes the one scope key selected during plan compilation."""

    registry = object()
    scope = _RecordingScope({"tools": registry})
    binding = ProviderBinding(
        capability="tools.bash[default]",
        resolution_key="tools",
        owner_plugin="tools-provider",
    )

    resolved = ScopeCapabilityResolver.from_scope(scope).require_provider_binding(binding)

    assert resolved is registry
    assert scope.lookups == ["tools"]


def test_provider_binding_does_not_infer_a_registry_key_at_runtime() -> None:
    """An unavailable explicit key must not fall back to a capability namespace."""

    scope = _RecordingScope({"tools": object()})
    binding = ProviderBinding(
        capability="tools.bash[default]",
        resolution_key="tools.bash[default]",
        owner_plugin="tools-provider",
    )

    with pytest.raises(CapabilityResolutionError, match="resolution key"):
        ScopeCapabilityResolver.from_scope(scope).require_provider_binding(binding)

    assert scope.lookups == ["tools.bash[default]"]


def test_declared_capability_snapshot_uses_compiled_provider_bindings() -> None:
    """运行时消费者只通过计划声明的解析键闭合所需能力。"""

    reducer = object()
    tools = object()
    scope = _RecordingScope({"runtime.reducer": reducer, "tools": tools})
    bindings = (
        ProviderBinding(
            capability="reducer",
            resolution_key="runtime.reducer",
            owner_plugin="reducer-provider",
            required_in_production=True,
        ),
        ProviderBinding(
            capability="tools.bash[default]",
            resolution_key="tools",
            owner_plugin="tools-provider",
        ),
    )

    resolved = ScopeCapabilityResolver.from_scope(scope).require_declared_capabilities(
        bindings,
        ("tools.bash[default]", "reducer"),
    )

    assert resolved == {"reducer": reducer, "tools.bash[default]": tools}
    assert scope.lookups == ["runtime.reducer", "tools"]


def test_declared_capability_snapshot_rejects_missing_or_ambiguous_plan_bindings() -> None:
    """声明校验必须在首个 scope 查找前拒绝不完整或并行的计划事实。"""

    scope = _RecordingScope({"runtime.reducer": object()})
    resolver = ScopeCapabilityResolver.from_scope(scope)

    with pytest.raises(CapabilityResolutionError, match="does not declare"):
        resolver.require_declared_capabilities((), ("reducer",))

    with pytest.raises(CapabilityResolutionError, match="multiple provider bindings"):
        resolver.require_declared_capabilities(
            (
                ProviderBinding(
                    capability="reducer",
                    resolution_key="runtime.reducer",
                    owner_plugin="reducer-provider-a",
                    required_in_production=True,
                ),
                ProviderBinding(
                    capability="reducer",
                    resolution_key="runtime.reducer",
                    owner_plugin="reducer-provider-b",
                    required_in_production=True,
                ),
            ),
            ("reducer",),
        )

    assert scope.lookups == []


def test_exact_composer_lookup_never_degrades_to_a_namespace_root() -> None:
    """Composer 是完整声明能力；根键存在也不能掩盖缺失的具体 composer。"""

    scope = _RecordingScope({"composer": object()})

    with pytest.raises(CapabilityResolutionError, match=r"composer\.brain"):
        ScopeCapabilityResolver.from_scope(scope).require_exact("composer.brain")

    assert scope.lookups == ["composer.brain"]


def test_exact_binding_snapshot_is_deterministic_and_deduplicated() -> None:
    """计划消费者获得稳定快照，不依赖 set 的迭代顺序或重复声明。"""

    perceive = object()
    think = object()
    scope = _RecordingScope(
        {
            "phase.perceive.standard": perceive,
            "phase.think.standard": think,
        }
    )

    bindings = ScopeCapabilityResolver.from_scope(scope).require_exact_bindings(
        ("phase.think.standard", "phase.perceive.standard", "phase.think.standard")
    )

    assert tuple(bindings) == ("phase.perceive.standard", "phase.think.standard")
    assert bindings == {"phase.perceive.standard": perceive, "phase.think.standard": think}
    assert scope.lookups == ["phase.perceive.standard", "phase.think.standard"]


def test_exact_binding_snapshot_fails_before_a_partial_mapping_can_escape() -> None:
    """任何计划声明缺失时，调用方不会收到可误用的局部能力闭包。"""

    scope = _RecordingScope({"phase.perceive.standard": object()})

    with pytest.raises(CapabilityResolutionError, match=r"phase\.think\.standard"):
        ScopeCapabilityResolver.from_scope(scope).require_exact_bindings(
            ("phase.perceive.standard", "phase.think.standard")
        )

    assert scope.lookups == ["phase.perceive.standard", "phase.think.standard"]


def test_runtime_assembly_uses_the_shared_scope_adapter_for_all_plan_reads() -> None:
    """运行时闭合与阶段执行器均不得绕开统一的计划能力接缝。"""

    runtime_assembly = (
        Path(__file__).resolve().parents[2] / "lca/plugins/composer/runtime/runtime_assembly.py"
    ).read_text(encoding="utf-8")
    runtime_capabilities = (
        Path(__file__).resolve().parents[2]
        / "lca/plugins/composer/runtime/runtime_capabilities.py"
    ).read_text(encoding="utf-8")

    assert "resolve_runtime_capabilities" in runtime_assembly
    assert "require_declared_capabilities(" in runtime_capabilities
    assert "require_exact_bindings(capabilities)" in runtime_capabilities
    assert "require_capability(" not in runtime_assembly
    assert "require_capability(" not in runtime_capabilities
    assert 'getattr(scope, "inject"' not in runtime_capabilities


def test_scope_without_inject_is_rejected_at_the_adapter_seam() -> None:
    """计划绑定只接受已启动且提供注入操作的 scope。"""

    with pytest.raises(CapabilityResolutionError, match="inject"):
        ScopeCapabilityResolver.from_scope(object())
