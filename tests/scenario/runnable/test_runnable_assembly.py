"""Tests for the deep runnable-assembly module used by CognitiveRunDriver."""

from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import cast

from lca.contracts.models.assistant.spec import AssistantBootstrapRefs, AssistantSpec
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.session.run.mode import RunModeRegistryProtocol
from lca.infrastructure.llm_adapter.model_override import ModelOverridingLLMAdapter
from lca.infrastructure.observability import BoundObservability
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    CognitiveRunnableAssembler,
    RunnableAssemblyRequest,
    RunnableBuildRequest,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


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


class _RecordingAdapter:
    """LLMAdapter stub that records kwargs passed to ``complete``."""

    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] = {}

    async def complete(self, prompt: str, **kwargs: object) -> object:
        self.last_kwargs = dict(kwargs)
        return object()

    async def stream(self, prompt: str, **kwargs: object):  # pragma: no cover
        if False:
            yield None


class _FakeSession:
    def __init__(self, assistant_id: str = "") -> None:
        self.assistant_id = assistant_id


class _FakeTools:
    def materialize(self, view: object) -> tuple[()]:
        return ()


class _FakeScope:
    """Minimal Cordis-like scope: serves assistant.catalog + no-op seams."""

    def __init__(self, catalog: object) -> None:
        self._catalog = catalog

    def require(self, key: str) -> object:
        if key == "assistant.catalog":
            return self._catalog
        if key == "tools":
            return _FakeTools()
        if key in {"file_store", "sandbox", "search", "skills"}:
            return object()
        raise KeyError(key)


class _FakeCatalog:
    def __init__(self, spec: AssistantSpec) -> None:
        self._spec = spec

    def get(self, assistant_id: str) -> AssistantSpec:
        return self._spec


def _assistant_spec(*, profile_model: str = "") -> AssistantSpec:
    return AssistantSpec(
        assistant_id="asst_test",
        home_path="/var/lca/assistants/asst_test",
        revision_seq=0,
        template_id="assistant.default",
        profile_name="Test",
        profile_description="test assistant",
        agent_spec=cast("object", object()),  # type: ignore[arg-type]
        bootstrap=AssistantBootstrapRefs(
            soul_digest="sha256:s",
            user_digest="sha256:u",
            agents_digest="sha256:a",
        ),
        skill_ids=(),
        job_ids=(),
        grant_digest="sha256:g",
        tools_policy_digest="sha256:t",
        profile_model=profile_model,
    )


def _request(
    *,
    mode: str,
    resolver: _Resolver,
    scope: object | None = None,
    session: RunSession | None = None,
) -> RunnableAssemblyRequest:
    return RunnableAssemblyRequest(
        session=session or cast("RunSession", object()),
        question="test question",
        mode=mode,
        observability=cast("BoundObservability", object()),
        bindings=None,
        scope=scope,
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

    async def test_assistant_model_override_wraps_llm_and_forwards_model(self) -> None:
        """带 assistant_id + Home model 时，llm 是 ModelOverridingLLMAdapter。"""
        inner = _RecordingAdapter()
        resolver = _Resolver(cast("LLMAdapter", inner))
        selected = _Adapter(object())
        registry = _Registry(selected)
        assembler = CognitiveRunnableAssembler(
            mode_registry=cast("RunModeRegistryProtocol", registry)
        )
        scope = _FakeScope(_FakeCatalog(_assistant_spec(profile_model="asst-model")))
        session = cast("RunSession", _FakeSession(assistant_id="asst_test"))

        await assembler.assemble(
            _request(mode="solo", resolver=resolver, scope=scope, session=session)
        )

        request = selected.requests[0]
        self.assertIsInstance(request.llm, ModelOverridingLLMAdapter)
        await request.llm.complete("hello")
        self.assertEqual(inner.last_kwargs.get("model"), "asst-model")

    async def test_assistant_without_model_keeps_resolver_adapter(self) -> None:
        """assistant_id 非空但 Home 无 model 时，返回 resolver 原始 adapter。"""
        inner = _RecordingAdapter()
        resolver = _Resolver(cast("LLMAdapter", inner))
        selected = _Adapter(object())
        registry = _Registry(selected)
        assembler = CognitiveRunnableAssembler(
            mode_registry=cast("RunModeRegistryProtocol", registry)
        )
        scope = _FakeScope(_FakeCatalog(_assistant_spec(profile_model="")))
        session = cast("RunSession", _FakeSession(assistant_id="asst_test"))

        await assembler.assemble(
            _request(mode="solo", resolver=resolver, scope=scope, session=session)
        )

        request = selected.requests[0]
        self.assertIs(request.llm, inner)
        self.assertNotIsInstance(request.llm, ModelOverridingLLMAdapter)

    async def test_no_assistant_path_keeps_resolver_adapter_untouched(self) -> None:
        """无 assistant_id 路径（I-B8）：llm 必须是 resolver 原始 adapter。"""
        inner = _RecordingAdapter()
        resolver = _Resolver(cast("LLMAdapter", inner))
        selected = _Adapter(object())
        registry = _Registry(selected)
        assembler = CognitiveRunnableAssembler(
            mode_registry=cast("RunModeRegistryProtocol", registry)
        )

        await assembler.assemble(_request(mode="solo", resolver=resolver))

        request = selected.requests[0]
        self.assertIs(request.llm, inner)
        self.assertNotIsInstance(request.llm, ModelOverridingLLMAdapter)


if __name__ == "__main__":
    unittest.main()
