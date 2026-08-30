from __future__ import annotations

import pytest

from lca.contracts.mechanisms import MissingCapabilityError
from lca.plugins.composer.action_authority import build_action_registry_from_authority


class _Handler:
    def __init__(self, *, creatable: bool = True) -> None:
        self.creatable = creatable

    def create(self, _tools, _safe_executor, _transport):
        return object() if self.creatable else None


class _Registry:
    def __init__(self, handlers: dict[str, _Handler]) -> None:
        self._handlers = handlers

    def registered(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def resolve(self, action_type: str):
        return self._handlers.get(action_type)


def _build(*, registry: _Registry, allowed: frozenset[str]):
    return build_action_registry_from_authority(
        tools=object(),
        safe_executor=object(),
        transport=object(),
        handler_registry=registry,
        allowed_actions=allowed,
        forbidden_actions=frozenset(),
    )


def test_action_authority_missing_handler_fails_closed() -> None:
    registry = _Registry({"respond": _Handler()})

    with pytest.raises(
        MissingCapabilityError,
        match="action authority requires registered handlers: use_tool",
    ):
        _build(registry=registry, allowed=frozenset({"respond", "use_tool"}))


def test_action_authority_non_creatable_handler_fails_closed() -> None:
    registry = _Registry({"respond": _Handler(creatable=False)})

    with pytest.raises(
        MissingCapabilityError,
        match="action authority handler cannot create action: respond",
    ):
        _build(registry=registry, allowed=frozenset({"respond"}))


def test_forbidden_action_is_not_required_from_registry() -> None:
    registry = _Registry({"respond": _Handler()})

    result = build_action_registry_from_authority(
        tools=object(),
        safe_executor=object(),
        transport=object(),
        handler_registry=registry,
        allowed_actions=frozenset({"respond", "use_tool"}),
        forbidden_actions=frozenset({"use_tool"}),
    )

    assert result.is_registered("respond")
    assert not result.is_registered("use_tool")
