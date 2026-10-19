"""cordis_control Tool 的 plugin 源加载 + 动态 import 助手。

职责
----
- :func:`load_plugin_source`：从磁盘读 plugin 源文本 + 元信息（语言 / size）。
- :func:`extract_plugin_factory`：从 plugin 源文本解析 ``plugin_meta`` 与
  ``factory()`` / ``<name>_factory()`` 函数；按 PR12 强制要求，缺
  ``plugin_meta`` 时抛 :class:`PluginMetaMissing`。
- :func:`ensure_plugin_on_disk`：把源文本写到 preset 目录（mount / publish
  都需要），为后续 ``importlib.util.spec_from_file_location`` 提供磁盘路径。

模块加载与入口发现走共享 seam（``lca.infrastructure.preset.plugin_loading``，
RA-162）：creator 管线与 preset 自主发现管线用同一模块名方案 + 内容摘要
感知的 ``sys.modules`` 复用——同一 ``.py`` 内容不变时一进程只 exec 一次，
磁盘内容变化（热升级）时重新 exec；入口发现的严格度由 ``require_meta``
显式选择（creator 线 PR12 严格，discovery 线 8-fallback 宽松）。

为什么独立成模块：cordis_control Tool 主类体超过 250 行有效代码上限，
helpers 独立后既满足宪法 §8.2 行数守卫，又能让 Tool 类聚焦「4-action 分发」。
"""

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from lca.application.authoring.preset_authoring import PresetAuthoring
from lca.contracts.harness.composition.plugin_meta import PluginMeta
from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT
from lca.infrastructure.preset.plugin_loading import extract_entry, load_plugin_module


def resolve_plugin_path(path: str, *, assistant_home: Path | None = None) -> Path:
    """解析 plugin 源码路径。若为相对路径且绑定 assistant_home，优先在其工作区下解析。"""
    p = Path(path)
    if not p.is_file():
        if assistant_home is not None:
            # 沙箱挂载映射：沙箱内的 /mnt/data/... 物理对应 host 上的 assistant_home / workspace
            if str(p).startswith(SANDBOX_MOUNT_ROOT + "/"):
                rel_mnt = str(p)[len(SANDBOX_MOUNT_ROOT) + 1 :]
                cand_mnt = assistant_home / "workspace" / rel_mnt
                if cand_mnt.is_file():
                    return cand_mnt
                cand_direct = assistant_home / rel_mnt
                if cand_direct.is_file():
                    return cand_direct
            if not p.is_absolute():
                candidate = assistant_home / path
                if candidate.is_file():
                    return candidate
                candidate_ws = assistant_home / "workspace" / path
                if candidate_ws.is_file():
                    return candidate_ws
        if not p.is_file():
            raise FileNotFoundError(f"plugin 源码不存在：{path}")
    return p


def load_plugin_source(path: str, *, assistant_home: Path | None = None) -> tuple[str, str, int]:
    """读 plugin 源；返回 ``(text, language, size_bytes)``。"""
    p = resolve_plugin_path(path, assistant_home=assistant_home)
    text = p.read_text(encoding="utf-8")
    language = "python" if p.suffix == ".py" else "text"
    return text, language, len(text.encode("utf-8"))


def ensure_plugin_on_disk(
    *,
    plugin_name: str,
    source_text: str,
    preset_root: Path | None = None,
) -> Path:
    """把 plugin 源码写到 ``<root>/<name>/plugins/<name>.py`` 并返回路径。"""
    root = preset_root or PresetAuthoring.presets_home()
    target = root / plugin_name / "plugins" / f"{plugin_name}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source_text, encoding="utf-8")
    return target


def extract_plugin_factory(
    *,
    source_path: str,
    source_text: str,
    plugin_name: str,
    preset_root: Path | None = None,
) -> tuple[Any, PluginMeta]:
    """动态加载 plugin 模块，提取 ``factory()`` 与 ``plugin_meta``。

    PR12 强制：plugin 源模块必须显式声明 ``plugin_meta`` 字典；缺则抛
    :class:`PluginMetaMissing`（不允许自动补全，避免隐性默认）。

    模块加载与入口发现收敛到共享 seam
    （``lca.infrastructure.preset.plugin_loading``）：``require_meta=True``
    保持 creator 线的 PR12 严格度；同一 ``.py`` 若经 discovery 管线加载过，
    复用 ``sys.modules`` 里的同一个 module 对象。

    Returns:
        ``(factory_callable, plugin_meta_dict)``
    """
    target = ensure_plugin_on_disk(
        plugin_name=plugin_name,
        source_text=source_text,
        preset_root=preset_root,
    )
    preset_root_str = str(target.parent.parent.parent)
    path_added = preset_root_str not in sys.path
    if path_added:
        sys.path.insert(0, preset_root_str)
    try:
        module = load_plugin_module(target, plugin_name)
        factory_callable, plugin_meta_raw = extract_entry(
            module, plugin_name, require_meta=True
        )
        plugin_meta: dict[str, Any] = dict(plugin_meta_raw)
        plugin_meta.setdefault("name", plugin_name)
        plugin_meta.setdefault("layer", "behavior")
        plugin_meta.setdefault("implements", ["Plugin"])
        plugin_meta["source_path"] = source_path
        return factory_callable, cast("PluginMeta", plugin_meta)
    finally:
        if path_added:
            with suppress(ValueError):
                sys.path.remove(preset_root_str)


__all__ = [
    "ensure_plugin_on_disk",
    "extract_plugin_factory",
    "load_plugin_source",
    "resolve_plugin_path",
]
