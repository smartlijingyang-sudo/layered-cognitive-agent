"""Tests for the deep runnable-assembly module used by CognitiveRunDriver."""

from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import cast

from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.session.run_mode import RunModeRegistryProtocol
from lca.infrastructure.observability import BoundObservability
from lca.plugins.transport.webserver.handlers.runs.lifecycle.runnable_assembly import (
    CognitiveRunnableAssembler,
    RunnableAssemblyRequest,
    RunnableBuildRequest,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession


class _Resolver:
    def __init__(self, llm: LLMAdapter) -> None:
        self.llm = llm
        self.calls = 0

    def resolve(self) -> LLMAdapter:
        self.calls += 1
        return self.llm


class _Adapter:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[RunnableBuildRequest] = []

    async def build(self, request: RunnableBuildRequest) -> object:
        self.requests.append(request)
        return self.result


class _Registry:
    def __init__(self, adapter: _Adapter) -> None:
        self.adapter = adapter
        self.modes: list[str] = []

    def resolve(self, mode: str) -> _Adapter:
        self.modes.append(mode)
        return self.adapter


def _request(*, mode: str, resolver: _Resolver) -> RunnableAssemblyRequest:
    return RunnableAssemblyRequest(
        session=cast("RunSession", object()),
        question="test question",
        mode=mode,
        observability=cast("BoundObservability", object()),
        bindings=None,
        scope=None,
        llm_resolver=resolver,
    )


class TestCognitiveRunnableAssembler(unittest.IsolatedAsyncioTestCase):
    def test_requires_one_declared_mode_registry(self) -> None:
        """Generic assembly cannot silently create mode fallback policy."""

        constructor = cast("Callable[..., CognitiveRunnableAssembler]", CognitiveRunnableAssembler)
        with self.assertRaisesRegex(TypeError, "missing 1 required keyword-only argument"):
            constructor()

    async def test_delegates_production_mode_selection_to_registry(self) -> None:
        llm = cast("LLMAdapter", object())
        resolver = _Resolver(llm)
        selected_result = object()
        selected = _Adapter(selected_result)
        registry = _Registry(selected)
        assembler = CognitiveRunnableAssembler(
            mode_registry=cast("RunModeRegistryProtocol", registry)
        )

        result = await assembler.assemble(_request(mode="research", resolver=resolver))

        self.assertIs(result, selected_result)
        self.assertEqual(registry.modes, ["research"])
        self.assertEqual(len(selected.requests), 1)


if __name__ == "__main__":
    unittest.main()
