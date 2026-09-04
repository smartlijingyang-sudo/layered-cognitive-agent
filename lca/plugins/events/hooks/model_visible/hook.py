"""ModelVisibleHook —— LLM 边界 model-visible 投影（ADR-0185 §3.2 / PR-2）。

职责
----
挂在 LLM adapter 装饰器链（PR-3 装配；PR-2 仅实现类，不主动注册），每次真实
LLM 调用前后:

1. ``capture_pre_llm(kwargs, prompt)``
   - 从 :func:`get_current_cursor` + :func:`get_current_reasoner_prompt` 拿真值
   - canonicalHeader 归一化 + headerEquals fold 优化（ADR-0185 §3.5）
   - fold 命中（同 header 且非 resume）→ 跳过 publish
   - 否则 publish :class:`SpineLlmRequestHeaderPayload`,``producer=ModelVisiblePublisher``
   - 缓存最近 header 到 :attr:`_last_headers`[(run_id, step_id)]

2. ``capture_post_llm(response)``
   - 拿对应 (run_id, step_id) 最近 header
   - publish :class:`SpineLlmRequestHeaderAssistantPayload`,
     ``producer=ModelVisiblePublisher``,header_digest = sha256(canonical(prev))

透明降级(对齐 ADR-0169 D5 / L10):

- cursor 缺席 → ``capture_pre_llm`` / ``capture_post_llm`` 直接返回
- prompt 缺席 → ``capture_pre_llm`` 直接返回（旧 capture 走同样路径）
- 任一 publish 抛错 → 吞错 + log,绝不挡业务(L10)

不动旧 capture
- :mod:`lca.infrastructure.observability.adapters.model_visible_llm_adapter`
  与 ``StdModelVisibleCapture`` / ``StdReasonerPromptCapture`` PR-4 删；
  本 PR 仅添加,与旧路径双轨共存(I-MV-2 收口前的安全迁移期)。

ADR-0185 §3.2 vs reality（偏差已显式记录）:

| ADR §3.2 | reality | 偏差处置 |
|---|---|---|
| ``cursor.snapshot.inherited_from_step`` | :class:`CursorSnapshot` 无此字段 | ``resume`` 分支由 :attr:`_resume_run_step` 显式 set;默认 None,行为退化为 ``change`` |
| ``ctx.llm_adapter.decorator_chain.append(hook)`` | 无 Cordis 公开面 | PR-3 装配;PR-2 仅提供类与 ``setup`` 实例化 |
| ``results[-1].assistant_payload`` | :class:`ConsumerResult` 无此字段 | ``capture_post_llm`` 由 PR-3 装配时从 LLMResponse 提取,本类不消费 ``results`` |
| ``requires=["event.bus","llm.adapter","cursor"]`` | 后两个无 Cordis 绑定 | publisher ``requires=["event.bus"]``;hook 类显式依赖按需注入 |
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any

from lca_kernel.events.fold import EpochHeader, canonicalHeader, headerEquals
from lca_kernel.events.payloads_model_visible import (
    ReasonType,
    SpineLlmRequestHeaderAssistantPayload,
    SpineLlmRequestHeaderPayload,
)

if TYPE_CHECKING:
    from lca.contracts.observability.loop_cursor import LoopCursor
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        CurrentReasonerPrompt,
    )
    from lca_kernel.events.bus import EventBus, EventRef

_log = logging.getLogger(__name__)

# payloads_model_visible forward-ref ``AssistantRequestConfig`` / ``MessageDict``
# / ``ToolCallDict`` / ``UsageDict`` 在 TYPE_CHECKING 块定义为 ``Any``,pydantic v2
# 不会自动从 module globals 解析 + 复合 forward-ref(tuple["X", ...])在
# 普通 rebuild 下也不收口。本模块 import 时一次性 rebuild,显式提供
# ``_types_namespace`` 把 forward-ref 链钉到 Any。
# (对齐 PR-0 注释 "PR-0 在 lca_kernel.events.types 落地" 后续工作)
import typing as _typing  # noqa: E402  # intentional: must follow the TYPE_CHECKING-only imports above so rebuild_namespace is bound before any first payload instantiation.

_rebuild_ns = {
    "AssistantRequestConfig": _typing.Any,
    "MessageDict": _typing.Any,
    "ToolCallDict": _typing.Any,
    "UsageDict": _typing.Any,
}
for _payload_cls in (
    SpineLlmRequestHeaderPayload,
    SpineLlmRequestHeaderAssistantPayload,
):
    try:
        _payload_cls.model_rebuild(force=True, _types_namespace=_rebuild_ns)
    except Exception as exc:  # INTENTIONAL: 失败仅记日志,publish 主路径不挡
        _log.debug("payload_model_rebuild_skip: %s", exc)
del _payload_cls, _rebuild_ns, _typing


def _sha256_hex(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canonical_digest(header: EpochHeader) -> str:
    """sha256 hex digest of canonical header, prefixed ``sha256:``。

    对齐 ADR-0185 §3.3 ``previous_header_digest`` 字段（``sha256:<hex>``）。
    :func:`canonicalHeader` 先归一空 system / 空 tools;再按字段排序 JSON 序列化,
    字节级稳定。
    """
    payload = {
        "config": header.config,
        "adapter_defaults": header.adapter_defaults,
        "system": header.system,
        "tools": list(header.tools),
    }
    import json

    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return _sha256_hex(encoded)


def _step_id_for(step_index: int) -> str:
    """``step-{step_index:03d}`` —— 与 :class:`LoopCursor` step_id 形态一致。

    ADR-0168 §D7 + ADR-0169 D7 step_id 约定 3 位零填充;cursor.snapshot.step_id
    与 ModelVisibleCapture 派生同一形式。
    """
    return f"step-{int(step_index):03d}"


def _coerce_tools(raw: Any) -> tuple[Any, ...]:
    """kwargs.tools → tuple;非 list/tuple 输入 → ()。"""
    if isinstance(raw, (list, tuple)):
        return tuple(raw)
    return ()


def _coerce_messages(raw: Any) -> tuple[Any, ...]:
    """kwargs.messages → tuple;非 list/tuple 输入 → ()。"""
    if isinstance(raw, (list, tuple)):
        return tuple(raw)
    return ()


class ModelVisibleHook:
    """LLM 边界 model-visible 拦截钩子（ADR-0185 §3.2 / PR-2）。

    状态:

    - :attr:`_last_headers` —— per-(run_id, step_id) 最近 header 缓存;fold
      优化按此判等。
    - :attr:`_resume_run_step` —— 显式 set 的 (run_id, step_id) 集合;
      PR-3 装配时,``ReasonerPromptCapture`` 检测到 resume 路径可调
      :meth:`mark_resume`,后续同 step 的 ``capture_pre_llm`` 强制 reason
      ``resume``（无论 header 是否变化）。

    公开面:

    - :meth:`capture_pre_llm` —— LLM 调用前调;fold 优化 + publish。
    - :meth:`capture_post_llm` —— LLM 调用后调;publish assistant payload。
    - :meth:`mark_resume` —— PR-3 在检测到 resume 路径时调;透明触发
      下一次 ``capture_pre_llm`` 的 reason = ``resume``。
    - :meth:`before_publish` / :meth:`after_dispatch` —— Protocol 形状适配
      （不参与本 PR 的实际数据流;PR-3 不挂载到 bus pipeline,仅占位）。
    """

    def __init__(
        self,
        *,
        bus: EventBus[Any],
        cursor_provider: Callable[[], LoopCursor | None],
        prompt_ctx_getter: Callable[[], CurrentReasonerPrompt | None],
    ) -> None:
        self._bus = bus
        self._cursor_provider = cursor_provider
        self._prompt_ctx_getter = prompt_ctx_getter
        self._last_headers: dict[tuple[str, str], EpochHeader] = {}
        self._resume_run_step: set[tuple[str, str]] = set()

    # ── 状态管理 ────────────────────────────────────────────────────

    def mark_resume(self, run_id: str, step_id: str) -> None:
        """标记 ``(run_id, step_id)`` 后续 :meth:`capture_pre_llm` 应取 ``resume`` reason。

        PR-3 装配:ReasonerPromptCapture 检测到 ``cursor.snapshot.iteration_reason
        == "checkpoint_resume"`` 时调本方法;非 PR-2 主路径。
        """
        self._resume_run_step.add((run_id, step_id))

    def forget_run(self, run_id: str) -> None:
        """run 收口时清缓存;cursor.close 后调,避免 dict 长期增长。"""
        self._last_headers = {k: v for k, v in self._last_headers.items() if k[0] != run_id}
        self._resume_run_step = {k for k in self._resume_run_step if k[0] != run_id}

    # ── PreDispatchHook 形状(ADR-0185 §3.2)─────────────────────────

    def before_publish(
        self,
        payload: Any,
        producer: type,
        ctx: Any,
    ) -> Any:
        """Protocol 形状占位 —— 不参与 PR-2 数据流;返回 payload 原值。

        PR-3 不挂载本 hook 到 bus pipeline(详见模块 docstring 偏差表);
        此方法保留以保持 :class:`PreDispatchHook` 形状,便于未来 PR 切换到
        bus pipeline 形态时 0 改动。
        """
        return payload

    def after_dispatch(
        self,
        payload: Any,
        ref: Any,
        results: list[Any],
    ) -> Iterable[Any]:
        """Protocol 形状占位 —— 不参与 PR-2 数据流;返回空。"""
        return ()

    # ── 真实数据流入口(PR-3 装配调) ────────────────────────────────

    def capture_pre_llm(
        self,
        *,
        run_id: str,
        step_index: int,
        incarnation: int,
        kwargs: Mapping[str, Any],
    ) -> EventRef | None:
        """LLM 调用前:fold 优化 + publish ``spine.llm.request.header``。

        Args:
            run_id: 透传到 payload 的 run 标识。
            step_index: cursor.snapshot.step_index;step_id = ``f"step-{step_index + 1:03d}"``。
            incarnation: cursor.snapshot.incarnation。
            kwargs: LLM adapter 调用的 kwargs;读 ``config`` / ``tools`` /
                ``messages`` / ``manifest`` / ``system``(若 model 注入)。

        Returns:
            ``EventRef`` 或 ``None``(透明降级 / fold 跳过)。

        失败语义:

        - cursor 缺席 / prompt 缺席 → 透明降级,返回 ``None``,不发盘。
        - fold 命中(headerEquals(prev, current) 且非 resume)→ 跳过,返回 ``None``。
        - 任一 publish 抛错 → 吞错 + log,返回 ``None``(L10)。
        """
        prompt = self._prompt_ctx_getter()
        if prompt is None:
            return None

        step_id = _step_id_for(step_index + 1)
        system_text = prompt.system_prompt_text or ""

        current = EpochHeader(
            config=kwargs.get("config"),
            system=system_text or None,
            tools=_coerce_tools(kwargs.get("tools")),
        )
        current = canonicalHeader(current)

        key = (run_id, step_id)
        previous = self._last_headers.get(key)
        previous_digest = _canonical_digest(previous) if previous is not None else None

        is_resume = key in self._resume_run_step
        if is_resume:
            reason: ReasonType = "resume"
        elif previous is None:
            reason = "initial"
        elif headerEquals(previous, current):
            return None  # fold 优化:同 header 不发
        else:
            reason = "change"

        messages = _coerce_messages(kwargs.get("messages"))
        manifest = kwargs.get("manifest")

        # tools 字段期望 ``tuple[ToolSchema, ...]``;EPOCH header 把 tools
        # 视作 Mapping 序列(对齐 dsh 字节级比较)。Runtime 序列化由 pydantic
        # model_serializer 决定;严格窄化留给 PR-3 真实 LLM 接入。
        from typing import cast

        payload_obj = SpineLlmRequestHeaderPayload(
            step_id=step_id,
            incarnation=incarnation,
            config=current.config if current.config is not None else {},
            system=current.system or "",
            tools=cast("Any", tuple(current.tools or ())),
            messages=cast("Any", messages),
            manifest=manifest,
            reason=reason,
            previous_header_digest=previous_digest,
        )
        ref: EventRef | None
        try:
            from lca.plugins.events.publishers._session_publish import publish_via_session
            from lca.plugins.events.publishers.model_visible.publisher import (
                ModelVisiblePublisher,
            )

            ref = publish_via_session(payload_obj, producer=ModelVisiblePublisher)
        except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
            _log.warning("model_visible_pre_publish_failed: %s", exc)
            return None

        self._last_headers[key] = current
        # resume 一次性标记:publish 后清除(下次 capture_pre_llm 走 change/initial)
        self._resume_run_step.discard(key)
        return ref

    def capture_post_llm(
        self,
        *,
        run_id: str,
        step_index: int,
        incarnation: int,
        response: Any,
    ) -> EventRef | None:
        """LLM 调用后:publish ``spine.llm.request.header.assistant``。

        Args:
            run_id: 透传到 payload 的 run 标识。
            step_index: cursor.snapshot.step_index;step_id = ``f"step-{step_index + 1:03d}"``。
            incarnation: cursor.snapshot.incarnation。
            response: LLM 响应对象;读取 ``content`` / ``tool_calls`` /
                ``finish_reason`` / ``usage`` 属性。形态不匹配 → 字段取空值
                (``""`` / ``()`` / ``{}``),仍 publish(降级而非跳过,便于
                viewer 看到 assistant 事件存在)。

        Returns:
            ``EventRef`` 或 ``None``(透明降级 / publish 失败)。

        失败语义:

        - 对应 (run_id, step_id) 无最近 header → 仍 publish,header_digest
          = 空字符串(对齐 ADR-0185 §3.3 ``header_digest`` 必填语义;
          空 = 未关联 request header)。
        - 任一 publish 抛错 → 吞错 + log(L10)。
        """
        step_id = _step_id_for(step_index + 1)
        key = (run_id, step_id)
        previous = self._last_headers.get(key)
        digest = _canonical_digest(previous) if previous is not None else ""

        assistant_content = getattr(response, "content", "") or ""
        finish_reason = getattr(response, "finish_reason", "") or ""
        usage = getattr(response, "usage", None) or {}
        tool_calls_raw = getattr(response, "tool_calls", None) or ()
        tool_calls = tuple(tool_calls_raw) if isinstance(tool_calls_raw, (list, tuple)) else ()

        payload_obj = SpineLlmRequestHeaderAssistantPayload(
            step_id=step_id,
            incarnation=incarnation,
            assistant_content=str(assistant_content),
            tool_calls=tool_calls,
            finish_reason=str(finish_reason),
            usage=usage,
            header_digest=digest,
        )
        try:
            from lca.plugins.events.publishers._session_publish import publish_via_session
            from lca.plugins.events.publishers.model_visible.publisher import (
                ModelVisiblePublisher,
            )

            return publish_via_session(payload_obj, producer=ModelVisiblePublisher)
        except Exception as exc:  # INTENTIONAL: L10 + D5 不挡业务
            _log.warning("model_visible_post_publish_failed: %s", exc)
            return None


__all__ = ["ModelVisibleHook"]
