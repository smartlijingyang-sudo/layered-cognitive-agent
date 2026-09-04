"""ModelVisibleLLMAdapter —— LLM 边界真实捕获(ADR-0169 D7 + PR-12.5)。

职责
----
Adapter 装饰器叠在 :class:`TelemetryLLMAdapter` 外层(组合根)。
每次 ``complete`` / ``stream`` 调用,在调内层**之前**:
    1. 从 :mod:`lca.infrastructure.observability.loop_cursor.model_visible_binding`
       取当前 cursor + capture(任一缺席则「透明透传」分支:不写盘、不落 EP、业务继续)
    2. 构造 ``system`` / ``tools`` / ``messages`` / ``manifest``(降级版
       messages 由 prompt 字符串派生 — 见 :func:`_derive_capture_inputs`;
       Reasoner 绑定了 :class:`CurrentReasonerPrompt` 时,manifest 从
       PromptTrace + ContextManifest 派生 skill / section 装配真值)
    3. 调 ``capture.capture(...)`` 写 4 件套(+ 可选 ``context-manifest.json``)
       到 ``model_visible/step_<NN>/``
    4. 拿回 :class:`ModelVisibleArtifact`,构造
       :class:`RequestHeader` 给 ``cursor.record_request_header(...)``:
       - 写 1 条 ``llm.request.header`` EP 到 spine(SSOT = spine)
       - 持久化 ``request-header.json`` 到 step 目录(replay cursor 对位 digest)
       - 自增 cursor.step_index(派生 step_id = ``"step-{step_index:03d}"``)
内层返回最终响应后(``complete()`` 返回值;``stream`` 的 COMPLETED 事件携带
的响应)记 1 次 thinking:``thinking.json`` 落 step 目录 +
``cursor.record_thinking(...)``(thinking_kind=final_response,EP =
step.thinking.record);每次调用只记 1 次,不按 token 切。

不变量(ADR-0169 D5 / L10):
- Capture / record_request_header / record_thinking 失败**不**挡业务,
  只 log + 透传到内层
- stream 路径只走 1 次 capture + 1 次 thinking(stream 起手 / COMPLETED),
  不按 token 切步
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

import json
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.observability.loop_cursor import LoopCursor
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
)
from lca.contracts.observability.model_visible_capture import (
    ModelVisibleArtifact,
    ModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    relative_posix as _relative_posix,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    sha256_digest as _sha256_digest,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    to_jsonable as _to_jsonable,
)
from lca.infrastructure.observability.loop_cursor._capture_io import (
    write_json as _write_json,
)
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    get_current_cursor,
)
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    get_current_model_visible_capture,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
    get_current_reasoner_prompt,
)

_log = logging.getLogger(__name__)

# Provider 类型:返回对象或 None
CursorProvider = Callable[[], LoopCursor | None]
CaptureProvider = Callable[[], ModelVisibleCapture | None]

# ContextManifest item payload 预览上限(字符);manifest 只落预览不落全文。
_PAYLOAD_PREVIEW_CHARS = 200
# record_thinking text_preview 上限(字符);EP payload 只携带前缀,
# 全文在 thinking.json sidecar。
_THINKING_PREVIEW_CHARS = 2000


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


def _ensure_think_phase(cursor: LoopCursor) -> None:
    """确保 cursor 进入 THINK 窗口;已 THINK / 已 stop / closed / halted 不动。

    副作用:cursor.advance('think') 派生 1 条 ``phase.think.fold`` EP。
    已 THINK 时本函数 no-op。
    """
    try:
        snap = cursor.snapshot
    except Exception:
        # INTENTIONAL: cursor 未就绪或已 closed → 不阻止下游 record_request_header
        # 自身会再 catch 此场景(双保险);此处仅做"cursor 缺失就跳过 advance"。
        return
    if snap.phase == "think":
        return
    if snap.stop_signal is not None or snap.phase == "stop":
        return
    try:
        cursor.advance("think")  # type: ignore[arg-type]
    except Exception:
        # INTENTIONAL: advance 在 stop / closed / halted 时抛 CursorError;
        # 静默跳过,record_request_header 自身仍会再 catch(双保险)。
        return


def _step_id_for(step_index: int) -> str:
    """``"step-{step_index:03d}"`` —— ModelVisibleCapture + cursor 内部约定一致。

    ADR-0168 §D7 + ADR-0169 D7 step_id 是「3 位零填充」形式;
    cursor.snapshot.step_id 也由此派生。
    """
    return f"step-{int(step_index):03d}"


def _payload_preview(payload: Any) -> str:
    """ContextManifest item payload 的有界预览串(≤ _PAYLOAD_PREVIEW_CHARS)。

    str 直接截断;其它对象走 ``json.dumps(default=str)``;仍失败则 ``repr``。
    只用于 manifest 落盘预览 —— 全文真值在 ContextManifest 自身,不进本文件。
    """
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = repr(payload)
    return text[:_PAYLOAD_PREVIEW_CHARS]


def _derive_capture_inputs(
    *,
    prompt: str,
    kwargs: dict[str, Any],
) -> tuple[Any, list[Any], list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    """从 ``prompt`` + ``kwargs`` 派生 capture 输入(ADR-0175 D4 / ADR-0167 D3)。

    返回 ``(system, tools, messages, manifest, context_manifest)``:
    ``context_manifest`` 非 None 当且仅当 Reasoner 绑定了携带真值的
    :class:`CurrentReasonerPrompt`(此时与 ``manifest`` 同内容,原样落
    ``context-manifest.json``);降级路径返回 None,不写该文件。

    4 件套里 system / tools / messages / manifest 全都能拿到最低限度。
    ``system`` 优先读 ``get_current_reasoner_prompt()``(Reasoner 已 set,
    注入 ``system_prompt_text`` 真值);若未绑定,退回占位字符串
    ``{"objective":"(see provider prompt catalog)","derived":True}``。

    ``tools`` 从 kwargs.tools 派生(若调用方注入);否则空列表。
    ``messages`` 由 prompt 派生单条 user message(degraded — 真实 messages
    在 provider 内部组装;这条降级足够 I-MV1 model_visible 4 件套真实落盘)。

    ``manifest``:Reasoner 绑定了 :class:`CurrentReasonerPrompt` 且
    ``system_prompt_text`` 非空时,从绑定真值派生完整上下文清单
    (template / selector path / skill ids / section trace / context items)——
    model_visible 目录据此可重建 skill / prompt 装配(ADR-0167 D3);
    section 只落 name + text_chars + content_digest + fallback 标记,
    不落全文(全文已在 system_prompt_sections.json)。无绑定 / 空 prompt
    时保留降级最小记录 ``{source, prompt_chars, has_tools, ...}``。
    """
    reasoner_prompt = get_current_reasoner_prompt()
    if reasoner_prompt is not None and reasoner_prompt.system_prompt_text:
        system = {
            "objective": "(from reasoner_prompt_capture)",
            "body": reasoner_prompt.system_prompt_text,
            "template_id": reasoner_prompt.template_id,
            "selector_decision_path": reasoner_prompt.selector_decision_path,
            "step_id": reasoner_prompt.step_id,
            "derived": False,
        }
    else:
        system = {"objective": "(see provider prompt catalog)", "derived": True}
    tools_raw = kwargs.get("tools")
    raw_list = list(tools_raw) if isinstance(tools_raw, (list, tuple)) else []
    # SSOT 收口:异源 tool 对象归一到 ToolSchema,防止 tools.json 落盘成空 dict。
    from lca.contracts.observability.loop_cursor_payloads import ToolSchema

    tools: list[ToolSchema] = [ToolSchema.from_any(t) for t in raw_list]
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt or ""}]
    manifest: dict[str, Any] = {
        "source": "model_visible_llm_adapter",
        "prompt_chars": len(prompt or ""),
        "has_tools": bool(tools),
        "has_temperature": "temperature" in kwargs,
        "kwargs_keys": sorted(kwargs.keys()),
    }
    context_manifest: dict[str, Any] | None = None
    if reasoner_prompt is not None and reasoner_prompt.system_prompt_text:
        manifest["template_id"] = reasoner_prompt.template_id
        manifest["selector_decision_path"] = reasoner_prompt.selector_decision_path
        trace = reasoner_prompt.prompt_trace
        if trace is not None:
            manifest["activated_skill_ids"] = list(trace.activated_skill_ids)
            manifest["available_skills_count"] = trace.available_skills_count
            manifest["tools_count"] = trace.tools_count
            manifest["sections"] = [
                {
                    "name": section.name,
                    "text_chars": section.text_chars,
                    "content_digest": _sha256_digest(section.text) if section.text else None,
                    "skipped_empty": section.skipped_empty,
                    "used_fallback": section.used_fallback,
                }
                for section in trace.sections
            ]
        perception_manifest = reasoner_prompt.context_manifest
        if perception_manifest is not None:
            manifest["context_manifest_items"] = [
                {"kind": item.kind, "payload_preview": _payload_preview(item.payload)}
                for item in perception_manifest.items
            ]
        # 绑定真值在场 ⇒ manifest 本身即 context manifest,原样落
        # context-manifest.json 供 replay cursor 对位(降级路径不写该文件)。
        context_manifest = manifest
    return system, tools, messages, manifest, context_manifest


def _safe_record_header(
    *,
    cursor: LoopCursor | None,
    artifact: ModelVisibleArtifact | None,
    model: str,
    run_dir: Path | None = None,
) -> None:
    """构造 ``RequestHeader`` 并喂给 ``cursor.record_request_header(...)``。

    manifest_digest / manifest_path 优先指向 ``context-manifest.json``
    (artifact.context_manifest_* 非 None 时);否则回退指向 manifest.json。
    ``run_dir`` 非 None 时,EP 落库后再把 header 字段持久化到
    ``model_visible/<step_id>/request-header.json`` —— replay cursor
    (:mod:`lca.infrastructure.observability.replay.cursor`)据此离线对位
    digest。

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
            manifest_digest=artifact.context_manifest_digest or artifact.manifest_digest,
            manifest_path=artifact.context_manifest_path or artifact.manifest_path,
            inherited_from_step=None,
        )
        cursor.record_request_header(header)
        if run_dir is not None:
            _write_json(
                Path(run_dir) / "model_visible" / step_id / "request-header.json",
                {
                    "step_id": header.step_id,
                    "reason": header.reason,
                    "model": header.model,
                    "system_digest": header.system_digest,
                    "system_path": header.system_path,
                    "tools_digest": header.tools_digest,
                    "tools_path": header.tools_path,
                    "messages_digest": header.messages_digest,
                    "messages_path": header.messages_path,
                    "manifest_digest": header.manifest_digest,
                    "manifest_path": header.manifest_path,
                    "inherited_from_step": header.inherited_from_step,
                },
            )
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

    def _run_capture(self, *, prompt: str, kwargs: dict[str, Any]) -> ModelVisibleArtifact | None:
        """调 capture + record_request_header;失败被吞(L10 + D5)。

        返回本次捕获的 :class:`ModelVisibleArtifact`(供后续
        ``_safe_record_thinking`` 定位同一 step 目录);任一透明分支 / 失败
        返回 ``None``。

        缺一不可:cursor 与 capture **都**必须存在才走完整 capture +
        record_request_header 链。任一缺失走透明分支(不写盘、不落 EP)。
        这是 ADR-0169 D5「profile 可关闭 model_visible capture」语义。

        ADR-0169 §L6 钉死 ``record_request_header`` 必在 THINK 窗口;真实
        生产路径上 cognitive driver 在 LLM 调用前往往还没 advance('think')
        (PR-26 阶段,coord.emit_phase → cursor.advance('think') 双写还没接)。
        这里 Adapter **自检** phase,如不是 think 且未 closed/halted/stopped,
        主动 advance('think') 打开窗口;然后 record;如已是 think 不重复
        advance(防 phase.think.fold EP 翻倍)。cursor 状态机 stop / closed
        不允许此 advance — 那时直接跳过 record(走透明语义)。

        ``_derive_capture_inputs`` 在 Reasoner 绑定真值在场时把 manifest
        同时作为 ``context_manifest`` 传给 capture —— 原样落
        ``context-manifest.json`` 并由 RequestHeader.manifest_digest/path
        指向(ADR-0167 D3/D4,replay cursor 离线对位);降级路径不写该文件。
        """
        cursor = self._cursor_provider()
        capture = self._capture_provider()
        if cursor is None or capture is None:
            return None
        # cursor 终结态(closed / halted / 已 stop 已 halt)→ 不走 capture。
        # 此检查先于 _ensure_think_phase,避免在停机后写盘到孤儿目录。
        try:
            cursor_snap = cursor.snapshot
        except Exception:
            # INTENTIONAL: cursor 已 dispose → 跳过 capture,本函数是 best-effort
            # 增强,不阻断主路径;_ensure_think_phase 自身有更深兜底。
            return None
        if cursor_snap.phase is None and cursor_snap.stop_signal is not None:
            return None
        try:
            _ensure_think_phase(cursor)
            snap = cursor.snapshot
            step_id = _step_id_for(snap.step_index + 1)
            system, tools, messages, manifest, context_manifest = _derive_capture_inputs(
                prompt=prompt, kwargs=kwargs
            )
            artifact: ModelVisibleArtifact = capture.capture(
                step_id=step_id,
                incarnation=snap.incarnation,
                system=system,
                tools=tools,
                messages=messages,
                manifest=manifest,
                context_manifest=context_manifest,
            )
        except Exception as exc:
            # capture 写盘失败:不挡业务(底 4 件套可能已部分写,artifact 也可能
            # 拿到部分 digest;但 record_request_header 必须 4 digest 全有,
            # 缺则跳过 EP;只警告一次)
            _log.warning("model_visible_capture_failed: %s", exc)
            return None
        run_dir = getattr(capture, "run_dir", None)
        _safe_record_header(
            cursor=cursor,
            artifact=artifact,
            model=self._model,
            run_dir=Path(run_dir) if run_dir is not None else None,
        )
        return artifact

    def _safe_record_thinking(
        self,
        *,
        response: LLMResponse,
        artifact: ModelVisibleArtifact | None,
    ) -> None:
        """把 LLM 最终响应落 ``model_visible/<step_id>/thinking.json`` + 记 EP。

        时序:内层返回最终响应后调 1 次(``complete()`` 返回值 / ``stream``
        的 COMPLETED 事件),每次调用只记 1 次,不按 token 记。
        与 :func:`_safe_record_header` 同纪律:``artifact is None``(无
        cursor / capture 或 capture 失败)⇒ 跳过;写盘 / cursor 失败只 log
        不抛(ADR-0169 L10 + D5),业务响应不受影响。

        ``record_thinking`` 要求 THINK 窗口:``_run_capture`` 已经
        ``_ensure_think_phase`` 开窗;若 cursor 仍抛 CursorError
        (窗口被并发切走 / closed / halted),同样兜住 + log。

        所有权:thinking.json 内容 = 本 step 模型最终响应文本;``text`` 为空
        且有 tool_calls 时落 tool_calls 摘要(call_id / name / arguments
        digest)。content_digest 指向写入文件(或等价 payload)的 canonical
        sha256;content_path 是相对 run_dir 的 POSIX relpath;token_count 取
        ``usage.completion_tokens``(provider 未返回时 None)。
        """
        if artifact is None:
            return
        cursor = self._cursor_provider()
        if cursor is None:
            return
        try:
            step_id = artifact.step_id
            text = response.text or ""
            payload: dict[str, Any] = {
                "step_id": step_id,
                "thinking_kind": "final_response",
                "text": text,
            }
            if not text and response.tool_calls:
                payload["tool_calls_summary"] = [
                    {
                        "call_id": tool_call.call_id,
                        "name": tool_call.name,
                        "arguments_digest": _sha256_digest(tool_call.arguments),
                    }
                    for tool_call in response.tool_calls
                ]
            capture = self._capture_provider()
            run_dir = getattr(capture, "run_dir", None)
            content_path: str | None = None
            if run_dir is not None:
                run_dir_path = Path(run_dir)
                thinking_path = run_dir_path / "model_visible" / step_id / "thinking.json"
                content_digest = _write_json(thinking_path, payload)
                content_path = _relative_posix(run_dir_path, thinking_path)
            else:
                content_digest = _sha256_digest(_to_jsonable(payload))
            token_count = response.usage.completion_tokens if response.usage is not None else None
            cursor.record_thinking(
                ThinkingRecord(
                    content_digest=content_digest,
                    content_path=content_path,
                    token_count=token_count,
                    thinking_kind="final_response",
                ),
                text_preview=text[:_THINKING_PREVIEW_CHARS],
            )
        except Exception as exc:
            # L10 + D5 不挡业务
            _log.warning("model_visible_record_thinking_failed: %s", exc)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        artifact = self._run_capture(prompt=prompt, kwargs=kwargs)
        response = await self._inner.complete(prompt, **kwargs)
        self._safe_record_thinking(response=response, artifact=artifact)
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        artifact = self._run_capture(prompt=prompt, kwargs=kwargs)
        thinking_recorded = False
        async for event in self._inner.stream(prompt, **kwargs):
            # COMPLETED 事件携带与 complete() 等价的最终响应(LLMStreamEvent
            # 契约);只在此记 1 次 thinking,不按 delta 记。
            if (
                not thinking_recorded
                and event.type == LLMStreamEventType.COMPLETED
                and event.response is not None
            ):
                self._safe_record_thinking(response=event.response, artifact=artifact)
                thinking_recorded = True
            yield event


__all__ = ["ModelVisibleLLMAdapter"]
