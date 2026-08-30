"""Structural checks for the delta handler implementation seam."""

from __future__ import annotations

import inspect

from lca.plugins.providers import delta_handler_registry, delta_handlers


def test_delta_handler_implementations_do_not_own_registry_assembly() -> None:
    """The handler module should expose behavior, not registry composition."""

    source = inspect.getsource(delta_handlers)
    assert "class InMemoryDeltaHandlerRegistry" not in source
    assert "def register_default_delta_handlers" not in source


def test_delta_handler_registry_module_owns_only_registry_composition() -> None:
    """The registry module should not duplicate concrete handler behavior."""

    assert hasattr(delta_handler_registry, "InMemoryDeltaHandlerRegistry")
    assert hasattr(delta_handler_registry, "register_default_delta_handlers")
    source = inspect.getsource(delta_handler_registry)
    assert "class StepDeltaHandler" not in source
    assert "class TurnDeltaHandler" not in source
