"""LLM adapter decorator invoking :class:`ModelVisibleHook` at the boundary.

ADR-0185 §3.2 / PR-3 wiring seam(PR-4 收口后为唯一 model-visible 边界装饰器):
composer 装配 ``instrument_llm(llm, *, ctx=...)`` 从
``ctx.soft_get("llm.adapter.hook.model_visible")`` 拿到 hook 实例后,用本
装饰器包 LLM 边界。装饰器内部:

1. ``complete(prompt, **kwargs)`` 与 ``stream(prompt, **kwargs)`` 入站前调
   :meth:`ModelVisibleHook.capture_pre_llm`(LLM 边界 snapshot + kwargs);
2. ``complete`` 返回 / ``stream`` COMPLETED 事件后调
   :meth:`ModelVisibleHook.capture_post_llm`(assistant 响应)。

失败语义(L10 + D5):hook 抛错 / publish 失败 ⇒ 吞错,不挡业务。
装饰器自身只是「调用 hook」,不持有真值、不写盘;所有事实走 hook 内部 fold
+ EventBus.publish,落 :class:`SpineLlmRequestHeaderPayload` /
:class:`SpineLlmRequestHeaderAssistantPayload` 至 ``<run_id>.spine.jsonl``。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter

if TYPE_CHECKING:
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook

_log = logging.getLogger(__name__)


def _snapshot_attrs(cursor: Any) -> tuple[str, int, int] | None:
    """Read ``(run_id, step_index, incarnation)`` from cursor snapshot。

    cursor 缺席 / 已 dispose / 无 ``snapshot`` 属性 → 返回 ``None``;调用方按
    「透明降级」处理(hook 内部亦走同语义)。
    """
    if cursor is None:
        return None
    try:
        snap = cursor.snapshot
    except Exception:
        return None
    run_id = getattr(snap, "run_id", None)
    step_index = getattr(snap, "step_index", None)
    incarnation = getattr(snap, "incarnation", None)
    if (
        not isinstance(run_id, str)
        or not isinstance(step_index, int)
        or not isinstance(incarnation, int)
    ):
        return None
    return run_id, step_index, incarnation


class ModelVisibleHookAdapter(LLMAdapter):
    """LLM adapter decorator wiring :class:`ModelVisibleHook` to the boundary.

    组合根 ``instrument_llm`` 装配时位于 :class:`TelemetryLLMAdapter` 外侧。
    装饰顺序(外 → 内):

        ModelVisibleHookAdapter → TelemetryLLMAdapter → inner

    这样 telemetry 在内层仍先收 LlmCallCompleted / Otel 投影 + token usage,
    model-visible 在最外层拦 pre/post;任一捕获失败不挡业务。
    """

    name = "model-visible-hook"

    def __init__(self, inner: LLMAdapter, hook: ModelVisibleHook) -> None:
        self._inner = inner
        self._hook = hook
        # hook 自带 cursor_provider(setup 时注入 get_current_cursor);此处复用,
        # 不再独立存 provider,避免 cursor ContextVar 解析路径分叉。
        self._cursor_provider = hook._cursor_provider  # type: ignore[attr-defined]

    @property
    def inner(self) -> LLMAdapter:
        return self._inner

    @property
    def hook(self) -> ModelVisibleHook:
        return self._hook

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        attrs = _snapshot_attrs(self._cursor_provider())
        if attrs is not None:
            run_id, step_index, incarnation = attrs
            try:
                self._hook.capture_pre_llm(
                    run_id=run_id,
                    step_index=step_index,
                    incarnation=incarnation,
                    kwargs=kwargs,
                )
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_pre_hook_failed: %s", exc)
        response = await self._inner.complete(prompt, **kwargs)
        attrs_post = _snapshot_attrs(self._cursor_provider())
        if attrs_post is not None:
            run_id, step_index, incarnation = attrs_post
            try:
                self._hook.capture_post_llm(
                    run_id=run_id,
                    step_index=step_index,
                    incarnation=incarnation,
                    response=response,
                )
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_post_hook_failed: %s", exc)
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        attrs = _snapshot_attrs(self._cursor_provider())
        if attrs is not None:
            run_id, step_index, incarnation = attrs
            try:
                self._hook.capture_pre_llm(
                    run_id=run_id,
                    step_index=step_index,
                    incarnation=incarnation,
                    kwargs=kwargs,
                )
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_pre_hook_failed: %s", exc)
        post_emitted = False
        async for event in self._inner.stream(prompt, **kwargs):
            # COMPLETED 事件携带与 complete() 等价的最终响应;只在此记 1 次
            # assistant payload,不按 delta 记。
            if (
                not post_emitted
                and event.type == LLMStreamEventType.COMPLETED
                and event.response is not None
            ):
                attrs_post = _snapshot_attrs(self._cursor_provider())
                if attrs_post is not None:
                    run_id, step_index, incarnation = attrs_post
                    try:
                        self._hook.capture_post_llm(
                            run_id=run_id,
                            step_index=step_index,
                            incarnation=incarnation,
                            response=event.response,
                        )
                    except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                        _log.debug("model_visible_post_hook_failed: %s", exc)
                post_emitted = True
            yield event


__all__ = ["ModelVisibleHookAdapter"]
