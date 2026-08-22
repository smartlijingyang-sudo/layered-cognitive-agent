"""Tests for the deep runnable-assembly module used by CognitiveRunDriver."""

from __future__ import annotations

import unittest
from typing import cast

from gateway.runs.runnable_assembly import (
    CognitiveRunnableAssembler,
    RunnableAssemblyRequest,
    RunnableBuildRequest,
)
from gateway.runs.session import RunSession
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.observability import BoundObservability


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
    async def test_selects_registered_mode_adapter(self) -> None:
        llm = cast("LLMAdapter", object())
        resolver = _Resolver(llm)
        selected_result = object()
        selected = _Adapter(selected_result)
        fallback = _Adapter(object())
        assembler = CognitiveRunnableAssembler(adapters={"solo": selected}, fallback=fallback)

        result = await assembler.assemble(_request(mode="solo", resolver=resolver))

        self.assertIs(result, selected_result)
        self.assertEqual(resolver.calls, 1)
        self.assertEqual(len(selected.requests), 1)
        self.assertEqual(fallback.requests, [])
        self.assertIs(selected.requests[0].llm, llm)
        self.assertEqual(selected.requests[0].tools, ())

    async def test_routes_unregistered_mode_to_team_fallback(self) -> None:
        llm = cast("LLMAdapter", object())
        resolver = _Resolver(llm)
        fallback_result = object()
        fallback = _Adapter(fallback_result)
        assembler = CognitiveRunnableAssembler(adapters={}, fallback=fallback)

        result = await assembler.assemble(_request(mode="team", resolver=resolver))

        self.assertIs(result, fallback_result)
        self.assertEqual(resolver.calls, 1)
        self.assertEqual(len(fallback.requests), 1)


if __name__ == "__main__":
    unittest.main()
