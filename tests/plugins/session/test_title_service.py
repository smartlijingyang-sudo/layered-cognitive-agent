"""SessionTitleService plugin 测试(ADR-0188,DSH session-title 对位)。

覆盖契约:

- 确定性回退:首条合格用户消息 → 立即 append ``source="fallback"`` 标题
- get latest-wins fold;畸形标题事件跳过
- rename:清洗/校验(空/超长拒绝)+ pin 语义(后续用户消息不再自动调度)
- refresh:解除 pin(无 provider 重派回退;有 provider 重新调度)
- provider 注册唯一性(重复注册 ValueError)+ 形状校验
- provider 成功 → ``source="provider"`` 取代回退;失败 → 回退保留(contained)
- revision 取代:新调度 cancel 旧在途,过期完成结果丢弃
- observer 失败 contained:调度异常绝不反噬 Session.append
- 装配:provides session.title、requires session.store、挂 store 活 Session + 未来新 Session

用真 Session(:class:`SessionStore`)+ fake provider;``asyncio_mode=auto``。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import ValidationError

from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.title_service.title_service import (
    TITLE_EVENT_TYPE,
    Config,
    SessionTitleService,
    normalize_title,
    setup,
)

# ── helpers ───────────────────────────────────────────────────────────


class FakeProvider:
    """可控 fake title provider:first-prompt 节奏,支持成功/失败/阻塞。"""

    def __init__(
        self,
        provider_id: str = "fake",
        *,
        title: str = "Provider Title",
        error: Exception | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.id = provider_id
        self.automatic = "first-prompt"
        self.calls: list[Sequence[Any]] = []
        self.signals: list[asyncio.Event] = []
        self._title = title
        self._error = error
        self._gate = gate

    async def generate(
        self,
        session: Any,
        messages: Sequence[Any],
        signal: asyncio.Event,
    ) -> dict[str, Any]:
        del session
        self.calls.append(messages)
        self.signals.append(signal)
        if self._gate is not None:
            await self._gate.wait()
        if self._error is not None:
            raise self._error
        return {"title": self._title, "message_seqs": [messages[0].seq]}


class _CountingProvider:
    """按调用次数返回不同标题的 provider:区分被取代的旧修订与新修订。"""

    def __init__(self, gate: asyncio.Event) -> None:
        self.id = "counting"
        self.automatic = "first-prompt"
        self.calls = 0
        self._gate = gate

    async def generate(
        self,
        session: Any,
        messages: Sequence[Any],
        signal: asyncio.Event,
    ) -> dict[str, Any]:
        del session, signal
        self.calls += 1
        await self._gate.wait()
        return {"title": f"Title {self.calls}", "message_seqs": [messages[0].seq]}


async def _wait_for(condition: Any, max_wait: float = 2.0) -> None:
    """轮询等待条件成立;超时 = 测试失败(避免 drain 挂在阻塞 provider 上)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_wait
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("timed out waiting for title scheduling condition")
        await asyncio.sleep(0.005)


def _make_service(**config: Any) -> tuple[SessionStore, SessionTitleService]:
    store = SessionStore()
    service = SessionTitleService(Config(**config))
    service.attach_to_store(store)
    return store, service


def _append_user_message(session: Any, text: str, *, role: str = "user") -> None:
    session.append(
        "message.accepted.v1",
        {"message_id": f"m-{session.seq}", "role": role, "content_ref": text},
    )


def _title_events(session: Any) -> list[dict[str, Any]]:
    return [event.data for event in session.snapshot_events() if event.type == TITLE_EVENT_TYPE]


def _fake_ctx(bindings: dict[str, Any]) -> Any:
    """最小 stub PluginContext:provide + soft_get(抄 test_persistence_jsonl)。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            return bindings.get(key)

    return _Ctx()


# ── normalize ─────────────────────────────────────────────────────────


def test_normalize_title_strips_ansi_and_collapses_whitespace() -> None:
    assert normalize_title("\x1b[31mred\x1b[0m\n\n  text   here  ") == "red text here"


def test_normalize_title_caps_words_then_bytes() -> None:
    assert normalize_title("one two three four five six seven", max_words=5) == (
        "one two three four five"
    )
    # 40 字节上限截断且不劈开码点(对齐 DSH fallbackSessionTitle)
    assert normalize_title("a" * 100) == "a" * 40
    assert len(normalize_title("中" * 50, max_words=100).encode("utf-8")) <= 40


def test_normalize_title_removes_control_and_directional_characters() -> None:
    assert normalize_title("he\u200bllo\u202eworld\u0007") == "helloworld"


def test_normalize_title_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        normalize_title("x", max_words=0)
    with pytest.raises(ValueError, match="positive integer"):
        normalize_title("x", max_bytes=0)


def test_config_rejects_fallback_exceeding_max_title_bytes() -> None:
    with pytest.raises(ValueError, match="fallback_max_bytes"):
        SessionTitleService(Config(fallback_max_bytes=90, max_title_bytes=80))


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Config(unknown_field=1)  # type: ignore[call-arg]


# ── 确定性回退 ─────────────────────────────────────────────────────────


async def test_first_user_message_appends_fallback_title() -> None:
    store, service = _make_service()
    session = store.create("s-fallback")

    _append_user_message(session, "  Fix   the login bug in the auth module please ")
    await service.drain()

    events = _title_events(session)
    assert len(events) == 1
    assert events[0]["source"] == "fallback"
    assert events[0]["title"] == "Fix the login bug in"
    assert events[0]["message_seqs"] == [0]
    assert service.get(session) == "Fix the login bug in"


async def test_non_user_role_message_does_not_trigger_fallback() -> None:
    store, service = _make_service()
    session = store.create("s-role")

    _append_user_message(session, "system prompt text", role="system")
    await service.drain()

    assert _title_events(session) == []
    assert service.get(session) is None


async def test_whitespace_only_message_is_not_eligible() -> None:
    store, service = _make_service()
    session = store.create("s-blank")

    _append_user_message(session, "   \x1b[0m  ")
    await service.drain()

    assert _title_events(session) == []


async def test_fallback_appended_only_once_when_title_missing() -> None:
    store, service = _make_service()
    session = store.create("s-once")

    _append_user_message(session, "first eligible prompt")
    _append_user_message(session, "second prompt")
    await service.drain()

    assert len(_title_events(session)) == 1


async def test_fallback_skipped_when_title_already_exists() -> None:
    store, service = _make_service()
    session = store.create("s-existing")
    session.append(TITLE_EVENT_TYPE, {"title": "kept", "message_seqs": [], "source": "user"})

    _append_user_message(session, "fresh prompt text")
    await service.drain()

    assert _title_events(session) == [{"title": "kept", "message_seqs": [], "source": "user"}]


# ── get / fold ────────────────────────────────────────────────────────


async def test_get_returns_latest_title_wins() -> None:
    store, service = _make_service()
    session = store.create("s-latest")
    session.append(TITLE_EVENT_TYPE, {"title": "old", "message_seqs": [], "source": "fallback"})
    session.append(TITLE_EVENT_TYPE, {"title": "new", "message_seqs": [], "source": "user"})

    assert service.get(session) == "new"


async def test_get_skips_malformed_title_events() -> None:
    store, service = _make_service()
    session = store.create("s-malformed")
    session.append(TITLE_EVENT_TYPE, {"title": "good", "message_seqs": [], "source": "fallback"})
    session.append(TITLE_EVENT_TYPE, {"title": "", "message_seqs": [], "source": "fallback"})

    assert service.get(session) == "good"


# ── rename / pin ──────────────────────────────────────────────────────


async def test_rename_normalizes_and_appends_user_title() -> None:
    store, service = _make_service()
    session = store.create("s-rename")

    service.rename(session, "  My   New  Title ")

    events = _title_events(session)
    assert events == [{"title": "My New Title", "message_seqs": [], "source": "user"}]
    assert service.get(session) == "My New Title"


async def test_rename_rejects_empty_and_control_only_title() -> None:
    store, service = _make_service()
    session = store.create("s-empty")

    with pytest.raises(ValueError, match="visible characters"):
        service.rename(session, "   ")
    with pytest.raises(ValueError, match="visible characters"):
        service.rename(session, "\x1b[31m")
    assert _title_events(session) == []


async def test_rename_rejects_title_over_max_title_bytes() -> None:
    store, service = _make_service()
    session = store.create("s-oversize")

    with pytest.raises(ValueError, match="max_title_bytes"):
        service.rename(session, "x" * 81)
    assert _title_events(session) == []


async def test_user_rename_pins_automatic_scheduling() -> None:
    store, service = _make_service()
    session = store.create("s-pin")
    service.rename(session, "Pinned")

    _append_user_message(session, "later prompt")
    await service.drain()

    events = _title_events(session)
    assert len(events) == 1
    assert events[0]["source"] == "user"
    assert events[0]["title"] == "Pinned"


async def test_rename_supersedes_inflight_provider_work() -> None:
    store, service = _make_service()
    session = store.create("s-supersede")
    gate = asyncio.Event()
    provider = FakeProvider(gate=gate)
    service.register_provider(provider)

    _append_user_message(session, "initial prompt")
    await _wait_for(lambda: provider.calls)  # provider task 已挂在 gate 上
    service.rename(session, "Renamed")
    gate.set()
    await service.drain()

    sources = [event["source"] for event in _title_events(session)]
    assert sources == ["fallback", "user"]
    assert provider.signals[0].is_set()


# ── refresh / 解 pin ──────────────────────────────────────────────────


async def test_refresh_unpins_user_title_with_fallback() -> None:
    store, service = _make_service()
    session = store.create("s-refresh")
    _append_user_message(session, "original first prompt")
    await service.drain()
    service.rename(session, "Pinned")

    service.refresh(session)

    events = _title_events(session)
    assert [event["source"] for event in events] == ["fallback", "user", "fallback"]
    assert service.get(session) == "original first prompt"


async def test_refresh_without_eligible_message_is_noop() -> None:
    store, service = _make_service()
    session = store.create("s-refresh-empty")
    service.rename(session, "Pinned")

    service.refresh(session)

    assert service.get(session) == "Pinned"


async def test_refresh_with_provider_reschedules_generation() -> None:
    store, service = _make_service()
    session = store.create("s-refresh-provider")
    provider = FakeProvider(title="Refreshed")
    service.register_provider(provider)
    _append_user_message(session, "prompt one")
    await service.drain()
    service.rename(session, "Pinned")
    _append_user_message(session, "prompt two")
    await service.drain()
    assert service.get(session) == "Pinned"

    service.refresh(session)
    await service.drain()

    assert service.get(session) == "Refreshed"
    assert len(provider.calls) == 2
    # 第二次调用以全部合格消息为输入
    assert [message.text for message in provider.calls[-1]] == ["prompt one", "prompt two"]


# ── provider 注册 ─────────────────────────────────────────────────────


async def test_provider_registration_is_unique() -> None:
    _, service = _make_service()
    cancel = service.register_provider(FakeProvider("first"))

    with pytest.raises(ValueError, match="already registered"):
        service.register_provider(FakeProvider("second"))

    cancel()
    service.register_provider(FakeProvider("after-cancel"))


async def test_provider_registration_cancel_is_idempotent() -> None:
    _, service = _make_service()
    cancel = service.register_provider(FakeProvider("first"))

    cancel()
    cancel()
    service.register_provider(FakeProvider("second"))
    cancel()  # 过期取消不得摘掉第二个 provider
    with pytest.raises(ValueError, match="already registered"):
        service.register_provider(FakeProvider("third"))


async def test_provider_shape_validation() -> None:
    _, service = _make_service()

    class NoId:
        id = ""
        automatic = "first-prompt"

        async def generate(self, session: Any, messages: Any, signal: Any) -> Any: ...

    class BadCadence(NoId):
        id = "x"
        automatic = "all-prompts"

    class NoGenerate:
        id = "y"
        automatic = "first-prompt"

    with pytest.raises(ValueError, match="non-empty string"):
        service.register_provider(NoId())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="automatic mode"):
        service.register_provider(BadCadence())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="generate"):
        service.register_provider(NoGenerate())  # type: ignore[arg-type]


# ── provider 成功 / 失败 ──────────────────────────────────────────────


async def test_provider_success_supersedes_fallback() -> None:
    store, service = _make_service()
    session = store.create("s-provider-ok")
    service.register_provider(FakeProvider(title="Generated Title"))

    _append_user_message(session, "please explain the title feature")
    await service.drain()

    events = _title_events(session)
    assert [event["source"] for event in events] == ["fallback", "provider"]
    assert service.get(session) == "Generated Title"
    assert events[-1]["message_seqs"] == [0]


async def test_provider_failure_keeps_fallback_contained() -> None:
    store, service = _make_service()
    session = store.create("s-provider-err")
    service.register_provider(FakeProvider(error=RuntimeError("boom")))

    _append_user_message(session, "prompt that survives provider failure")
    await service.drain()

    events = _title_events(session)
    assert [event["source"] for event in events] == ["fallback"]
    assert service.get(session) == "prompt that survives provider failure"


async def test_provider_invalid_result_is_rejected_and_contained() -> None:
    store, service = _make_service()
    session = store.create("s-provider-bad")

    class BadResultProvider(FakeProvider):
        async def generate(
            self, session: Any, messages: Sequence[Any], signal: asyncio.Event
        ) -> dict[str, Any]:
            del session, messages, signal
            return {"title": "ok", "message_seqs": [999]}

    service.register_provider(BadResultProvider())
    _append_user_message(session, "some prompt")
    await service.drain()

    assert [event["source"] for event in _title_events(session)] == ["fallback"]


async def test_provider_result_normalized_to_max_title_bytes() -> None:
    store, service = _make_service(max_title_bytes=10, fallback_max_bytes=10)
    session = store.create("s-provider-cap")
    service.register_provider(FakeProvider(title="y" * 50))

    _append_user_message(session, "prompt")
    await service.drain()

    assert service.get(session) == "y" * 10


async def test_second_user_message_does_not_reschedule_first_prompt_provider() -> None:
    store, service = _make_service()
    session = store.create("s-cadence")
    provider = FakeProvider(title="First")
    service.register_provider(provider)

    _append_user_message(session, "first prompt")
    await service.drain()
    _append_user_message(session, "second prompt")
    await service.drain()

    assert len(provider.calls) == 1
    assert service.get(session) == "First"


# ── revision 取代 ─────────────────────────────────────────────────────


async def test_stale_provider_completion_is_discarded() -> None:
    store, service = _make_service()
    session = store.create("s-stale")
    gate = asyncio.Event()
    provider = _CountingProvider(gate)
    service.register_provider(provider)

    _append_user_message(session, "prompt for stale generation")
    await _wait_for(lambda: provider.calls == 1)
    # refresh 产生新 revision:cancel 旧在途(其结果过期后必须丢弃),调度新修订
    service.refresh(session)
    await _wait_for(lambda: provider.calls == 2)
    gate.set()
    await service.drain()

    titles = [event["title"] for event in _title_events(session)]
    assert "Title 1" not in titles
    assert service.get(session) == "Title 2"


async def test_cancelled_provider_task_propagates_cancellation() -> None:
    store, service = _make_service()
    session = store.create("s-cancel")
    provider = FakeProvider(gate=asyncio.Event())  # 永不放行
    service.register_provider(provider)

    _append_user_message(session, "prompt")
    await _wait_for(lambda: provider.calls)
    service.close()
    await service.drain()

    assert provider.signals[0].is_set()
    assert [event["source"] for event in _title_events(session)] == ["fallback"]


async def test_expired_completion_is_discarded_even_if_cancel_is_swallowed() -> None:
    """防御层:provider 吞掉取消仍然返回时,过期结果被 revision 守卫丢弃。"""
    store, service = _make_service()
    session = store.create("s-expired")

    class CancelSwallowingProvider:
        id = "swallower"
        automatic = "first-prompt"

        def __init__(self) -> None:
            self.entered = asyncio.Event()
            self.completed = asyncio.Event()

        async def generate(
            self, session_: Any, messages: Sequence[Any], signal: asyncio.Event
        ) -> dict[str, Any]:
            del session_, signal
            self.entered.set()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(10)
            self.completed.set()
            return {"title": "Stale", "message_seqs": [messages[0].seq]}

    provider = CancelSwallowingProvider()
    cancel_provider = service.register_provider(provider)

    _append_user_message(session, "prompt with expired generation")
    await _wait_for(provider.entered.is_set)
    cancel_provider()  # 反注册 + 取代在途工作
    await _wait_for(provider.completed.is_set)
    await service.drain()

    assert "Stale" not in [event["title"] for event in _title_events(session)]
    assert service.get(session) == "prompt with expired generation"


# ── observer 失败 contained ──────────────────────────────────────────


async def test_observer_scheduling_failure_does_not_poison_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, service = _make_service()
    session = store.create("s-observer")

    def exploding_defer(coro: Any) -> None:
        coro.close()
        raise RuntimeError("scheduler exploded")

    monkeypatch.setattr(service, "_defer", exploding_defer)
    _append_user_message(session, "prompt with broken scheduler")

    # append 已提交,observer 异常被 contained,日志完整
    assert session.seq == 1
    assert session.event_at(0) is not None


async def test_service_close_stops_scheduling() -> None:
    store, service = _make_service()
    session = store.create("s-closed")
    service.close()

    _append_user_message(session, "after close")
    await service.drain()

    assert _title_events(session) == []


# ── 装配 ──────────────────────────────────────────────────────────────


async def test_attach_to_store_covers_existing_and_future_sessions() -> None:
    store = SessionStore()
    existing = store.create("s-existing")
    service = SessionTitleService()
    service.attach_to_store(store)
    future = store.create("s-future")

    _append_user_message(existing, "existing prompt")
    _append_user_message(future, "future prompt")
    await service.drain()

    assert service.get(existing) == "existing prompt"
    assert service.get(future) == "future prompt"


async def test_attach_to_store_requires_observer_hook() -> None:
    class BareStore:
        def list(self) -> tuple[Any, ...]:
            return ()

    with pytest.raises(TypeError, match="add_observer_hook"):
        SessionTitleService().attach_to_store(BareStore())


async def test_setup_provides_capability_and_attaches_store() -> None:
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})

    await setup.setup(ctx, Config())

    service = ctx.provided["session.title"]
    assert isinstance(service, SessionTitleService)
    session = store.create("s-setup")
    _append_user_message(session, "setup wired prompt")
    await service.drain()
    assert service.get(session) == "setup wired prompt"


async def test_setup_without_store_provides_capability_only() -> None:
    ctx = _fake_ctx({})

    await setup.setup(ctx, Config())

    assert isinstance(ctx.provided["session.title"], SessionTitleService)


async def test_setup_attaches_store_created_after_boot() -> None:
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await setup.setup(ctx, Config())

    session = store.create("s-late")
    _append_user_message(session, "late session prompt")
    await ctx.provided["session.title"].drain()

    assert ctx.provided["session.title"].get(session) == "late session prompt"
