"""ModelVisibleLLMAdapter —— LLM 边界真实捕获(ADR-0169 D7 + PR-12.5)。

职责
----
Adapter 装饰器叠在 :class:`TelemetryLLMAdapter` 外层(组合根)。
每次 ``complete`` / ``stream`` 调用,在调内层**之前**:
    1. 从 :mod:`lca.infrastructure.observability.loop_cursor.model_visible_binding`
       取当前 cursor + capture(任一缺席则「透明透传」分支:不写盘、不落 EP、业务继续)
    2. 构造 ``system`` / ``tools`` / ``messages`` / ``manifest``(降级版
       messages 由 prompt 字符串派生 — 见 :func:`_derive_capture_inputs`)
    3. 调 ``capture.capture(...)`` 写 4 件套到 ``model_visible/step_<NN>/``
    4. 拿回 :class:`ModelVisibleArtifact`,构造
       :class:`RequestHeader` 给 ``cursor.record_request_header(...)``:
       - 写 1 条 ``llm.request.header`` EP 到 spine(SSOT = spine)
       - 自增 cursor.step_index(派生 step_id = ``"step-{step_index:03d}"``)

不变量(ADR-0169 D5 / L10):
- Capture / record_request_header 失败**不**挡业务,只 log + 透传到内层
- stream 路径只走 1 次 capture(stream 起手),不按 token 切步
- 装饰器对内层结果(LLMResponse / AsyncIterator[LLMStreamEvent])完全透明

构造签名
--------
接受两个 ``Provider``(可调用),由组合根注入:

.. code-block:: python

    ModelVisibleLLMAdapter(
        inner=...,
        cursor_provider=get_current_cursor,        # () -> LoopCursor | None
        capture_provider=get_current_model_visible_capture,
        model="openai/gpt-4o",
    )

默认值与 ADR-0169 装配一致(走 ContextVar);测试可注入占位 Provider。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.observability.loop_cursor import LoopCursor
from lca.contracts.observability.loop_cursor_payloads import RequestHeader
from lca.contracts.observability.model_visible_capture import (
    ModelVisibleArtifact,
    ModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    get_current_cursor,
)
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    get_current_model_visible_capture,
)

_log = logging.getLogger(__name__)

# Provider 类型:返回对象或 None
CursorProvider = Callable[[], LoopCursor | None]
CaptureProvider = Callable[[], ModelVisibleCapture | None]


def _to_provider(
    *,
    value: Any,
    fallback: Callable[[], Any] | None,
    default: Callable[[], Any],
) -> Callable[[], Any]:
    """把 ``inner`` 接的对象或 callable 统一成 Provider(callable)。

    优先级:``value``(对象或 callable) > ``fallback`` > ``default``。
    """
    if value is None and fallback is not None:
        return fallback
    if value is None:
        return default
    if callable(value):
        return value
    # 对象:包装为常量 provider(不读 ContextVar)
    captured = value

    def _provider() -> Any:
        return captured

    return _provider


def _step_id_for(step_index: int) -> str:
    """``"step-{step_index:03d}"`` —— ModelVisibleCapture + cursor 内部约定一致。

    ADR-0168 §D7 + ADR-0169 D7 step_id 是「3 位零填充」形式;
    cursor.snapshot.step_id 也由此派生。
    """
    return f"step-{int(step_index):03d}"


def _derive_capture_inputs(
    *,
    prompt: str,
    kwargs: dict[str, Any],
) -> tuple[Any, list[Any], list[dict[str, Any]], dict[str, Any]]:
    """从 ``prompt`` + ``kwargs`` 派生降级版 capture 输入。

    5 件套里 system / tools / messages / manifest 全都能拿到最低限度;
    ``system`` 不可派生(不知道 brain prompt),留空字符串 + manifest 标注。
    ``tools`` 从 kwargs.tools 派生(若调用方注入);否则空列表。
    ``messages`` 由 prompt 派生单条 user message(degraded — 真实 messages
    在 provider 内部组装;这条降级足够 I-MV1 model_visible 5 件套真实落盘)。
    ``manifest`` 派生最小上下文记录:{source, prompt_chars, has_tools, ...}。
    """
    system = {"objective": "(see provider prompt catalog)", "derived": True}
    tools_raw = kwargs.get("tools")
    tools: list[Any] = list(tools_raw) if isinstance(tools_raw, (list, tuple)) else []
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt or ""}]
    manifest: dict[str, Any] = {
        "source": "model_visible_llm_adapter",
        "prompt_chars": len(prompt or ""),
        "has_tools": bool(tools),
        "has_temperature": "temperature" in kwargs,
        "kwargs_keys": sorted(kwargs.keys()),
    }
    return system, tools, messages, manifest


def _safe_record_header(
    *,
    cursor: LoopCursor | None,
    artifact: ModelVisibleArtifact | None,
    model: str,
) -> None:
    """构造 ``RequestHeader`` 并喂给 ``cursor.record_request_header(...)``。

    ``artifact is None`` ⇒ cursor 没有 capture(走透明分支);cursor is None
    ⇒ 走「无 cursor」透明分支;两者都失败时均不抛,只 log。
    """
    if cursor is None or artifact is None:
        return
    try:
        snap = cursor.snapshot
        step_id = artifact.step_id if artifact.step_id else _step_id_for(snap.step_index + 1)
        header = RequestHeader(
            step_id=step_id,
            incarnation=snap.incarnation,
            reason="initial",
            model=model,
            system_digest=artifact.system_digest,
            system_path=artifact.system_path,
            tools_digest=artifact.tools_digest,
            tools_path=artifact.tools_path,
            messages_digest=artifact.messages_digest,
            messages_path=artifact.messages_path,
            manifest_digest=artifact.manifest_digest,
            manifest_path=artifact.manifest_path,
            inherited_from_step=None,
        )
        cursor.record_request_header(header)
    except Exception as exc:
        # 其它非预期失败:L10 + D5 不挡业务
        _log.warning("model_visible_record_header_failed: %s", exc)


class ModelVisibleLLMAdapter:
    """LLM 边界真实捕获装饰器(ADR-0169 PR-12.5)。

    与 :class:`TelemetryLLMAdapter` 同级(组合根叠层);本装饰器只做捕获,
    不做 LlmCallCompleted / Otel span / token usage 记 — 由 TelemetryLLMAdapter
    与 ADR-0172 OTel Projection 共同负责(控制 / 观察分离)。
    """

    name = "model-visible-llm"

    def __init__(
        self,
        inner: Any,
        *,
        cursor: LoopCursor | CursorProvider | None = None,
        capture: ModelVisibleCapture | CaptureProvider | None = None,
        cursor_provider: CursorProvider | None = None,
        capture_provider: CaptureProvider | None = None,
        model: str = "unknown",
    ) -> None:
        self._inner = inner
        # cursor / capture 既可接对象也可接 callable,缺省回退到 ContextVar 隐式取
        self._cursor_provider: CursorProvider = _to_provider(
            value=cursor,
            fallback=cursor_provider,
            default=get_current_cursor,
        )
        self._capture_provider: CaptureProvider = _to_provider(
            value=capture,
            fallback=capture_provider,
            default=get_current_model_visible_capture,
        )
        self._model = model

    @property
    def inner(self) -> Any:
        """被装饰的 LLM adapter(组合无损性内省)。"""
        return self._inner

    @property
    def model(self) -> str:
        return self._model

    def _run_capture(self, *, prompt: str, kwargs: dict[str, Any]) -> None:
        """调 capture + record_request_header;失败被吞(L10 + D5)。

        缺一不可:cursor 与 capture **都**必须存在才走完整 capture +
        record_request_header 链。任一缺失走透明分支(不写盘、不落 EP)。
        这是 ADR-0169 D5「profile 可关闭 model_visible capture」语义。
        """
        cursor = self._cursor_provider()
        capture = self._capture_provider()
        if cursor is None or capture is None:
            return
        try:
            snap = cursor.snapshot
            step_id = _step_id_for(snap.step_index + 1)
            system, tools, messages, manifest = _derive_capture_inputs(prompt=prompt, kwargs=kwargs)
            artifact: ModelVisibleArtifact = capture.capture(
                step_id=step_id,
                incarnation=snap.incarnation,
                system=system,
                tools=tools,
                messages=messages,
                manifest=manifest,
            )
        except Exception as exc:
            # capture 写盘失败:不挡业务(底 5 件套可能已部分写,artifact 也可能
            # 拿到部分 digest;但 record_request_header 必须 4 digest 全有,
            # 缺则跳过 EP;只警告一次)
            _log.warning("model_visible_capture_failed: %s", exc)
            return
        _safe_record_header(cursor=cursor, artifact=artifact, model=self._model)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self._run_capture(prompt=prompt, kwargs=kwargs)
        return await self._inner.complete(prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        self._run_capture(prompt=prompt, kwargs=kwargs)
        async for event in self._inner.stream(prompt, **kwargs):
            yield event


__all__ = ["ModelVisibleLLMAdapter"]
