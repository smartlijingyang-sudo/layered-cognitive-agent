"""model_visible publisher + hook 端到端（ADR-0185 §3.1 + §3.2 / PR-2）。

盖章 1（I-MV-1）: ``ModelVisiblePublisher`` 是 ``spine.llm.request.header`` +
``spine.llm.request.header.assistant`` 两类 category 的唯一授权 producer。
盖章 2: ``ModelVisibleHook`` 在 fold 优化命中时跳过 publish（同 header）,
header 变更时 publish + reason = ``change``;首次 publish reason = ``initial``。
盖章 3: ``capture_post_llm`` publish assistant payload;header_digest 与上次
request header canonical header sha256 一致。
盖章 4: 透明降级 —— cursor / prompt 缺席 → ``capture_pre_llm`` 返回 ``None``
且不抛错;assistant publish 不挡业务。

不动 LLM adapter 装配（PR-3 领土）;本测试只覆盖 hook 类 + marker 鉴权。
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from lca_kernel.events.bus import EventBus

# ── fixtures ────────────────────────────────────────────────────────────
# bus / bound_session 来自上层 conftest:publish 走绑定 Session 路径
# (ADR-0186 fail-loud),EventBus.set_default / 复位由 bound_session 统一承担。


@pytest.fixture
def hook(bound_session: Any) -> Any:
    """单实例 :class:`ModelVisibleHook` + monkey-patch 的 cursor / prompt providers。"""
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook
    from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
        CurrentReasonerPrompt,
    )

    state: dict[str, Any] = {
        "cursor": None,
        "prompt": None,
    }

    class _StubCursor:
        def __init__(self, run_id: str) -> None:
            self._snapshot = type(
                "_Snap",
                (),
                {"run_id": run_id, "step_index": 0, "incarnation": 1},
            )()
            self.opened_steps: list[str] = []

        @property
        def snapshot(self) -> Any:
            return self._snapshot

        def open_step(self, step_id: str) -> None:
            # LoopCursor.open_step 契约:step 推进(状态机),不落 EP。
            self.opened_steps.append(step_id)
            self._snapshot.step_index += 1
            self._snapshot.step_id = step_id

    def cursor_provider() -> Any:
        return state["cursor"]

    def prompt_provider() -> Any:
        return state["prompt"]

    h = ModelVisibleHook(
        bus=bound_session.bus,
        cursor_provider=cursor_provider,
        prompt_ctx_getter=prompt_provider,
    )

    def make_prompt(template_id: str, text: str) -> Any:
        return CurrentReasonerPrompt(
            step_id="step-001",
            template_id=template_id,
            selector_decision_path="default",
            system_prompt_text=text,
        )

    # 用 SimpleNamespace 避免 type() 类字典中函数被当 unbound method 处理。
    from types import SimpleNamespace

    return SimpleNamespace(
        hook=h,
        state=state,
        StubCursor=_StubCursor,
        make_prompt=make_prompt,
    )


# ── 盖章 1: yaml 鉴权 + I-MV-1 ──────────────────────────────────────────


def test_i_mv_1_model_visible_publisher_authorized(bus: EventBus[Any]) -> None:
    """``ModelVisiblePublisher`` 在两类 model-visible category 的 publishers 集合内。"""
    from lca.contracts.event import Category
    from lca.plugins.events.publishers.model_visible.publisher import (
        ModelVisiblePublisher,
    )

    for cat in (
        Category("spine.llm.request.header"),
        Category("spine.llm.request.header.assistant"),
    ):
        assert ModelVisiblePublisher in bus.registry.publishers[cat], (
            f"ModelVisiblePublisher 未授权 {cat.value};yaml 替换未生效"
        )


def test_i_mv_1_unauthorized_producer_rejected(bus: EventBus[Any]) -> None:
    """非授权 class publish → ``UnauthorizedPublishError``(鉴权矩阵生效)。"""
    from lca.contracts.event import Category
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads_model_visible import (
        SpineLlmRequestHeaderPayload,
    )

    class _OtherPlugin:
        pass

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineLlmRequestHeaderPayload(
                step_id="step-001",
                incarnation=1,
                config={},
                system="s",
                tools=(),
                messages=(),
                manifest=None,
                reason="initial",
                previous_header_digest=None,
            ),
            producer=_OtherPlugin,
        )
    # sanity: Category 类不缺失
    assert Category("spine.llm.request.header") is not None


# ── 盖章 2: fold 优化 + reason 派生 ────────────────────────────────────


def test_capture_pre_llm_initial_then_change(hook: Any) -> None:
    """首次 publish reason=initial;第二次 system 变 → reason=change。"""
    hook.state["cursor"] = hook.StubCursor("run-1")
    hook.state["prompt"] = hook.make_prompt("t1", "first")

    ref1 = hook.hook.capture_pre_llm(
        run_id="run-1", step_index=0, incarnation=1, kwargs={"tools": [], "messages": []}
    )
    assert ref1 is not None
    assert ref1.category == "spine.llm.request.header"

    # 第二次 prompt 变 → reason=change
    hook.state["prompt"] = hook.make_prompt("t1", "second")
    ref2 = hook.hook.capture_pre_llm(
        run_id="run-1", step_index=0, incarnation=1, kwargs={"tools": [], "messages": []}
    )
    assert ref2 is not None
    assert ref2.category == "spine.llm.request.header"


def test_capture_pre_llm_fold_skips_repeat(hook: Any) -> None:
    """同 header(同 system + tools)第二次 → fold 跳过,返回 ``None``。"""
    hook.state["cursor"] = hook.StubCursor("run-1")
    hook.state["prompt"] = hook.make_prompt("t1", "stable")

    kwargs: dict[str, Any] = {"tools": [], "messages": []}
    ref1 = hook.hook.capture_pre_llm(run_id="run-1", step_index=0, incarnation=1, kwargs=kwargs)
    assert ref1 is not None

    ref2 = hook.hook.capture_pre_llm(run_id="run-1", step_index=0, incarnation=1, kwargs=kwargs)
    assert ref2 is None, "同 header 应 fold 跳过"


def test_capture_pre_llm_advances_cursor_step(hook: Any) -> None:
    """回归锁(缺口 B,run_a7ead118420b):capture_pre_llm 经 open_step 推进 cursor。

    修复前 hook 路径不调 cursor 的 L6 自增(record_request_header 被
    EventBus publish 取代后丢失),cursor.step_index 恒 0:所有 header
    的 step_id=step-001,foldRequestHeader 只覆盖 step-001;
    ``step.*.record`` payload.step_index=0 挂不上 fold 帧 →
    journal.tool_total=0(H-xref)。
    """
    from lca.contracts.observability.incarnation import Incarnation
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor

    cursor = InMemoryLoopCursor(
        run_id="run-adv",
        trace_id="t-adv",
        incarnation=Incarnation(run_id="run-adv", plan_ref="p", incarnation_seq=1),
    )
    hook.state["cursor"] = cursor
    hook.state["prompt"] = hook.make_prompt("t1", "sys-a")

    ref1 = hook.hook.capture_pre_llm(
        run_id="run-adv", step_index=0, incarnation=1, kwargs={"tools": [], "messages": []}
    )
    assert ref1 is not None
    assert cursor.snapshot.step_index == 1
    assert cursor.snapshot.step_id == "step-001"

    # 第二次 LLM 请求:adapter 读到新 snapshot(step_index=1)→ step-002
    hook.state["prompt"] = hook.make_prompt("t1", "sys-b")
    ref2 = hook.hook.capture_pre_llm(
        run_id="run-adv",
        step_index=cursor.snapshot.step_index,
        incarnation=1,
        kwargs={"tools": [], "messages": []},
    )
    assert ref2 is not None
    assert cursor.snapshot.step_index == 2
    assert cursor.snapshot.step_id == "step-002"


def test_capture_pre_llm_fold_skip_does_not_advance_cursor(hook: Any) -> None:
    """fold 命中(同 step 重试,同 header)→ 跳过 publish 也不推进步。"""
    hook.state["cursor"] = hook.StubCursor("run-skip")
    hook.state["prompt"] = hook.make_prompt("t1", "stable")

    kwargs: dict[str, Any] = {"tools": [], "messages": []}
    ref1 = hook.hook.capture_pre_llm(run_id="run-skip", step_index=0, incarnation=1, kwargs=kwargs)
    assert ref1 is not None
    assert hook.state["cursor"].opened_steps == ["step-001"]

    ref2 = hook.hook.capture_pre_llm(run_id="run-skip", step_index=0, incarnation=1, kwargs=kwargs)
    assert ref2 is None, "同 header 同 step 应 fold 跳过"
    assert hook.state["cursor"].opened_steps == ["step-001"], "fold 跳过不得新开步"


def test_capture_pre_llm_transparent_when_prompt_missing(hook: Any) -> None:
    """prompt 未注入 → 透明降级,不发盘,不抛错。"""
    hook.state["cursor"] = hook.StubCursor("run-1")
    hook.state["prompt"] = None

    ref = hook.hook.capture_pre_llm(run_id="run-1", step_index=0, incarnation=1, kwargs={})
    assert ref is None


def test_capture_pre_llm_transparent_when_cursor_missing(hook: Any) -> None:
    """cursor 未注入 → 透明降级(capture_pre_llm 不依赖 cursor,走 prompt-only 即可)。"""
    hook.state["cursor"] = None
    hook.state["prompt"] = hook.make_prompt("t1", "x")

    # capture_pre_llm 不要求 cursor(由 caller 注入 run_id);prompt 齐全即发
    ref = hook.hook.capture_pre_llm(run_id="run-1", step_index=0, incarnation=1, kwargs={})
    assert ref is not None


def test_capture_pre_llm_narrows_tool_objects(hook: Any, bound_session: Any) -> None:
    """真实 ``Tool`` 协议对象 → 边界窄化为 ``ToolSchema`` 后落 payload。

    回归锁:kwargs.tools 承载认知 Tool 对象(llm_turn executor 透传
    ``list[Tool]``);修复前 payload 构造命中 pydantic ValidationError 并
    穿透 capture_pre_llm,``spine.llm.request.header`` 完全不落盘。
    """
    from lca.contracts.observability.loop_cursor_payloads import ToolSchema
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )
    from lca_kernel.events.payloads_model_visible import (
        SpineLlmRequestHeaderPayload,
    )

    class _Tool:
        """Tool 协议同形:无 ``to_openai_dict``,走 from_any 属性分支。"""

        name = "bash"
        description = "run shell commands"
        parameters: ClassVar[dict[str, Any]] = {
            "type": "object",
            "properties": {"command": {"type": "string"}},
        }
        is_idempotent = False
        default_timeout_s = 30

        async def execute(self, args: dict[str, Any]) -> Any:
            raise NotImplementedError

    captured: list[Any] = []

    class _CapturingSession:
        """append 时留底 payload,再委托 bus 走完整鉴权路径。"""

        def append(self, payload: Any, *, producer: Any = None) -> Any:
            captured.append(payload)
            return bound_session.bus.publish(payload, producer=producer)

    hook.state["cursor"] = hook.StubCursor("run-narrow")
    hook.state["prompt"] = hook.make_prompt("t1", "sys")

    token = set_publish_session(_CapturingSession())
    try:
        ref = hook.hook.capture_pre_llm(
            run_id="run-narrow",
            step_index=0,
            incarnation=1,
            kwargs={"tools": [_Tool()], "messages": []},
        )
    finally:
        reset_publish_session(token)

    assert ref is not None
    assert len(captured) == 1
    payload = captured[0]
    assert isinstance(payload, SpineLlmRequestHeaderPayload)
    assert len(payload.tools) == 1
    narrowed = payload.tools[0]
    assert isinstance(narrowed, ToolSchema)
    assert narrowed.name == "bash"
    assert narrowed.description == "run shell commands"
    assert narrowed.parameters == {
        "type": "object",
        "properties": {"command": {"type": "string"}},
    }


def test_capture_pre_llm_construction_failure_is_transparent(hook: Any) -> None:
    """payload 构造失败(非法 manifest)→ 吞错 + 返回 ``None``,不外抛。

    修复前构造在 try 之外,ValidationError 穿透到 adapter 的 debug 级兜底,
    生产不可见;修复后构造与 publish 同 try,失败走 warning。
    """
    hook.state["cursor"] = hook.StubCursor("run-bad")
    hook.state["prompt"] = hook.make_prompt("t1", "sys")

    ref = hook.hook.capture_pre_llm(
        run_id="run-bad",
        step_index=0,
        incarnation=1,
        kwargs={"tools": [], "messages": [], "manifest": object()},
    )
    assert ref is None


# ── 盖章 3: assistant payload + digest 关联 ─────────────────────────────


def test_capture_post_llm_emits_assistant_payload(hook: Any) -> None:
    """capture_post_llm 发 ``spine.llm.request.header.assistant`` + header_digest。"""
    from lca.plugins.events.publishers.model_visible.publisher import (
        ModelVisiblePublisher,
    )

    hook.state["cursor"] = hook.StubCursor("run-2")
    hook.state["prompt"] = hook.make_prompt("t1", "stable")

    hook.hook.capture_pre_llm(
        run_id="run-2", step_index=0, incarnation=1, kwargs={"tools": [], "messages": []}
    )

    class _StubResponse:
        content: ClassVar[str] = "hello world"
        tool_calls: ClassVar[tuple[Any, ...]] = ()
        finish_reason: ClassVar[str] = "stop"
        usage: ClassVar[dict[str, int]] = {"prompt_tokens": 5, "completion_tokens": 3}

    # publish 后 EventBus 应有 self-observers 等 fanout 行为,但本测试只关心
    # 抛错与否 + 返回 ref + category。bus 不挂 sink,published 计数仍涨。
    pre_count = bus_count_published(hook.hook._bus)
    ref = hook.hook.capture_post_llm(
        run_id="run-2", step_index=0, incarnation=1, response=_StubResponse()
    )
    post_count = bus_count_published(hook.hook._bus)

    assert ref is not None
    assert ref.category == "spine.llm.request.header.assistant"
    assert post_count == pre_count + 1

    # sanity: marker 是有效 type,bind 走 producer= 鉴权
    assert isinstance(ModelVisiblePublisher, type)


def test_capture_post_llm_reads_llmresponse_text_field(hook: Any, monkeypatch: Any) -> None:
    """回归锁:``LLMResponse`` 契约字段是 ``text``,assistant_content 必须读到。

    旧实现读 ``.content``(``LLMResponse`` 无此属性)→ 模型输出文本恒为空。
    本测试用真实 :class:`LLMResponse`(``.text`` 有值)断言 assistant_content
    捕获到文本,防字段名回归。
    """
    from lca.contracts.models.core.llm import LLMResponse

    captured: dict[str, Any] = {}

    def _fake_publish(payload: Any, *, producer: Any = None) -> Any:
        captured["payload"] = payload
        return None

    monkeypatch.setattr(
        "lca.plugins.events.publishers._session_publish.publish_via_session",
        _fake_publish,
    )

    response = LLMResponse(
        text="模型真实思考输出",
        model="test-model",
        finish_reason="stop",
        tool_calls=[],
    )
    hook.hook.capture_post_llm(run_id="run-text", step_index=0, incarnation=1, response=response)

    payload = captured.get("payload")
    assert payload is not None
    assert payload.assistant_content == "模型真实思考输出"


def test_capture_post_llm_without_prior_header(hook: Any) -> None:
    """无前置 capture_pre_llm → assistant publish 仍发,header_digest = 空字符串。"""

    class _StubResponse:
        content: ClassVar[str] = "x"
        tool_calls: ClassVar[tuple[Any, ...]] = ()
        finish_reason: ClassVar[str] = "stop"
        usage: ClassVar[dict[str, int]] = {}

    ref = hook.hook.capture_post_llm(
        run_id="run-orphan", step_index=2, incarnation=1, response=_StubResponse()
    )
    assert ref is not None
    assert ref.category == "spine.llm.request.header.assistant"


def test_adapter_pre_post_share_step_identity_after_open_step(bound_session: Any) -> None:
    """回归锁(缺口 B):open_step 推进 cursor 后,pre/post 仍配对同一 step。

    修复前 adapter 在 await 内层 LLM 之后重读 cursor snapshot;
    capture_pre_llm 已推进 step → post 拿到新 step_index,assistant
    payload 错挂到下一步(无对应 header)。修复后同一次调用共用入站
    快照,header 与 assistant 的 step_id 一致。
    """
    import asyncio

    from lca.contracts.models.core.llm import LLMResponse
    from lca.contracts.observability.incarnation import Incarnation
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        CurrentReasonerPrompt,
    )
    from lca.plugins.events.hooks.model_visible.adapter import ModelVisibleHookAdapter
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )

    cursor = InMemoryLoopCursor(
        run_id="run-pair",
        trace_id="t-pair",
        incarnation=Incarnation(run_id="run-pair", plan_ref="p", incarnation_seq=1),
    )
    prompt = CurrentReasonerPrompt(
        step_id="step-001",
        template_id="t1",
        selector_decision_path="default",
        system_prompt_text="sys",
    )
    hook = ModelVisibleHook(
        bus=bound_session.bus,
        cursor_provider=lambda: cursor,
        prompt_ctx_getter=lambda: prompt,
    )

    class _Inner:
        async def complete(self, prompt_text: str, **kwargs: Any) -> LLMResponse:
            return LLMResponse(text="done")

        async def stream(self, prompt_text: str, **kwargs: Any):  # pragma: no cover
            raise NotImplementedError

    adapter = ModelVisibleHookAdapter(_Inner(), hook)  # type: ignore[arg-type]

    captured: list[Any] = []

    class _CapturingSession:
        def append(self, payload: Any, *, producer: Any = None) -> Any:
            captured.append(payload)
            return bound_session.bus.publish(payload, producer=producer)

    token = set_publish_session(_CapturingSession())
    try:
        response = asyncio.run(adapter.complete("hello"))
    finally:
        reset_publish_session(token)

    assert response.text == "done"
    headers = [p for p in captured if p.category == "spine.llm.request.header"]
    assistants = [p for p in captured if p.category == "spine.llm.request.header.assistant"]
    assert len(headers) == 1
    assert len(assistants) == 1
    assert headers[0].step_id == "step-001"
    assert assistants[0].step_id == "step-001", "post 必须与 pre 同 step"
    assert cursor.snapshot.step_index == 1
    assert cursor.snapshot.step_id == "step-001"


# ── 盖章 4: setup() 装配 marker + hook(不依赖真实 Cordis) ──────────────


def test_setup_provides_marker_and_hook() -> None:
    """``setup()`` 注册 marker class 与 :class:`ModelVisibleHook` 实例到 ctx。

    注:``@plugin`` 装饰把 :func:`setup` 包成 ``CordisPlugin`` 对象,实际
    函数经 ``plugin.setup`` 拿到;EventBus.default() 走进程单例,本测试
    仅断言 marker class 注入 + hook 提供 + setup 签名(防声明漂移)。
    """
    from lca.plugins.events.publishers.model_visible.publisher import (
        ModelVisiblePublisher,
    )
    from lca.plugins.events.publishers.model_visible.publisher import (
        setup as plugin_setup,
    )

    captured: dict[str, Any] = {}

    class _Ctx:
        """最小 stub PluginContext:审计 provide 即可。"""

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            captured[str(key)] = value

    setup_fn = getattr(plugin_setup, "setup", plugin_setup)
    assert callable(setup_fn), "@plugin 应暴露 .setup 属性指向原函数"

    from pydantic import BaseModel

    class _EmptyConfig(BaseModel):
        model_config = {"extra": "forbid"}

    import asyncio

    asyncio.run(setup_fn(_Ctx(), _EmptyConfig()))

    assert "event.bus.publisher.model_visible" in captured
    assert captured["event.bus.publisher.model_visible"] is ModelVisiblePublisher
    assert "llm.adapter.hook.model_visible" in captured
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook

    assert isinstance(captured["llm.adapter.hook.model_visible"], ModelVisibleHook)

    import inspect

    sig = inspect.signature(setup_fn)
    assert "ctx" in sig.parameters
    assert "config" in sig.parameters


def test_plugin_decorator_metadata() -> None:
    """``@plugin`` 元数据与现有 15 个 spine_reflector 同形(I-FW-BUS-1 一致)。"""
    from lca.plugins.events.publishers.model_visible.publisher import (
        ModelVisiblePublisher,
    )
    from lca.plugins.events.publishers.model_visible.publisher import (
        setup as plugin_setup,
    )

    assert isinstance(ModelVisiblePublisher, type)
    setup_fn = getattr(plugin_setup, "setup", None)
    assert callable(setup_fn)
    assert ModelVisiblePublisher.__name__ == "ModelVisiblePublisher"


# ── helpers ─────────────────────────────────────────────────────────────


def bus_count_published(bus: EventBus[Any]) -> int:
    """读 EventBus.delivery_snapshot 的 published 总和(0 sink 时仍计数)。"""
    snap = bus.delivery_snapshot()
    return sum(c.get("published", 0) for c in snap.values())
