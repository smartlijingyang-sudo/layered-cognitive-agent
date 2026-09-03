from __future__ import annotations

import pytest

from lca.plugins.collaboration.modes.cognitive import _cognitive_driver_factory
from lca.contracts.capabilities import RUN_MODE_REGISTRY
from lca.contracts.mechanisms.capability import MissingCapabilityError


class _Context:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def inject(self, key: str) -> object:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


def test_cognitive_driver_factory_rejects_missing_mode_registry() -> None:
    with pytest.raises(MissingCapabilityError):
        _cognitive_driver_factory(_Context({}))


def test_cognitive_driver_factory_uses_declared_mode_registry() -> None:
    mode_registry = object()

    driver = _cognitive_driver_factory(_Context({RUN_MODE_REGISTRY.key: mode_registry}))

    assert driver._assembler._mode_registry is mode_registry
