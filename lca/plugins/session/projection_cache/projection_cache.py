"""ProjectionCache —— 持久化投影缓存（DSH session-projection-cache 的 LCA 形态）。

把 ``registry.checkpoint(session)`` 的检查点行（``key → {version, seq,
state}``）以 per-session 一个 JSON 文档写到
``<cache_root>/<session_id>.projcache.json``。

**缓存永不是真值** —— Session 事件日志才是唯一真值；缓存行只是 fold
快捷方式：可能旧（``seq`` 说明有多旧）但永不错。由此：

- 全部写路径 fail-soft：写失败只记结构化日志，永不抛、永不反噬
  ``Session.append``；丢一次写只令下次冷读多折一段尾；
- ``state_version`` 失配即整行丢弃（不猜测、不迁移）；``restore``
  失败即全量重折（见 :meth:`ProjectionCache.cold_snapshot`）；
- 强制写点：``turn.ended.v1`` 事件到达（observer 订阅）与
  :meth:`ProjectionCache.close` 最终写（live→cold 时刻）。

与 DSH 形态的偏差：DSH 走 storage domain（``session_projcache``，
write-behind 节流 + 创建/``turn/end``/dispose 三强制点 + 身份见证）；
LCA 对齐 write-behind 批量落盘（``AtomicJsonFileSink``），强制写点：
``turn.ended.v1``、``Session.flush()`` 与 ``close()`` 最终写。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.session.projection_unit import (
    ProjectionCheckpoint,
    ProjectionSnapshot,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.persistence.atomic_json_sink import AtomicJsonFileSink, AtomicJsonSnapshot
from lca.infrastructure.persistence.write_behind import WriteBehindBuffer
from lca_kernel.events.session import SessionEvent

if TYPE_CHECKING:
    from lca_kernel.events.session import SessionProtocol

_log = structlog.get_logger(__name__)

__all__ = ["Config", "ProjectionCache", "setup"]

_FILE_SUFFIX = ".projcache.json"
_CACHE_ROOT_DEFAULT = "traces/projcache"
_TURN_ENDED = "turn.ended.v1"


class Config(BaseModel):
    """plugin 配置：缓存文档根目录；拒绝未知键。"""

    model_config = {"extra": "forbid"}

    cache_root: str = _CACHE_ROOT_DEFAULT
    """缓存文档根目录；每个 session 一个 ``<session_id>.projcache.json``。"""


class _CacheObserver:
    """把 :class:`ProjectionCache` 装成 Session observer 的适配器。

    只承接 ``turn.ended.v1`` 强制写点；enqueue 到 write-behind buffer。
    """

    def __init__(self, cache: ProjectionCache) -> None:
        self._cache = cache

    def __call__(self, session: Any, event: SessionEvent) -> None:
        if event.type == _TURN_ENDED:
            self._cache.save(session)


class _ProjectionCacheFlushListener:
    """``Session.flush()`` 链：排空 projection cache write-behind buffer。"""

    def __init__(self, cache: ProjectionCache) -> None:
        self._cache = cache

    async def flush(self, session: SessionProtocol) -> None:
        del session
        self._cache.flush_sync()


class ProjectionCache:
    """per-session JSON 检查点缓存（fold 快捷方式，永不是真值）。

    ``registry`` 须具备 ``checkpoint(session)`` / ``restore(checkpoint,
    events, header)`` / ``state_version_of(key)`` 面（即
    ``session.projections`` capability，:class:`ProjectionRegistry`）；
    插件间禁止直接 import，故此处按结构鸭子型接收。
    """

    def __init__(self, registry: Any, cache_root: Path | str | None = None) -> None:
        """构造 detached 缓存；``cache_root`` 缺省 = ``traces/projcache``。

        实例化阶段不创建目录；目录在首次写时按需建立。
        """
        self._registry = registry
        self._cache_root = Path(cache_root) if cache_root is not None else Path(_CACHE_ROOT_DEFAULT)
        self._tracked: dict[str, Any] = {}
        self._store_hooks: list[Callable[[], None]] = []
        self._closed = False
        self._sink = AtomicJsonFileSink()
        self._buffer = WriteBehindBuffer(self._sink, max_delay_ms=200)

    # ── 公开面 ──────────────────────────────────────────────────────

    def path_for(self, session_id: str) -> Path:
        """``session_id`` 的缓存文档路径（不创建文件）。"""
        return self._cache_root / f"{session_id}{_FILE_SUFFIX}"

    def register_to(self, session: Any) -> Callable[[], None]:
        """把强制写点 observer + flush listener 挂到给定 Session。

        ``turn.ended.v1`` enqueue 检查点；``Session.flush()`` 显式 drain。
        返回合并的幂等取消函数。
        """
        session_id = _session_id(session)
        if session_id != "unknown":
            self._tracked[session_id] = session
        observe_cancel = session.observe(_CacheObserver(self))
        flush_cancel: Callable[[], None] | None = None
        register_flush = getattr(session, "register_flush_listener", None)
        if callable(register_flush):
            flush_cancel = register_flush(_ProjectionCacheFlushListener(self))

        def cancel() -> None:
            observe_cancel()
            if flush_cancel is not None:
                flush_cancel()

        return cancel

    def flush_sync(self) -> None:
        """显式排空 write-behind buffer（``Session.flush`` / 测试用）。"""
        self._buffer.flush()

    def save(self, session: Any) -> bool:
        """Enqueue 一个活 session 的检查点（强制写点的落盘体）。

        fail-soft：checkpoint 取切或 enqueue 失败只记结构化日志，永不抛；
        返回是否成功入队（落盘由 write-behind 异步完成）。
        """
        session_id = _session_id(session)
        try:
            rows = self._registry.checkpoint(session)
            payload = {
                key: {"version": row.version, "seq": row.seq, "state": row.state}
                for key, row in rows.items()
            }
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except Exception:
            _log.warning(
                "session.projection_cache.checkpoint_failed",
                session_id=session_id,
                exc_info=True,
            )
            return False
        try:
            self._buffer.enqueue(
                AtomicJsonSnapshot(path=self.path_for(session_id), encoded=encoded)
            )
            return True
        except Exception:
            _log.warning(
                "session.projection_cache.enqueue_failed",
                session_id=session_id,
                path=str(self.path_for(session_id)),
                exc_info=True,
            )
            return False

    def load(self, session_id: str) -> dict[str, ProjectionCheckpoint] | None:
        """读一个 session 的检查点行；文档缺失 / 损坏返回 ``None``。

        整行弃，不猜测：JSON 解析失败或非 Mapping 文档 → ``None``；
        单行形状非法（缺 ``state``、``version``/``seq`` 非整数）或
        ``version`` 与当前注册单元失配（含 key 未注册）→ 弃该行。
        返回行可直接喂 ``registry.restore``。
        """
        path = self.path_for(session_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            doc = json.loads(raw)
        except ValueError:
            _log.warning(
                "session.projection_cache.doc_corrupt", session_id=session_id, path=str(path)
            )
            return None
        if not isinstance(doc, dict):
            _log.warning(
                "session.projection_cache.doc_shape", session_id=session_id, path=str(path)
            )
            return None
        rows: dict[str, ProjectionCheckpoint] = {}
        for key, value in doc.items():
            row = self._parse_row(key, value)
            if row is not None:
                rows[key] = row
        return rows

    def cold_snapshot(self, session: Any) -> ProjectionSnapshot:
        """冷读：先试带缓存行的 ``restore``；失败即全量重折。

        缓存行只是快捷方式：带行 ``restore`` 抛错（旧行形状漂移 / 单元
        fold 拒绝旧状态）即弃缓存，从完整日志重新折（**恢复失败 ⟹
        全量重折**）；重折仍失败是单元自身错误，向上 fail-loud。
        """
        events = session.snapshot_events()
        session_id = _session_id(session)
        rows = self.load(session_id) or {}
        try:
            result = self._registry.restore(rows, events, session.header)
        except Exception:
            _log.warning(
                "session.projection_cache.restore_failed_refold",
                session_id=session_id,
                exc_info=True,
            )
            result = self._registry.restore({}, events, session.header)
        return cast("ProjectionSnapshot", result.snapshot)

    def close(self) -> None:
        """最终写（live→cold 时刻）：全部跟踪 session 落盘 + 释放 store 钩子。

        幂等：第二次起为 no-op。close 后再 ``register_to`` 仍可工作
        （手动路径），但其最终写由下一次 :meth:`close` 承担。
        """
        if self._closed:
            return
        self._closed = True
        for session in tuple(self._tracked.values()):
            self.save(session)
        self._buffer.dispose()
        self._tracked.clear()
        for cancel in self._store_hooks:
            cancel()
        self._store_hooks.clear()

    # ── 内部 ────────────────────────────────────────────────────────

    def _parse_row(self, key: str, value: Any) -> ProjectionCheckpoint | None:
        """整行形状化；任何非法整行弃（不猜测）。"""
        if not isinstance(value, dict):
            return None
        version = value.get("version")
        seq = value.get("seq")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or not isinstance(seq, int)
            or isinstance(seq, bool)
            or "state" not in value
        ):
            return None
        expected = self._registry.state_version_of(key)
        if expected is None or version != expected:
            return None
        return ProjectionCheckpoint(version=version, seq=seq, state=value["state"])


def _session_id(session: Any) -> str:
    """从 Session 实例派生 session id；缺 ``.id`` 回退 ``"unknown"``。

    Session 协议保证 :attr:`Session.id` 权威（与 ``persistence_jsonl``
    的 Session 实例权威规则一致）。
    """
    sid = getattr(session, "id", None)
    if isinstance(sid, str) and sid:
        return sid
    return "unknown"


def _attach_to_store(store: Any, cache: ProjectionCache) -> None:
    """对 store 当前活 Session 挂强制写点 observer，并接管未来新 Session。

    时序与失败语义对齐 ``persistence_jsonl._attach_to_store``：先对现存
    Session 一次性挂入，再经 ``add_observer_hook`` 接管未来 ``create`` /
    ``restore``；缺钩子抛 ``TypeError``（fail-loud）；单个 Session 挂入
    失败 contained。钩子反注册闭包存 ``cache._store_hooks``，``close()``
    时释放。
    """
    for session in getattr(store, "list", lambda: ())():
        try:
            cache.register_to(session)
        except Exception:
            _log.warning(
                "session.projection_cache.attach_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)

    def _on_create(session: Any) -> None:
        try:
            cache.register_to(session)
        except Exception:
            _log.warning(
                "session.projection_cache.attach_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )

    cancel = hook(_on_create)
    if callable(cancel):
        cache._store_hooks.append(cancel)


@plugin(
    id="lca.plugins.session.projection_cache",
    provides=["session.projection_cache"],
    requires=["session.projections"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="filesystem",
    description=(
        "持久化投影缓存（模块②，DSH session-projection-cache 对照形态）："
        "把 registry.checkpoint 行以 per-session 一个 JSON 文档写到 "
        "<cache_root>/<session_id>.projcache.json。缓存永不是真值：写 "
        "fail-soft，version 失配弃整行，restore 失败即全量重折。强制写点："
        "turn.ended.v1 到达 + Session.flush() + close() 最终写。"
    ),
    test_suite="tests/plugins/session/test_projection_cache.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.projections", "session.store"),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """投影缓存 boot。

    行为契约：

    1. 经 ``ctx.require`` 从 ``session.projections`` 拿 registry（硬
       依赖：缺席显式失败，对齐 DSH ``inject`` 形态）；
    2. 构造 :class:`ProjectionCache` 并提供 ``session.projection_cache``;
    3. ``session.store`` 装载时（soft），把强制写点 observer 挂到活
       Session 与未来 Session；未装载时 no-op（不抛），测试可手动
       ``register_to``。
    """
    registry = ctx.require("session.projections")
    cache = ProjectionCache(registry, cache_root=config.cache_root)
    ctx.provide("session.projection_cache", cache)
    store = ctx.soft_get("session.store")
    if store is None:
        _log.info("session.projection_cache.no_store", id="lca.plugins.session.projection_cache")
        return
    _attach_to_store(store, cache)
