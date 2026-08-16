"""Registry for named, capability-declaring subagent implementations."""

from __future__ import annotations

from lca.contracts.harness.subagent import SubagentSpec


class SubagentRegistry:
    """Registers subagent types and resolves requests by capability."""

    def __init__(self) -> None:
        self._specs: dict[str, SubagentSpec] = {}

    def register(self, spec: SubagentSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"subagent already registered: {spec.name}")
        if spec.capabilities.max_delegation_depth < 0:
            raise ValueError("max_delegation_depth must be non-negative")
        self._specs[spec.name] = spec

    def get(self, name: str) -> SubagentSpec:
        try:
            return self._specs[name]
        except KeyError as error:
            raise KeyError(f"unknown subagent: {name}") from error

    def find(self, required_capabilities: frozenset[str]) -> tuple[SubagentSpec, ...]:
        return tuple(
            spec
            for spec in self._specs.values()
            if required_capabilities <= spec.capabilities.capabilities
        )
