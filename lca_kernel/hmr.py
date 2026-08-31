"""K8:HMR —— ``cordis.patch.yml`` 监听 + reload 信号(ADR-0118)。

Public surface
--------------
- :data:`DEFAULT_PATCH_PATH` —— 默认监听 ``Path("cordis.patch.yml")``。
- :data:`MIN_DEBOUNCE_MS` —— 防抖下限 50ms。
- :data:`PATCH_EVENT_KIND` —— 事件 kind 上层订阅标识 ``"kernel.hmr.patch"``。
- :class:`PatchConfig` —— 不可变 dataclass,描述 watcher 行为。
- :class:`PatchEvent` —— 不可变 dataclass,描述一次 patch 变更。
- :class:`PatchWatcher` —— Protocol,L0 seam。
- :class:`PollingPatchWatcher` —— 默认实现:daemon thread + poll mtime + debounce。
- :func:`validate_patch` —— shape gate;不递归校验子结构(resolve 阶段职责)。
- :func:`summarize_patch` —— 给人看的 patch 摘要(``lca-ops`` 用)。

Why polling over inotify
------------------------
跨平台(macOS / Linux / WSL)行为一致,不引入 watchdog / pyinotify 这类
native 扩展;poll interval 1s 对 hot-reload 场景足够(K8s readiness 也是
秒级)。``watchfiles`` 是更现代替代,留待后续 ADR。
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from lca_kernel.errors import ReloadError

DEFAULT_PATCH_PATH: Path = Path("cordis.patch.yml")
MIN_DEBOUNCE_MS: int = 50
PATCH_EVENT_KIND: str = "kernel.hmr.patch"

# 顶层只允许这些 keys;resolve 阶段的子结构校验是另一个职责。
_ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"version", "bundles", "profiles", "patches", "settings"}
)


@dataclass(frozen=True, slots=True)
class PatchConfig:
    """K8 watcher 行为配置。

    Attributes
    ----------
    path:
        监听的文件路径;默认 ``cordis.patch.yml``(由 :data:`DEFAULT_PATCH_PATH` 给出)。
    debounce_ms:
        防抖窗口(ms);最后一次文件变更 + 静默期后才触发 callback。低于
        :data:`MIN_DEBOUNCE_MS` 时自动抬升到下限。
    poll_interval_ms:
        fs poll 间隔(ms);主循环 sleep 时长。
    allow_missing:
        缺失文件是否视为 no-op(默认 False,文件不存在 raise :exc:`ReloadError`)。
    allow_empty:
        空文件是否允许(默认 False)。
    """

    path: Path = DEFAULT_PATCH_PATH
    debounce_ms: int = 250
    poll_interval_ms: int = 1000
    allow_missing: bool = False
    allow_empty: bool = False

    def __post_init__(self) -> None:
        # coerce + bounds;``frozen=True`` 禁止外部 mutate,只能走 __post_init__
        if self.debounce_ms < MIN_DEBOUNCE_MS:
            object.__setattr__(self, "debounce_ms", MIN_DEBOUNCE_MS)
        if self.poll_interval_ms < MIN_DEBOUNCE_MS:
            object.__setattr__(self, "poll_interval_ms", MIN_DEBOUNCE_MS)


@dataclass(frozen=True, slots=True)
class PatchEvent:
    """一次 patch 变更事件,callback 收到的唯一负载。

    ``raw`` 是已解析的 patch 字典(frozen MappingProxyType);``patch_kind``
    推断自顶层 ``settings.kind`` 或 fallback ``"user"``。
    """

    ts: float
    path: Path
    raw: Mapping[str, Any] = field(default_factory=dict)
    patch_kind: str = "user"

    def __post_init__(self) -> None:
        if not isinstance(self.raw, MappingProxyType):
            object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))


@runtime_checkable
class PatchWatcher(Protocol):
    """K8 L0 seam:watcher 必须暴露 start/stop/reload_now。

    实现可以是 polling(K8 默认)、inotify(后续 ADR)、WebSocket 推送
    (交给 transport layer),但契约不变。
    """

    @property
    def config(self) -> PatchConfig: ...

    def start(self) -> None:
        """启动后台轮询线程;幂等(二次调用 no-op)。"""

    def stop(self) -> None:
        """停止轮询线程;幂等。"""

    def reload_now(self) -> PatchEvent:
        """同步触发一次 reload;不依赖后台线程。返回 :class:`PatchEvent`。

        Raises
        ------
        ReloadError
            文件缺失 / 解析失败 / 空文件 / IO 错误时。
        """


def validate_patch(patch: Any, *, path: Path | None = None) -> None:
    """Shape gate:HMR 路径的快速合法性校验。

    只检查顶层结构;嵌套内容(bundles / profiles / patches)由 resolve
    阶段负责。空 mapping 视作 ``shape`` 错误(除非 ``allow_empty=True``)。

    Parameters
    ----------
    patch:
        任意对象;期望是 mapping。
    path:
        用于错误信息的 path(可选)。

    Raises
    ------
    ReloadError(reason="shape")
        非 mapping / 缺失 ``version`` / 含未授权顶层 key。
    ReloadError(reason="empty")
        空 mapping。
    """
    label = path or DEFAULT_PATCH_PATH
    if not isinstance(patch, Mapping):
        raise ReloadError(label, "shape", f"patch must be a mapping, got {type(patch).__name__}")
    if len(patch) == 0:
        raise ReloadError(label, "empty", "patch mapping is empty")
    if "version" not in patch:
        raise ReloadError(label, "shape", "patch missing required top-level 'version'")
    version = patch["version"]
    # YAML may parse ``version: 1`` as int; accept str OR int/float.
    if isinstance(version, bool) or not isinstance(version, (str, int, float)):
        raise ReloadError(
            label,
            "shape",
            f"patch 'version' must be str/int/float, got {type(version).__name__}",
        )
    if isinstance(version, str) and not version:
        raise ReloadError(label, "shape", "patch 'version' must be non-empty when str")
    unknown = set(patch.keys()) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        raise ReloadError(
            label,
            "shape",
            f"patch has unknown top-level keys: {sorted(unknown)}",
        )


def summarize_patch(patch: Mapping[str, Any]) -> str:
    """给人看的 patch 摘要,``lca-ops`` + 日志用。

    列出 version + 顶层 keys 的数量 + settings.kind(若有)。
    """
    lines = [f"version={patch.get('version', '<missing>')}"]
    for key in ("bundles", "profiles", "patches", "settings"):
        if key in patch:
            value = patch[key]
            count = len(value) if hasattr(value, "__len__") else "?"
            lines.append(f"{key}={count}")
    settings = patch.get("settings")
    if isinstance(settings, Mapping):
        kind = settings.get("kind")
        if isinstance(kind, str):
            lines.append(f"settings.kind={kind}")
    return " ".join(lines)


class PollingPatchWatcher:
    """K8 默认 watcher:daemon thread + poll mtime + debounce。

    Notes
    -----
    进程内 hot-swap 不在本期范围(违反 ADR-0062 运行期不改 State);
    watcher 仅观察文件变更并回调,reload 决策交给上层 supervisor
    (uvicorn --reload / k8s readiness / lca-ops restart)。
    """

    def __init__(
        self,
        config: PatchConfig,
        on_change: Callable[[PatchEvent], None],
    ) -> None:
        self._config = config
        self._on_change = on_change
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_mtime: float | None = None
        self._last_change_ts: float | None = None

    @property
    def config(self) -> PatchConfig:
        return self._config

    def start(self) -> None:
        """启动后台轮询线程;幂等。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_mtime = _safe_mtime(self._config.path)
            self._thread = threading.Thread(
                target=self._loop,
                name=f"lca-kernel-hmr:{self._config.path.name}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """停止后台轮询线程;幂等。"""
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._config.poll_interval_ms / 1000 * 2 + 0.5)
        self._last_change_ts = None

    def reload_now(self) -> PatchEvent:
        """同步触发一次 reload;不依赖后台线程。"""
        return _read_and_dispatch(
            self._config,
            on_change=self._on_change,
            source="manual",
        )

    def _loop(self) -> None:
        """主循环:defer to ``_wait_for_change`` until stop is requested."""
        while not self._stop_event.is_set():
            try:
                changed = self._wait_for_change()
            except Exception:
                # poll loop must not crash;suppress and continue.
                changed = False
            if changed:
                with contextlib.suppress(Exception):
                    self.reload_now()

    def _wait_for_change(self) -> bool:
        """Poll mtime + debounce;return True when a stable change is detected."""
        poll_seconds = self._config.poll_interval_ms / 1000
        last_mtime = self._last_mtime
        while not self._stop_event.is_set():
            current = _safe_mtime(self._config.path)
            if current != last_mtime:
                # Debounce:wait for ``debounce_ms`` of stillness.
                self._stop_event.wait(self._config.debounce_ms / 1000)
                still = _safe_mtime(self._config.path)
                if still == current:
                    self._last_mtime = current
                    self._last_change_ts = time.time()
                    return True
                # mtime changed again inside debounce;restart window.
                last_mtime = still
                continue
            self._stop_event.wait(poll_seconds)
        return False


def _safe_mtime(path: Path) -> float | None:
    """Return mtime as float, or None if the file does not exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _read_and_dispatch(
    config: PatchConfig,
    *,
    on_change: Callable[[PatchEvent], None],
    source: str,
) -> PatchEvent:
    """Read + parse + validate + dispatch; raise ``ReloadError`` on failure."""
    path = config.path
    try:
        text = path.read_text()
    except FileNotFoundError as exc:
        if config.allow_missing:
            return _noop_event(path)
        raise ReloadError(path, "missing", f"{exc}") from exc
    except OSError as exc:
        raise ReloadError(path, "io", f"{exc}") from exc
    if not text.strip():
        if config.allow_empty:
            return _noop_event(path)
        raise ReloadError(path, "empty", "patch file is empty")
    raw = _parse_yaml_safe(text)
    validate_patch(raw, path=path)
    settings = raw.get("settings") if isinstance(raw, Mapping) else None
    kind = "user"
    if isinstance(settings, Mapping):
        candidate = settings.get("kind")
        if isinstance(candidate, str) and candidate:
            kind = candidate
    event = PatchEvent(
        ts=time.time(),
        path=path,
        raw=dict(raw),
        patch_kind=kind,
    )
    on_change(event)
    return event


def _parse_yaml_safe(text: str) -> Mapping[str, Any]:
    """Parse YAML using a minimal safe loader; avoids importing ``pyyaml``.

    This is a fallback when ``yaml`` is not available. The LCA env
    whitelist (ADR-0117 K7) makes PyYAML available, so we prefer that.
    """
    import yaml  # local import: keep top-level free of pyyaml hard dep

    return yaml.safe_load(text) or {}


def _noop_event(path: Path) -> PatchEvent:
    return PatchEvent(ts=time.time(), path=path, raw={}, patch_kind="noop")


__all__ = [
    "DEFAULT_PATCH_PATH",
    "MIN_DEBOUNCE_MS",
    "PATCH_EVENT_KIND",
    "PatchConfig",
    "PatchEvent",
    "PatchWatcher",
    "PollingPatchWatcher",
    "summarize_patch",
    "validate_patch",
]
