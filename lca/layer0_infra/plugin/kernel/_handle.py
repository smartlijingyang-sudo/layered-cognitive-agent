"""PluginHandle — runtime state for one loaded plugin entry (Cordis Fiber)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from lca.layer0_infra.plugin.kernel._disposable import DisposableList
from lca.layer0_infra.plugin.kernel._effect_meta import EffectMeta
from lca.layer0_infra.plugin.kernel._spec import PluginSpec
from lca.layer0_infra.plugin.kernel._types import Cleanup, PluginState


@dataclass
class PluginHandle:
    """One entry's runtime state. Lifecycle state machine + effect accumulator."""

    entry_id: str
    spec: PluginSpec
    config: Any
    injected: tuple[str, ...]
    desired: bool = True
    state: PluginState = PluginState.PENDING
    error: BaseException | None = None

    # ── Ownership tracking ────────────────────────────────
    effects: list[tuple[Cleanup, EffectMeta | None]] = field(default_factory=list)
    provided_services: set[str] = field(default_factory=set)
    listener_tokens: set[tuple[str, int]] = field(default_factory=set)
    disposables: DisposableList = field(default_factory=DisposableList)

    # ── Async lifecycle ───────────────────────────────────
    inertia: asyncio.Task[None] | None = None

    # ── Internal ──────────────────────────────────────────
    _accessors: dict[str, dict[str, Any]] = field(default_factory=dict)
    _entry: Any = None

    @property
    def dependencies(self) -> tuple[str, ...]:
        return self.injected

    def get_effects_meta(self) -> list[EffectMeta]:
        return [meta for _, meta in self.effects if meta is not None]

    async def await_settled(self) -> PluginHandle:
        while self.inertia is not None:
            await self.inertia
        if self.error is not None:
            raise self.error
        return self
