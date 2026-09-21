"""Composite execution-environment catalog — aggregates environment providers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
)
from lca.contracts.protocols.runtime.environment import (
    EnvironmentProvider,
)


class CompositeEnvironmentCatalog:
    """Merge providers into one deduplicated, current-marked directory.

    The catalog is the SSOT read model for "what can the agent run on".
    Providers are ordered; the first occurrence of a ``(kind, id)`` pair wins.
    The current environment is always present and flagged ``is_current=True``.
    """

    def __init__(
        self,
        providers: Sequence[EnvironmentProvider] = (),
        *,
        current: ExecutionEnvironment | None = None,
    ) -> None:
        self._providers = list(providers)
        self._current = current

    def list_all(self) -> list[ExecutionEnvironment]:
        seen: set[tuple[EnvironmentKind, str]] = set()
        merged: list[ExecutionEnvironment] = []
        for provider in self._providers:
            for env in provider.list_environments():
                key = (env.kind, env.id)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(self._with_current(env))
        if self._current is not None:
            key = (self._current.kind, self._current.id)
            if key not in seen:
                merged.append(replace(self._current, is_current=True))
        return merged

    def current(self) -> ExecutionEnvironment | None:
        return self._current

    def _with_current(self, env: ExecutionEnvironment) -> ExecutionEnvironment:
        if (
            self._current is not None
            and env.kind == self._current.kind
            and env.id == self._current.id
        ):
            return replace(env, is_current=True)
        return env


__all__ = ["CompositeEnvironmentCatalog"]
