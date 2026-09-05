"""SessionTitleService —— DSH session-title 一比一对位(ADR-0188)。

标题是日志事件,不是旁路存储(``session-event-pipeline-spec.md`` §4.3):
fold 最新 ``session.title.v1``(latest-wins),写回只经 ``Session.append``;
事件 ``visibility="audit"``,log-only,绝不进模型可见面。确定性回退(首条
合格用户消息)+ 可选 provider(first-prompt,per-session revision 取代);
``source="user"`` 钉住自动调度,``refresh`` 解钉;一切失败 contained,
绝不阻塞主响应,绝不反噬 append。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import structlog
from pydantic import BaseModel, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.harness.memory.events import MessageAccepted, SessionTitle
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_log = structlog.get_logger(__name__)

TITLE_EVENT_TYPE: str = str(SessionTitle._event_type)  # type: ignore[attr-defined]
USER_MESSAGE_EVENT_TYPE: str = str(MessageAccepted._event_type)  # type: ignore[attr-defined]
SOURCE_FALLBACK = "fallback"
SOURCE_PROVIDER = "provider"
SOURCE_USER = "user"

# 清洗规则对齐 DSH normalize.ts:OSC / CSI / ESC 序列、C0/C1 控制字符、方向性隐形字符。
_STRIP_PATTERNS = (
    re.compile(r"(?:\u001B\]|\u009D)(?:(?!\u0007|\u001B\\)[\s\S])*(?:\u0007|\u001B\\|$)"),
    re.compile(r"(?:\u001B\[|\u009B)[0-?]*[ -/]*[@-~]"),
    re.compile(r"\u001B[@-_]"),
    re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]"),
    re.compile(r"[\u200B\u200E\u200F\u202A-\u202E\u2060-\u2064\u2066-\u206F\uFEFF]"),
)
_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class TitleUserMessage:
    """一条合格的用户文本消息(对位 DSH ``SessionTitleUserMessage``)。"""

    seq: int
    text: str


@runtime_checkable
class SessionTitleProvider(Protocol):
    """标题 provider duck-type 契约;``signal`` 在被取代时被 set。"""

    id: str
    automatic: str

    async def generate(
        self, session: Any, messages: Sequence[TitleUserMessage], signal: asyncio.Event
    ) -> Mapping[str, Any]: ...


class Config(BaseModel):
    """标题服务配置;拒绝未知键防声明漂移(上限对位 DSH Config)。"""

    model_config = {"extra": "forbid"}

    fallback_max_words: int = Field(default=5, ge=1)
    fallback_max_bytes: int = Field(default=40, ge=1)
    max_title_bytes: int = Field(default=80, ge=1)


@dataclass
class _WorkState:
    """per-session 自动调度并发状态(对位 DSH ``SessionTitleWorkState``)。"""

    revision: int = 0
    active_task: asyncio.Task[None] | None = None
    active_revision: int = -1
    active_signal: asyncio.Event | None = None


def normalize_title(text: str, max_words: int | None = 5, max_bytes: int = 40) -> str:
    """确定性标题归一化 + 词数/UTF-8 字节双上限(对位 DSH ``fallbackSessionTitle``;
    ``max_words=None`` 只做字节截断,等价 ``normalizeSessionTitle``)。截断不劈开码点。"""
    if max_bytes <= 0 or (max_words is not None and max_words <= 0):
        raise ValueError("max_words/max_bytes must be positive integers")
    cleaned = _clean_text(text)
    if max_words is not None:
        cleaned = " ".join([word for word in cleaned.split(" ") if word][:max_words])
    if len(cleaned.encode("utf-8")) <= max_bytes:
        return cleaned.rstrip()
    used = 0
    for index, character in enumerate(cleaned):
        used += len(character.encode("utf-8"))
        if used > max_bytes:
            return cleaned[:index].rstrip()
    return cleaned.rstrip()


def _clean_text(text: str) -> str:
    """去 ANSI/控制/方向性隐形字符,压缩空白,产出单行干净文本。"""
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub("", text)
    return _WHITESPACE_RUN.sub(" ", text).strip()


def _user_message_of(event: Any) -> TitleUserMessage | None:
    """从 session 事件提取一条合格用户文本消息(清洗后非空)。"""
    if event.type != USER_MESSAGE_EVENT_TYPE or event.data.get("role") != "user":
        return None
    text = event.data.get("content_ref")
    if not isinstance(text, str) or not _clean_text(text):
        return None
    return TitleUserMessage(seq=event.seq, text=text)


def _collect_messages(session: Any, through_seq: int | None = None) -> list[TitleUserMessage]:
    """按 seq 顺序收集合格用户文本消息;``through_seq`` 为包含式上界。"""
    messages: list[TitleUserMessage] = []
    for event in session.snapshot_events():
        if through_seq is not None and event.seq > through_seq:
            break
        message = _user_message_of(event)
        if message is not None:
            messages.append(message)
    return messages


def _validate_result(
    result: Any, messages: Sequence[TitleUserMessage], max_title_bytes: int
) -> tuple[str, tuple[int, ...]]:
    """校验并归一化 provider 输出(对位 DSH ``validateResult``):拒绝空标题、
    空/非请求快照内/不唯一/不升序的 ``message_seqs``。"""
    if not isinstance(result, Mapping):
        raise ValueError("session-title provider returned an invalid result")
    title_raw = result.get("title")
    if not isinstance(title_raw, str):
        raise ValueError("session-title provider title must be a string")
    title = normalize_title(title_raw, max_words=None, max_bytes=max_title_bytes)
    if not title:
        raise ValueError("session-title provider returned an empty title")
    seqs_raw = result.get("message_seqs")
    if isinstance(seqs_raw, str | bytes) or not isinstance(seqs_raw, Sequence) or not seqs_raw:
        raise ValueError("session-title provider must identify at least one source message seq")
    order = {message.seq: index for index, message in enumerate(messages)}
    seqs: list[int] = []
    previous = -1
    for raw in seqs_raw:
        index = order.get(raw) if isinstance(raw, int) and not isinstance(raw, bool) else None
        if index is None or index <= previous:
            raise ValueError("session-title provider messageSeqs must be unique, ordered seqs")
        seqs.append(raw)
        previous = index
    return title, tuple(seqs)


class SessionTitleService:
    """日志事件形态的标题服务:fold 读取 + 经 ``Session.append`` 写入,失败 contained。"""

    def __init__(self, config: Config | None = None) -> None:
        """构造 detached service;``fallback_max_bytes > max_title_bytes`` 抛 ``ValueError``。"""
        self._config = config or Config()
        if self._config.fallback_max_bytes > self._config.max_title_bytes:
            raise ValueError("session-title: fallback_max_bytes must not exceed max_title_bytes")
        self._provider: SessionTitleProvider | None = None
        self._work: dict[str, _WorkState] = {}
        self._inflight: set[asyncio.Task[Any]] = set()
        self._store_hooks: list[Callable[[], None]] = []
        self._closed = False

    def get(self, session: Any) -> str | None:
        """fold 读取最新标题文本(latest-wins);无标题事件返回 ``None``。"""
        event = self._fold_title_event(session)
        return None if event is None else str(event.data.get("title"))

    def rename(self, session: Any, title: str) -> None:
        """接受显式用户标题并钉住(自动调度停止;``refresh`` 是唯一解钉)。

        清洗后必须非空且不超过 ``max_title_bytes``,违反抛 ``ValueError``
        (LCA 显式拒绝超长而非 DSH 静默截断,见 ADR-0188 §3);先取代在途
        自动生成,再写 ``source="user"`` 标题事件。
        """
        cleaned = _clean_text(title)
        if not cleaned:
            raise ValueError("session title must contain visible characters")
        if len(cleaned.encode("utf-8")) > self._config.max_title_bytes:
            raise ValueError(
                f"session title exceeds max_title_bytes={self._config.max_title_bytes}"
            )
        self._supersede(self._state_for(session.id), "user rename superseded automatic title")
        session.append(
            TITLE_EVENT_TYPE, {"title": cleaned, "message_seqs": [], "source": SOURCE_USER}
        )

    def refresh(self, session: Any) -> None:
        """唯一有意解钉:无 provider 时重派回退覆盖 ``user`` 钉住(否则仅在无标题时
        补齐回退);有 provider 时以全部合格消息调度一次生成。"""
        messages = _collect_messages(session)
        if self._provider is None:
            event = self._fold_title_event(session)
            pinned = event is not None and event.data.get("source") == SOURCE_USER
            if pinned and messages:
                self._append_fallback(session, messages[0])
            else:
                self._ensure_fallback(session)
        elif messages:
            self._start_provider(session, self._state_for(session.id), messages[-1].seq)

    def register_provider(self, provider: SessionTitleProvider) -> Callable[[], None]:
        """注册唯一可选 provider(形状校验见 ``_validate_provider``;重复注册抛
        ``ValueError``)。返回的取消函数反注册并取代在途工作(幂等)。"""
        self._validate_provider(provider)
        if self._provider is not None:
            existing = getattr(self._provider, "id", "<unknown>")
            raise ValueError(f"session-title provider {existing!r} is already registered")
        self._provider = provider

        def cancel() -> None:
            if self._provider is not provider:
                return
            self._provider = None
            for state in self._work.values():
                self._supersede(state, "session-title provider was disposed")

        return cancel

    def attach_to_store(self, store: Any) -> None:
        """挂到 SessionStore:活 Session 逐个挂入 + ``add_observer_hook`` 接管未来
        ``create``/``restore``(抄 ``persistence_jsonl._attach_to_store``;store 缺钩子
        抛 ``TypeError`` fail-loud,单个 Session 挂入失败 contained)。"""
        hook = getattr(store, "add_observer_hook", None)
        if not callable(hook):
            msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
            raise TypeError(msg)
        for session in getattr(store, "list", lambda: ())():
            self._attach_session(session)
        cancel = hook(self._attach_session)
        if callable(cancel):
            self._store_hooks.append(cancel)

    def _attach_session(self, session: Any) -> None:
        """把 observer 挂到单个 Session;挂入失败 contained。"""
        try:
            session.observe(_TitleObserver(self))
        except Exception:
            _log.warning("session.title.attach_failed", exc_info=True)

    def close(self) -> None:
        """停止服务:反注册、取消全部在途工作、释放 store 接管(幂等)。"""
        self._closed = True
        self._provider = None
        for state in self._work.values():
            self._supersede(state, "session-title service disposed")
        for cancel in self._store_hooks:
            cancel()
        self._store_hooks.clear()

    async def drain(self) -> None:
        """等待全部在途 defer 工作落定(测试 / teardown 用)。"""
        while self._inflight:
            await asyncio.gather(*tuple(self._inflight), return_exceptions=True)

    def _on_session_event(self, session: Any, event: Any) -> None:
        """observer 入口:只收合格用户消息;异常全 contained,绝不反噬 append。"""
        try:
            if self._closed or _user_message_of(event) is None:
                return
            self._defer(self._on_user_message(session, event.seq))
        except Exception:
            _log.warning("session.title.observer_failed", exc_info=True)

    async def _on_user_message(self, session: Any, through_seq: int) -> None:
        """一条合格用户消息的延迟调度:回退立即追加 + first-prompt provider 调度。"""
        current = self._fold_title_event(session)
        if current is not None and current.data.get("source") == SOURCE_USER:
            return  # 用户重命名钉住:任何自动修订不得覆盖
        messages = _collect_messages(session)
        if not messages:
            return
        if current is None:
            self._append_fallback(session, messages[0])
        if self._provider is None or self._closed or len(messages) != 1:
            return
        self._start_provider(session, self._state_for(session.id), through_seq)

    def _start_provider(self, session: Any, state: _WorkState, through_seq: int) -> None:
        """取代旧工作并调度一次当前 provider 修订。"""
        revision = self._supersede(state, "newer title scheduling superseded older generation")
        signal = asyncio.Event()
        state.active_task = self._defer(
            self._run_provider(session, state, revision, through_seq, signal)
        )
        state.active_revision = revision
        state.active_signal = signal

    async def _run_provider(
        self,
        session: Any,
        state: _WorkState,
        revision: int,
        through_seq: int,
        signal: asyncio.Event,
    ) -> None:
        """执行并接受一次当前 provider 修订;失败 contained,取消透传。"""
        provider = self._provider
        try:
            if provider is None or self._closed:
                return
            self._ensure_fallback(session)
            if not self._is_current(session, state, revision, provider):
                return
            messages = _collect_messages(session, through_seq)
            result = await provider.generate(session, messages, signal)
            if not self._is_current(session, state, revision, provider):
                return  # 过期完成结果:丢弃
            title, seqs = _validate_result(result, messages, self._config.max_title_bytes)
            session.append(
                TITLE_EVENT_TYPE,
                {"title": title, "message_seqs": list(seqs), "source": SOURCE_PROVIDER},
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.warning(
                "session.title.provider_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )

    def _fold_title_event(self, session: Any) -> Any:
        """从事件快照折叠最新标题事件;畸形事件跳过(视作无标题)。"""
        for event in reversed(session.snapshot_events()):
            title = event.data.get("title") if event.type == TITLE_EVENT_TYPE else None
            if isinstance(title, str) and title:
                return event
        return None

    def _append_fallback(self, session: Any, first: TitleUserMessage) -> None:
        """追加确定性回退标题;同步执行——推导与 append 不得被 await 拆开。"""
        title = normalize_title(
            first.text, self._config.fallback_max_words, self._config.fallback_max_bytes
        )
        if title:
            session.append(
                TITLE_EVENT_TYPE,
                {"title": title, "message_seqs": [first.seq], "source": SOURCE_FALLBACK},
            )

    def _ensure_fallback(self, session: Any) -> None:
        """仅当 session 尚无标题时创建首个确定性回退标题。"""
        if self._fold_title_event(session) is not None:
            return
        messages = _collect_messages(session)
        if messages:
            self._append_fallback(session, messages[0])

    def _state_for(self, session_id: str) -> _WorkState:
        state = self._work.get(session_id)
        if state is None:
            state = _WorkState()
            self._work[session_id] = state
        return state

    def _supersede(self, state: _WorkState, reason: str) -> int:
        """取消在途工作、set 其 signal,并预留下一个 revision。"""
        if state.active_task is not None and not state.active_task.done():
            state.active_task.cancel()
        if state.active_signal is not None:
            state.active_signal.set()
        state.active_task, state.active_revision, state.active_signal = None, -1, None
        state.revision += 1
        _log.debug("session.title.superseded", reason=reason, revision=state.revision)
        return state.revision

    def _is_current(
        self, session: Any, state: _WorkState, revision: int, provider: SessionTitleProvider
    ) -> bool:
        """完成路径守卫:注册、状态对象、修订任一过期即拒绝接受。"""
        return (
            not self._closed
            and self._provider is provider
            and self._work.get(session.id) is state
            and state.revision == revision == state.active_revision
        )

    def _defer(self, coro: Any) -> asyncio.Task[None] | None:
        """调度分离式工作;无运行中事件循环时 contained 返回 ``None``(``Session.append``
        是同步的,observer 可能在同步上下文被 fire;标题缺席不阻塞主响应,ADR-0188 §3)。"""
        if self._closed:
            coro.close()
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            _log.debug("session.title.no_running_loop")
            return None
        task = loop.create_task(self._guarded(coro))
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)
        return task

    async def _guarded(self, coro: Any) -> None:
        """contain 全部 defer 工作失败:取消透传(取代语义),其余只记日志。"""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.warning("session.title.deferred_failed", exc_info=True)

    def _validate_provider(self, provider: object) -> None:
        """注册前形状校验(对位 DSH ``validateProvider``)。"""
        provider_id = getattr(provider, "id", None)
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("session-title provider id must be a non-empty string")
        if getattr(provider, "automatic", None) != "first-prompt":
            raise ValueError("session-title provider automatic mode is invalid")
        if not callable(getattr(provider, "generate", None)):
            raise ValueError(f"session-title provider {provider_id!r} requires generate()")


class _TitleObserver:
    """Session observer 适配器:把用户消息事件派发给服务调度面。"""

    def __init__(self, service: SessionTitleService) -> None:
        self._service = service

    def __call__(self, session: Any, event: Any) -> None:
        self._service._on_session_event(session, event)


@plugin(
    id="lca.plugins.session.title_service",
    provides=["session.title"],
    requires=["session.store"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "SessionTitleService(ADR-0188):标题是日志事件(session.title.v1,log-only);"
        "确定性回退 + 可选 provider(first-prompt,revision 取代)+ rename pin/refresh 解钉。"
    ),
    test_suite="tests/plugins/session/test_title_service.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.store",), emits=(), state_mutation="reducer-only"
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """boot:构造 service、provide ``session.title``、挂 session.store;store 未装载时
    no-op 保留 capability 供测试后注册(对齐 persistence_jsonl)。"""
    service = SessionTitleService(config)
    ctx.provide("session.title", service)
    store = ctx.soft_get("session.store")
    if store is None:
        _log.info("session.title.no_store", id="lca.plugins.session.title_service")
        return
    service.attach_to_store(store)
