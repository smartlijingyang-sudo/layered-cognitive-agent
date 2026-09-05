"""title_llm_provider plugin 测试(ADR-0188,DSH session-title-llm + first-prompt 合体)。

覆盖契约:

- 无 LLM capability 时 ``generate`` 上抛(由 title_service contained,回退保留)
- 有 fake LLM capability 时正确构造 prompt 并返回 ``{title, message_seqs, model}``
- 超时路径:``config.timeout_ms`` 经 ``asyncio.wait_for`` 上抛 ``TimeoutError``
- provider 形状(id / automatic / generate)与 plugin 装配(经 ``session.title``
  capability 注册;服务缺席时只 provide 不注册)

fake ctx 为最小 stub PluginContext(provide + soft_get);``asyncio_mode=auto``。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from lca.contracts.models.core.llm import LLMResponse
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.title_llm_provider.title_llm_provider import (
    PROVIDER_ID,
    Config,
    FirstPromptTitleProvider,
    build_title_prompt,
    setup,
)
from lca.plugins.session.title_service.title_service import SessionTitleService


class FakeLlm:
    """``LLMAdapter`` 形态 fake:``complete(prompt, **kwargs) -> LLMResponse``。"""

    def __init__(
        self,
        text: str = "Generated Title",
        model: str = "fake-model",
        *,
        delay: float = 0.0,
    ) -> None:
        self.text = text
        self.model = model
        self.delay = delay
        self.prompts: list[str] = []
        self.kwargs: list[dict[str, Any]] = []

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.prompts.append(prompt)
        self.kwargs.append(dict(kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        return LLMResponse(text=self.text, model=self.model)


class _Message:
    """duck-typed 用户消息(对位 title_service 的 TitleUserMessage)。"""

    def __init__(self, seq: int, text: str) -> None:
        self.seq = seq
        self.text = text


def _fake_ctx(bindings: dict[str, Any]) -> Any:
    """最小 stub PluginContext:provide + soft_get。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            return bindings.get(key)

    return _Ctx()


# ── prompt 构造 ───────────────────────────────────────────────────────


def test_build_title_prompt_frames_instruction_and_json_messages() -> None:
    prompt = build_title_prompt(5, [{"seq": 3, "text": "fix the login bug"}])

    assert "concise title" in prompt
    assert "about 5 words" in prompt
    assert '[{"seq": 3, "text": "fix the login bug"}]' in prompt


def test_build_title_prompt_keeps_non_ascii_text() -> None:
    prompt = build_title_prompt(5, [{"seq": 0, "text": "修复登录缺陷"}])

    assert "修复登录缺陷" in prompt


def test_config_rejects_unknown_keys_and_bad_values() -> None:
    with pytest.raises(ValidationError):
        Config(unknown=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Config(target_words=0)
    with pytest.raises(ValidationError):
        Config(timeout_ms=0)


# ── generate ──────────────────────────────────────────────────────────


async def test_generate_without_llm_capability_raises() -> None:
    """无 LLM capability:generate 上抛,由 title_service contained(回退保留)。"""
    provider = FirstPromptTitleProvider(None)

    with pytest.raises(RuntimeError, match="llm capability"):
        await provider.generate(None, [_Message(0, "hi")], asyncio.Event())


async def test_generate_requires_at_least_one_message() -> None:
    provider = FirstPromptTitleProvider(FakeLlm())

    with pytest.raises(ValueError, match="at least one source message"):
        await provider.generate(None, [], asyncio.Event())


async def test_generate_rejects_malformed_message_shape() -> None:
    provider = FirstPromptTitleProvider(FakeLlm())

    with pytest.raises(ValueError, match="seq:int and text:str"):
        await provider.generate(None, [{"seq": True, "text": "x"}], asyncio.Event())


async def test_generate_returns_title_seqs_and_model() -> None:
    llm = FakeLlm(text="Quantum Fix", model="m-1")
    provider = FirstPromptTitleProvider(llm, Config(target_words=7))

    result = await provider.generate(None, [_Message(3, "fix quantum bug")], asyncio.Event())

    assert result == {"title": "Quantum Fix", "message_seqs": [3], "model": "m-1"}
    assert len(llm.prompts) == 1
    assert "about 7 words" in llm.prompts[0]
    assert "fix quantum bug" in llm.prompts[0]


async def test_generate_accepts_mapping_shaped_messages() -> None:
    provider = FirstPromptTitleProvider(FakeLlm())

    result = await provider.generate(None, [{"seq": 1, "text": "mapped"}], asyncio.Event())

    assert result["message_seqs"] == [1]


async def test_generate_passes_model_override_to_llm() -> None:
    llm = FakeLlm()
    provider = FirstPromptTitleProvider(llm, Config(model="custom-model"))

    await provider.generate(None, [_Message(0, "x")], asyncio.Event())

    assert llm.kwargs[0] == {"model": "custom-model"}


async def test_generate_omits_model_kwarg_without_override() -> None:
    llm = FakeLlm()
    provider = FirstPromptTitleProvider(llm)

    await provider.generate(None, [_Message(0, "x")], asyncio.Event())

    assert llm.kwargs[0] == {}


async def test_generate_times_out() -> None:
    llm = FakeLlm(delay=0.2)
    provider = FirstPromptTitleProvider(llm, Config(timeout_ms=1))

    with pytest.raises(TimeoutError):
        await provider.generate(None, [_Message(0, "x")], asyncio.Event())


async def test_generate_empty_model_yields_none() -> None:
    provider = FirstPromptTitleProvider(FakeLlm(model=""))

    result = await provider.generate(None, [_Message(0, "x")], asyncio.Event())

    assert result["model"] is None


def test_provider_shape_matches_contract() -> None:
    provider = FirstPromptTitleProvider(None)

    assert provider.id == PROVIDER_ID
    assert provider.automatic == "first-prompt"
    assert callable(provider.generate)


# ── plugin 装配 ───────────────────────────────────────────────────────


async def test_setup_registers_provider_into_title_service() -> None:
    service = SessionTitleService()
    ctx = _fake_ctx({"session.title": service, "llm": FakeLlm()})

    await setup.setup(ctx, Config())

    provided = ctx.provided["session.title.provider"]
    assert isinstance(provided, FirstPromptTitleProvider)
    # 已注册:重复注册被服务拒绝(行为断言,不触碰私有面)
    with pytest.raises(ValueError, match="already registered"):
        service.register_provider(FirstPromptTitleProvider(None))


async def test_setup_without_title_service_still_provides() -> None:
    ctx = _fake_ctx({"llm": FakeLlm()})

    await setup.setup(ctx, Config())

    assert isinstance(ctx.provided["session.title.provider"], FirstPromptTitleProvider)


async def test_setup_without_llm_capability_registers_deferred_provider() -> None:
    service = SessionTitleService()
    ctx = _fake_ctx({"session.title": service})

    await setup.setup(ctx, Config())

    provider = ctx.provided["session.title.provider"]
    with pytest.raises(RuntimeError, match="llm capability"):
        await provider.generate(None, [_Message(0, "x")], asyncio.Event())


async def test_end_to_end_provider_title_supersedes_fallback() -> None:
    """注册 → 首条用户消息 → 回退立即落 → LLM 标题取代(contained 全链)。"""
    store = SessionStore()
    service = SessionTitleService()
    service.attach_to_store(store)
    llm = FakeLlm(text="E2E Title")
    await setup.setup(_fake_ctx({"session.title": service, "llm": llm}), Config())

    session = store.create("e2e")
    session.append(
        "message.accepted.v1",
        {"message_id": "m1", "role": "user", "content_ref": "end to end prompt"},
    )
    await service.drain()

    assert service.get(session) == "E2E Title"
    assert llm.prompts[0].count("end to end prompt") == 1


async def test_end_to_end_missing_llm_keeps_fallback() -> None:
    store = SessionStore()
    service = SessionTitleService()
    service.attach_to_store(store)
    await setup.setup(_fake_ctx({"session.title": service}), Config())

    session = store.create("e2e-no-llm")
    session.append(
        "message.accepted.v1",
        {"message_id": "m1", "role": "user", "content_ref": "prompt without llm capability"},
    )
    await service.drain()

    assert service.get(session) == "prompt without llm capability"
