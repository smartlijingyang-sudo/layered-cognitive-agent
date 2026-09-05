"""ProjectionRegistry —— DSH session-projection 一比一的 LCA 投影注册表。

消费模块②投影（``docs/specs/session-event-pipeline-spec.md`` §4.3）框架侧：
领域单元（:class:`ProjectionUnit` 契约）只做纯同步 fold；本注册表拥有订阅、
per-session 水位缓存与变更通知，客户端出口是完整值，绝不外发 fold 中间事件。
驱动形态（对齐 DSH ``SessionProjectionRegistry``）：每个 Session 经
``register_to`` 挂一条 observer（适配器无 ``flush`` 面，不参与 ``Session.flush``
链），每条已提交事件急切穿过全部单元的 ``apply``；``apply`` 返回与前一状态
``==`` 的结果视为无变化，不触发变更订阅；迟到注册 / 迟到 session 首次触及时
从 ``session.snapshot_events()`` 折历史；注册引用计数，同 key 共享一个单元，
最后一个取消者移除 key。失败语义（§8「单元错误不波及」）：单元 apply / init
/ view / 订阅者错误 contained；apply 抛错水位照常推进（跳过毒事件保后续可用）。
"""

from __future__ import annotations

import contextlib
import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

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
    ProjectionUnit,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.events.session import SessionEvent, SessionHeader

_log = structlog.get_logger(__name__)

__all__ = ["Config", "ProjectionRegistry", "ProjectionRestoreResult", "setup"]

# 变更订阅者：(session, key, 完整值, 引发变更的事件 seq)。
ChangeListener = Callable[[Any, str, Any, int], None]


@dataclass(slots=True)
class _Registration:
    """一条活注册：单元 + 引用计数（N 个注册方共享一个单元）。"""

    unit: ProjectionUnit
    refs: int = 1


@dataclass(slots=True)
class _Cell:
    """per-session per-unit 状态与水位（最后折入事件的 seq；空日志 -1）。"""

    state: Any
    observed_seq: int


@dataclass(frozen=True, slots=True)
class ProjectionRestoreResult:
    """一次冷恢复的结果：日志末端完整值快照 + 刷新后的检查点行。"""

    snapshot: ProjectionSnapshot
    checkpoint: dict[str, ProjectionCheckpoint]


class _ProjectionObserver:
    """注册表的 Session observer 适配器：只有 ``__call__``，无 ``flush`` 面。"""

    def __init__(self, registry: ProjectionRegistry) -> None:
        self._registry = registry

    def __call__(self, session: Any, event: SessionEvent) -> None:
        self._registry.on_session_event(session, event)


class ProjectionRegistry:
    """投影单元表与驱动；``snapshot`` 出口是完整值，``state_of`` 读宿主态。"""

    def __init__(self) -> None:
        self._units: dict[str, _Registration] = {}
        self._listeners: list[ChangeListener] = []
        self._cells: WeakKeyDictionary[Any, dict[str, _Cell]] = WeakKeyDictionary()

    def register(self, unit: ProjectionUnit) -> Callable[[], None]:
        """注册一个领域单元；返回幂等取消函数。同 key 共享一个单元
        （``state_version`` 必须一致，否则抛 ``ValueError``），引用计数，
        最后一个取消才移除 key 并清掉全部缓存 cell。
        """
        key = unit.key
        version = unit.state_version
        if not isinstance(key, str) or not key:
            msg = f"projection unit key must be a non-empty string, got {key!r}"
            raise ValueError(msg)
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            msg = f"projection unit {key!r} state_version must be a non-negative integer, got {version!r}"
            raise ValueError(msg)
        existing = self._units.get(key)
        if existing is None:
            self._units[key] = _Registration(unit=unit)
        else:
            if existing.unit.state_version != version:
                msg = f"projection key {key!r} already registered at state_version {existing.unit.state_version}"
                raise ValueError(msg)
            existing.refs += 1
        disposed = False

        def dispose() -> None:
            nonlocal disposed
            if disposed:
                return
            disposed = True
            live = self._units.get(key)
            if live is None:
                return
            live.refs -= 1
            if live.refs <= 0:
                del self._units[key]
                for cells in self._cells.values():
                    cells.pop(key, None)

        return dispose

    def on_changed(self, listener: ChangeListener) -> Callable[[], None]:
        """订阅变更源；返回幂等取消函数。``apply`` 返回 ``!=`` 状态时以
        ``(session, key, 完整值, seq)`` 通知；host-only 单元（无 ``view``）
        不通知，重复订阅只记一次。
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

        def dispose() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return dispose

    def register_to(self, session: Any) -> Callable[[], None]:
        """挂驱动 observer；重复挂入安全（水位闸门跳过已折入事件）。"""
        return session.observe(_ProjectionObserver(self))

    def on_session_event(self, session: Any, event: SessionEvent) -> None:
        """observer 入口：一条已提交事件急切穿过全部单元。单个单元失败
        contained，不波及其他单元、不反噬 append；遍历走注册表快照，
        监听器内部注册/注销不影响本次派发。
        """
        for key, registration in tuple(self._units.items()):
            try:
                self._drive_unit(session, registration.unit, event)
            except Exception:
                _log.warning("session.projection.unit_failed", key=key, exc_info=True)

    def state_of(self, session: Any, key: str) -> Any | None:
        """读单元当前宿主态（先按 Session 水位物化）；未注册返回 ``None``。"""
        registration = self._units.get(key)
        if registration is None:
            return None
        return self._cell_for(session, key, registration.unit).state

    def snapshot(self, session: Any, keys: Sequence[str] | None = None) -> ProjectionSnapshot:
        """一次一致读切：物化全部单元后取完整客户端值。全同步：所有值与
        ``as_of_seq`` 反映同一日志位置（空日志 ``-1``）；host-only 单元与
        ``keys`` 未选中的 key 不进 ``values``；``view`` 抛错 contained。
        """
        selected = None if keys is None else set(keys)
        values: dict[str, Any] = {}
        for key, registration in self._units.items():
            unit = registration.unit
            cell = self._cell_for(session, key, unit)
            view = getattr(unit, "view", None)
            if not callable(view) or (selected is not None and key not in selected):
                continue
            try:
                values[key] = view(cell.state)
            except Exception:
                _log.warning("session.projection.view_failed", key=key, exc_info=True)
        return ProjectionSnapshot(as_of_seq=session.seq - 1, values=values)

    def checkpoint(self, session: Any) -> dict[str, ProjectionCheckpoint]:
        """全部已注册单元的状态级检查点（持久化投影缓存的写侧）。每行
        ``state`` 是脱钩深拷贝，绝活引用 cell（防污染权威水位缓存）。
        """
        rows: dict[str, ProjectionCheckpoint] = {}
        for key, registration in self._units.items():
            unit = registration.unit
            cell = self._cell_for(session, key, unit)
            rows[key] = ProjectionCheckpoint(
                version=unit.state_version, seq=cell.observed_seq, state=copy.deepcopy(cell.state)
            )
        return rows

    def state_version_of(self, key: str) -> int | None:
        """当前注册单元的 ``state_version``；未注册返回 ``None``。"""
        registration = self._units.get(key)
        return registration.unit.state_version if registration is not None else None

    def restore(
        self,
        checkpoint: Mapping[str, ProjectionCheckpoint] | None,
        events: Sequence[SessionEvent],
        header: SessionHeader,
    ) -> ProjectionRestoreResult:
        """冷恢复：在完整日志上折全部单元，可用检查点行做种子。行可用 ⟺
        行形合法 ∧ ``version`` 与活单元一致 ∧ ``-1 <= seq <= 日志末端``；
        不可用行整行丢弃、该 key 从 ``init`` 重折 —— 缓存永不是真值。
        ``events`` 必须从 seq 0 起连续（LCA 冷读恒全量，恢复失败即全量
        重折，无 DSH baseSeq 部分尾语义）；单元错误向上传播。
        """
        event_list = tuple(events)
        for index, event in enumerate(event_list):
            if event.seq != index:
                msg = f"restore events not contiguous from seq 0 at index {index} (seq {event.seq})"
                raise ValueError(msg)
        end_seq = event_list[-1].seq if event_list else -1
        rows = checkpoint or {}
        values: dict[str, Any] = {}
        refreshed: dict[str, ProjectionCheckpoint] = {}
        for key, registration in self._units.items():
            unit = registration.unit
            row = rows.get(key)
            usable = (
                isinstance(row, ProjectionCheckpoint)
                and row.version == unit.state_version
                and -1 <= row.seq <= end_seq
            )
            if usable and row is not None:
                state, start = row.state, row.seq + 1
            else:
                state, start = unit.init(header), 0
            for event in event_list[start:]:
                state = unit.apply(state, event)
            view = getattr(unit, "view", None)
            if callable(view):
                values[key] = view(state)
            refreshed[key] = ProjectionCheckpoint(
                version=unit.state_version, seq=end_seq, state=state
            )
        return ProjectionRestoreResult(
            snapshot=ProjectionSnapshot(as_of_seq=end_seq, values=values), checkpoint=refreshed
        )

    def _drive_unit(self, session: Any, unit: ProjectionUnit, event: SessionEvent) -> None:
        key = unit.key
        cells = self._session_cells(session)
        cell = cells.get(key)
        if cell is not None and cell.observed_seq >= event.seq:
            return  # 幂等闸门：已折入（重复 observer / 重放）
        if cell is None:
            # 迟到注册：先折本事件之前的历史 [0, event.seq)，再走正常路径。
            cells[key] = cell = self._build_cell(unit, session, until_seq=event.seq)
        else:
            self._advance_cell(unit, cell, session, through=event.seq - 1)
        previous = cell.state
        next_state = self._safe_apply(unit, previous, event)
        cell.state = next_state
        cell.observed_seq = event.seq
        if next_state != previous:
            self._notify_change(session, unit, next_state, event.seq)

    def _notify_change(self, session: Any, unit: ProjectionUnit, state: Any, seq: int) -> None:
        view = getattr(unit, "view", None)
        if not callable(view) or not self._listeners:
            return
        try:
            value = view(state)
        except Exception:
            _log.warning("session.projection.view_failed", key=unit.key, exc_info=True)
            return
        for listener in tuple(self._listeners):
            try:
                listener(session, unit.key, value, seq)
            except Exception:
                _log.warning("session.projection.listener_failed", key=unit.key, exc_info=True)

    def _cell_for(self, session: Any, key: str, unit: ProjectionUnit) -> _Cell:
        cells = self._session_cells(session)
        cell = cells.get(key)
        if cell is None:
            cell = self._build_cell(unit, session)
            cells[key] = cell
        else:
            self._advance_cell(unit, cell, session, through=session.seq - 1)
        return cell

    def _build_cell(
        self, unit: ProjectionUnit, session: Any, until_seq: int | None = None
    ) -> _Cell:
        state = self._safe_init(unit, session)
        events = session.snapshot_events(0, until_seq)
        observed = -1
        for event in events:
            state = self._safe_apply(unit, state, event)
            observed = event.seq
        return _Cell(state=state, observed_seq=observed)

    def _advance_cell(self, unit: ProjectionUnit, cell: _Cell, session: Any, through: int) -> None:
        while cell.observed_seq < through:
            seq = cell.observed_seq + 1
            event = session.event_at(seq)
            if event is None or event.seq != seq:
                msg = f"projection {unit.key!r} cannot advance across missing seq {seq}"
                raise ValueError(msg)
            cell.state = self._safe_apply(unit, cell.state, event)
            cell.observed_seq = seq

    def _safe_apply(self, unit: ProjectionUnit, state: Any, event: SessionEvent) -> Any:
        """contained ``apply``：单元抛错返回原状态，水位照常推进。"""
        try:
            return unit.apply(state, event)
        except Exception:
            _log.warning("session.projection.apply_failed", key=unit.key, exc_info=True)
            return state

    def _safe_init(self, unit: ProjectionUnit, session: Any) -> Any:
        try:
            return unit.init(session.header)
        except Exception:
            _log.warning("session.projection.init_failed", key=unit.key, exc_info=True)
            return None

    def _session_cells(self, session: Any) -> dict[str, _Cell]:
        return self._cells.setdefault(session, {})


class Config(BaseModel):
    """投影注册表无配置项；拒绝未知键防声明漂移。"""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.projection_registry",
    provides=["session.projections"],
    requires=["session.store"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Session 投影注册表（模块②，DSH session-projection 对照形态）：单元注册"
        "（引用计数）+ Session.observe 急切驱动 + 完整值 snapshot / checkpoint / 冷 restore。"
    ),
    test_suite="tests/plugins/session/test_projection_registry.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.store",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """投影注册表 boot：构造注册表并提供 ``session.projections``；挂 store
    活 Session + 经 ``add_observer_hook`` 接管未来 Session；无 store 时
    no-op（不抛）。
    """
    del config
    registry = ProjectionRegistry()
    ctx.provide("session.projections", registry)
    store = ctx.soft_get("session.store")
    if store is None:
        _log.info("session.projections.no_store", id="lca.plugins.session.projection_registry")
        return
    _attach_to_store(store, registry)


def _try_attach(registry: ProjectionRegistry, session: Any) -> None:
    try:
        registry.register_to(session)
    except Exception:
        _log.warning(
            "session.projections.attach_failed",
            session_id=getattr(session, "id", None),
            exc_info=True,
        )


def _attach_to_store(store: Any, registry: ProjectionRegistry) -> None:
    """对 store 活 Session 挂驱动 observer，并接管未来新 Session（对齐
    ``persistence_jsonl._attach_to_store``）；缺钩子抛 ``TypeError``。
    """
    for session in getattr(store, "list", lambda: ())():
        _try_attach(registry, session)
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)
    hook(lambda session: _try_attach(registry, session))
