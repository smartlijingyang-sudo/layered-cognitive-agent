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

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter

if TYPE_CHECKING:
    from lca.plugins.events.hooks.model_visible.hook import ModelVisibleHook

_log = logging.getLogger(__name__)


def _snapshot_attrs(cursor: Any) -> tuple[str, int] | None:
    """Read ``(run_id, incarnation)`` from cursor snapshot。

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
    incarnation = getattr(snap, "incarnation", None)
    if not isinstance(run_id, str) or not isinstance(incarnation, int):
        return None
    return run_id, incarnation


def _model_identity(kwargs: dict[str, Any]) -> tuple[str, str]:
    config = kwargs.get("config")
    if isinstance(config, dict):
        model = str(config.get("model") or config.get("model_id") or "unknown")
        provider = str(config.get("provider") or config.get("provider_id") or "unknown")
        return provider, model
    return "unknown", "unknown"


def _resolve_model_config(inner: LLMAdapter) -> dict[str, Any] | None:
    cur: Any = inner
    for _ in range(8):
        model = getattr(cur, "model", None) or getattr(cur, "model_name", None)
        provider = getattr(cur, "provider", None) or getattr(cur, "provider_id", None)
        if model:
            cfg: dict[str, Any] = {"model": str(model)}
            if provider:
                cfg["provider"] = str(provider)
            return cfg
        nxt = getattr(cur, "inner", None) or getattr(cur, "_inner", None)
        if nxt is None or nxt is cur:
            break
        cur = nxt
    return None


def _kwargs_for_hook(
    kwargs: dict[str, Any],
    *,
    inner: LLMAdapter,
    prompt: str = "",
    system: str | None = None,
) -> dict[str, Any]:
    out = dict(kwargs)
    history = out.get("history")
    if isinstance(history, (list, tuple)) and history:
        wire_prompt = (prompt or str(out.get("prompt") or "")).strip()
        if wire_prompt:
            from lca.infrastructure.llm_adapter.openai_compat.history import (
                openai_messages_with_history,
            )

            out["messages"] = tuple(
                openai_messages_with_history(system, wire_prompt, list(history))
            )
        elif "messages" not in out:
            out["messages"] = tuple(history)
    elif "messages" not in out and "history" in out:
        out["messages"] = out["history"]
    cfg = _resolve_model_config(inner)
    if cfg is not None:
        existing = out.get("config")
        if isinstance(existing, dict):
            out["config"] = {**cfg, **existing}
        else:
            out["config"] = cfg
    return out


def _tool_calls_payload(response: LLMResponse) -> list[dict[str, Any]] | None:
    if not response.tool_calls:
        return None
    out: list[dict[str, Any]] = []
    for call in response.tool_calls:
        out.append(
            {
                "id": getattr(call, "call_id", ""),
                "name": getattr(call, "tool_name", ""),
                "arguments": getattr(call, "arguments", {}),
            }
        )
    return out


def _emit_lifecycle_pre(hook: Any, kwargs: dict[str, Any]) -> None:
    from lca.infrastructure.session.emit.lifecycle_emit import request_model

    step = hook._step_counter
    provider, model = _model_identity(kwargs)
    request_model(turn=1, step=step, provider=provider, model=model)


def _emit_lifecycle_post(hook: Any, response: LLMResponse) -> None:
    from lca.infrastructure.session.bindings import (
        resolve_session_reader,
    )
    from lca.infrastructure.session.emit.lifecycle_emit import complete_model
    from lca.runtime.session.run_session_writer import RunSessionWriter

    step = hook._step_counter
    session = resolve_session_reader()
    if session is None:
        return
    tool_calls = _tool_calls_payload(response)
    text = response.text or ""
    usage = response.usage if isinstance(response.usage, dict) else None
    complete_model(
        turn=1,
        step=step,
        usage=usage,
        content=text,
        tool_calls=tool_calls,
    )
    RunSessionWriter(session=session).append_assistant_message(
        turn=1,
        step=step,
        role="assistant",
        content=text or None,
        tool_calls=tool_calls,
        usage=None,
    )


def _emit_lifecycle_fail(hook: Any, error: str) -> None:
    from lca.infrastructure.session.emit.lifecycle_emit import fail_model

    step = hook._step_counter
    fail_model(turn=1, step=step, error=error)


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
        # spec section H ContextVar deletion: cursor + reasoner_prompt no
        # longer come from a ``_cursor_provider`` callable on the hook.
        # They are explicit kwargs on the LLM call (``cursor`` + ``reasoner_prompt``),
        # extracted here before forwarding to ``self._inner.complete``.

    @property
    def inner(self) -> LLMAdapter:
        return self._inner

    @property
    def hook(self) -> ModelVisibleHook:
        return self._hook

    @staticmethod
    def _split_model_visible_kwargs(kwargs: dict[str, Any]) -> tuple[Any, Any]:
        """Pop ``cursor`` + ``reasoner_prompt`` from kwargs for the hook.

        spec section H: caller (reasoner / llm.invoke node) passes the
        bound ``LoopCursor`` and the current ``CurrentReasonerPrompt`` via
        kwargs to ``llm.complete(prompt, *, cursor=..., reasoner_prompt=...)``.
        The adapter pops them before forwarding the rest to the inner LLM
        (inner LLMs must not see ``cursor`` / ``reasoner_prompt``).
        """
        cursor = kwargs.pop("cursor", None)
        reasoner_prompt = kwargs.pop("reasoner_prompt", None)
        return cursor, reasoner_prompt

    @staticmethod
    def _system_text_from_prompt(reasoner_prompt: Any) -> str | None:
        """Extract ``system_prompt_text`` from a ``CurrentReasonerPrompt``-shaped obj."""
        if reasoner_prompt is None:
            return None
        text = getattr(reasoner_prompt, "system_prompt_text", None)
        return text if isinstance(text, str) else None

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        # 同一次调用共用入站快照:step 身份在 hook 内部唯一派生 + 锁定。
        cursor, reasoner_prompt = self._split_model_visible_kwargs(kwargs)
        attrs = _snapshot_attrs(cursor)
        system_text = self._system_text_from_prompt(reasoner_prompt)
        if attrs is not None:
            run_id, incarnation = attrs
            try:
                _emit_lifecycle_pre(self._hook, kwargs)
                self._hook.capture_pre_llm(
                    run_id=run_id,
                    incarnation=incarnation,
                    kwargs=_kwargs_for_hook(
                        kwargs,
                        inner=self._inner,
                        prompt=prompt,
                        system=system_text,
                    ),
                    system_prompt_text=system_text,
                )
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_pre_hook_failed: %s", exc)
        try:
            response = await self._inner.complete(prompt, **kwargs)
        except Exception as exc:
            if attrs is not None:
                pass
                try:
                    _emit_lifecycle_fail(self._hook, str(exc))
                except Exception as fail_exc:  # INTENTIONAL: L10 + D5 不挡业务
                    _log.debug("model_visible_fail_model_failed: %s", fail_exc)
            raise
        if attrs is not None:
            run_id, incarnation = attrs
            try:
                self._hook.capture_post_llm(
                    run_id=run_id,
                    incarnation=incarnation,
                    response=response,
                )
                _emit_lifecycle_post(self._hook, response)
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_post_hook_failed: %s", exc)
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        # 与 complete() 同语义:pre/post 共用入站快照。
        cursor, reasoner_prompt = self._split_model_visible_kwargs(kwargs)
        attrs = _snapshot_attrs(cursor)
        system_text = self._system_text_from_prompt(reasoner_prompt)
        if attrs is not None:
            run_id, incarnation = attrs
            try:
                _emit_lifecycle_pre(self._hook, kwargs)
                self._hook.capture_pre_llm(
                    run_id=run_id,
                    incarnation=incarnation,
                    kwargs=_kwargs_for_hook(
                        kwargs,
                        inner=self._inner,
                        prompt=prompt,
                        system=system_text,
                    ),
                    system_prompt_text=system_text,
                )
            except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                _log.debug("model_visible_pre_hook_failed: %s", exc)
        post_emitted = False
        try:
            async for event in self._inner.stream(prompt, **kwargs):
                # COMPLETED 事件携带与 complete() 等价的最终响应;只在此记 1 次
                # assistant payload,不按 delta 记。
                if (
                    not post_emitted
                    and event.type == LLMStreamEventType.COMPLETED
                    and event.response is not None
                ):
                    if attrs is not None:
                        run_id, incarnation = attrs
                        try:
                            self._hook.capture_post_llm(
                                run_id=run_id,
                                incarnation=incarnation,
                                response=event.response,
                            )
                            _emit_lifecycle_post(self._hook, event.response)
                        except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
                            _log.debug("model_visible_post_hook_failed: %s", exc)
                    post_emitted = True
                yield event
        except Exception as exc:
            if attrs is not None:
                try:
                    _emit_lifecycle_fail(self._hook, str(exc))
                except Exception as fail_exc:  # INTENTIONAL: L10 + D5 不挡业务
                    _log.debug("model_visible_fail_model_failed: %s", fail_exc)
            raise


__all__ = ["ModelVisibleHookAdapter"]
