"""插件 .py 源的统一加载 seam：同一路径一进程只 exec 一次 + 统一入口发现。

收敛点（RA-162）：creator 管线（``lca/plugins/tools/cordis_control/loader.py``
的 ``extract_plugin_factory``）与 preset 自主发现管线
（``AssistantPresetDiscovery._load_plugin_tool``）原来用两套模块名
（``lca_agent_presets._runtime.{name}`` vs
``lca_presets._autonomous.{dir}.{name}``）对同一 ``.py`` 做 importlib exec——
同一进程里模块级状态（单例/缓存）分叉成两份；且两处"找入口函数"启发式
不一致（PR12 强制 ``plugin_meta`` vs 8 选 1 宽松）。

本模块是单一真值：
- :func:`plugin_module_name`：由文件路径派生的统一模块名。
- :func:`load_plugin_module`：统一命名 + 内容摘要感知的 ``sys.modules``
  复用——同一路径、内容不变时一进程内只 exec 一次（两条管线得到同一个
  module 对象）；磁盘内容变化（热升级）时重新 exec，保证永远加载磁盘
  最新版本。
- :func:`extract_entry`：共享的入口发现。``require_meta=True`` 保持 creator
  线 PR12 严格度（缺 ``plugin_meta`` → ``PluginMetaMissing``）；
  ``require_meta=False`` 保持 discovery 线 8-fallback 宽松度。

两条管线的严格度差异是既有契约（PR12 / ADR-0256 注册语义），收进显式
参数，不抹平。
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

from lca.contracts.mechanisms.composition.composition import PluginMetaMissing

_PLUGIN_EXEC_PREFIX = "lca_presets._exec"


def plugin_module_name(plugin_name: str, plugin_path: str | Path) -> str:
    """由插件名 + 绝对路径摘要派生统一模块名。

    同一路径 → 同一名（``sys.modules`` 复用）；不同路径 → 不同名
    （路径摘要防碰撞）。插件名中的非标识符字符转义为下划线。
    """
    resolved = str(Path(plugin_path).resolve())
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    safe_name = re.sub(r"\W", "_", plugin_name)
    return f"{_PLUGIN_EXEC_PREFIX}.{safe_name}.{digest}"


# module_name -> (module, exec 时的文件内容摘要)
_EXEC_CACHE: dict[str, tuple[ModuleType, str]] = {}


def _content_digest(plugin_path: str | Path) -> str | None:
    """文件内容 sha256；读不到时返回 None（交给 exec 自然抛错）。"""
    try:
        return hashlib.sha256(Path(plugin_path).read_bytes()).hexdigest()
    except OSError:
        return None


def _drop_stale_bytecode(plugin_path: str | Path) -> None:
    """删掉可能过时的 pyc。

    同一秒内、同尺寸改写会让 pyc 校验（整数秒 mtime + size）误判缓存有效，
    导致 exec 到旧字节码——热升级静默失效。用内容摘要判定需要重 exec 后，
    先删 pyc 再走正常 spec 流程，保证编译的是磁盘最新源码。
    """
    try:
        pyc = Path(importlib.util.cache_from_source(str(plugin_path)))
    except Exception:
        return
    with suppress(OSError):
        pyc.unlink()


def load_plugin_module(plugin_path: str | Path, plugin_name: str) -> ModuleType:
    """加载插件 ``.py`` 为模块。

    同一路径、内容不变时一进程内只 exec 一次：creator 管线与 discovery 管线
    加载同一文件得到的是同一个 module 对象，模块级状态不再分叉。磁盘内容
    变化时（热升级）重新 exec，保证加载到的永远是磁盘上的最新版本。
    """
    module_name = plugin_module_name(plugin_name, plugin_path)
    digest = _content_digest(plugin_path)
    cached = _EXEC_CACHE.get(module_name)
    if cached is not None and digest is not None and cached[1] == digest:
        return cached[0]
    _drop_stale_bytecode(plugin_path)
    spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {plugin_path} 构建 importlib spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if digest is not None:
        _EXEC_CACHE[module_name] = (module, digest)
    return module


def extract_entry(
    module: ModuleType, plugin_name: str, *, require_meta: bool
) -> tuple[Any, dict[str, Any]]:
    """共享的插件入口发现。

    严格度由 ``require_meta`` 显式选择——两条管线的既有契约，不抹平：
    - ``True``（creator 线）：entry 只能是 ``factory()`` /
      ``<name>_factory()``（返回时不调用，由调用方决定何时调用）；
      缺 ``plugin_meta`` → :class:`PluginMetaMissing`（PR12 强制）。
    - ``False``（discovery 线）：8-fallback 宽松启发式——factory 找到即
      调用，返回其结果；否则按 ``<name>`` / ``run`` / ``analyze`` /
      ``execute`` / ``handler`` / ``main`` 顺序找；``plugin_meta`` 可选。
    """
    factory_fn = getattr(module, "factory", None) or getattr(
        module, f"{plugin_name}_factory", None
    )
    if require_meta:
        if factory_fn is None or not callable(factory_fn):
            raise PluginMetaMissing(
                f"plugin 模块 {getattr(module, '__file__', module)} "
                f"未定义 factory() 或 {plugin_name}_factory()",
                plugin_name=plugin_name,
            )
        plugin_meta_raw = getattr(module, "plugin_meta", None)
        if not plugin_meta_raw:
            raise PluginMetaMissing(
                f"plugin 模块 {getattr(module, '__file__', module)} "
                "缺少 plugin_meta TypedDict（PR12 强制）",
                plugin_name=plugin_name,
            )
        return factory_fn, dict(plugin_meta_raw)

    target_fn: Any = None
    if factory_fn is not None and callable(factory_fn):
        target_fn = factory_fn()
    else:
        target_fn = getattr(module, plugin_name, None) or getattr(module, "run", None)
        if target_fn is None:
            for candidate in ("analyze", "execute", "handler", "main"):
                fn = getattr(module, candidate, None)
                if callable(fn):
                    target_fn = fn
                    break
    if target_fn is None:
        raise AttributeError(
            f"Plugin {plugin_name!r} does not expose a callable factory, "
            f"function {plugin_name!r}, or run()"
        )
    return target_fn, dict(getattr(module, "plugin_meta", None) or {})


__all__ = [
    "extract_entry",
    "load_plugin_module",
    "plugin_module_name",
]
