"""RA-099: ``register_hook`` fails loud on a runtime without hooks.

The ``else`` branch of the ``isinstance(runtime, HasHooks)`` check used to
silently drop the registration — a "my hook never fires" debug session had
to penetrate the concrete runtime type to find the silent no-op. Now it
raises, naming the runtime type.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lca.agent.cognitive_agent import CognitiveAgent


class _HooksLessRuntime:
    """Minimal runtime stub that does not expose a HookRegistry."""


class _HookedRuntime:
    """Minimal runtime stub exposing a HookRegistry.

    A real ``hooks`` attribute (not a MagicMock auto-attr): ``isinstance``
    against the ``HasHooks`` runtime-checkable protocol does not see through
    MagicMock's dynamic attribute creation.
    """

    def __init__(self) -> None:
        self.hooks = MagicMock()


def _agent(runtime: object) -> CognitiveAgent:
    return CognitiveAgent(
        runtime=runtime,  # type: ignore[arg-type]
        role_profile=MagicMock(),
        observability=MagicMock(),
    )


def test_register_hook_without_hooks_fails_loud() -> None:
    agent = _agent(_HooksLessRuntime())
    with pytest.raises(TypeError, match="does not implement HasHooks"):
        agent.register_hook("on_start", MagicMock())


def test_register_hook_without_hooks_names_runtime_type() -> None:
    agent = _agent(_HooksLessRuntime())
    with pytest.raises(TypeError, match="_HooksLessRuntime"):
        agent.register_hook("on_start", MagicMock())


def test_register_hook_with_hooks_registers() -> None:
    runtime = _HookedRuntime()
    agent = _agent(runtime)
    hook_fn = MagicMock()
    agent.register_hook("on_start", hook_fn)
    runtime.hooks.register.assert_called_once_with("on_start", hook_fn)
