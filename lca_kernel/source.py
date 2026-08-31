"""Profile YAML / Bundle / Patch 输入适配(K1a)。

ADR-0115 决定 1 K1a:本模块在 PR-2 阶段是 :mod:`lca.harness.profile.source` 的
薄 re-export(为 6 个月 compat 窗口保留);新增 deepseek 借鉴的
:func:`compose_entries` 多层 patch 合并函数。完整迁移到独立 kernel 实现
留给后续阶段(避免与 compat 形成 cycle)。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# 重导出旧路径实现 —— source 是纯 IO adapter,无业务逻辑,直接 import 比复制代码更稳。
from lca.harness.profile.source import (
    ProfileSource,
    load_profile_entries,
    load_profile_source,
    programmatic_profile_source,
)


def compose_entries(
    bundle_patches: Sequence[Mapping[str, Any]] | None = None,
    profile_patches: Sequence[Mapping[str, Any]] | None = None,
    home_patches: Sequence[Mapping[str, Any]] | None = None,
    overlays: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """组合多层 patch 为单一 entry list(借鉴 deepseek ``composeEntries``)。

    借鉴 deepseek ``app-boot/src/index.ts:composeEntries()``:把多个来源
    的 patch 列表按"先底层后覆盖"顺序合并为一份平坦的 entry list。
    LCA 没有 deepseek 的 group / include 概念,所以 entry 即 plugin
    declaration;later wins,dict-key 维度 deep merge。

    Parameters
    ----------
    bundle_patches:
        Bundle YAML 中的 plugin entries(profile expansion 的最低层)。
    profile_patches:
        Profile YAML 顶层的 ``patch:`` 段;会覆盖 bundle 同 id 配置。
    home_patches:
        用户 ``~/.lca/patches/*.yaml`` 等 home 级别 patch。
    overlays:
        ``--patch`` CLI 提供的最后一层 patch;优先级最高。

    Returns
    -------
    list[dict[str, Any]]
        按 ``bundle → profile → home → overlays`` 顺序合并后的 entry list;
        ``id`` 字段相同的后层覆盖前层(dict deep merge)。
    """
    layers: list[Sequence[Mapping[str, Any]]] = [
        bundle_patches or (),
        profile_patches or (),
        home_patches or (),
        overlays or (),
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for entry in layer:
            plugin_id = str(entry.get("id") or "")
            if not plugin_id:
                continue
            existing = by_id.get(plugin_id)
            if existing is None:
                by_id[plugin_id] = {k: v for k, v in entry.items() if k != "inject"}
            else:
                _deep_merge_entry(existing, entry)
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for layer in layers:
        for entry in layer:
            plugin_id = str(entry.get("id") or "")
            if not plugin_id or plugin_id in seen:
                continue
            if plugin_id in by_id:
                ordered.append(by_id[plugin_id])
                seen.add(plugin_id)
    for entry in overlays or ():
        plugin_id = str(entry.get("id") or "")
        if plugin_id and plugin_id not in seen and plugin_id in by_id:
            ordered.append(by_id[plugin_id])
            seen.add(plugin_id)
    return ordered


def _deep_merge_entry(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    """Mutate ``base`` with a deep merge of ``overlay`` (dict keys recurse)."""
    for key, value in overlay.items():
        if key == "id":
            continue
        if key == "inject":
            base["inject"] = value
            continue
        if isinstance(value, Mapping) and isinstance(base.get(key), Mapping):
            _deep_merge_entry(base[key], value)
        else:
            base[key] = value


__all__ = [
    "ProfileSource",
    "compose_entries",
    "load_profile_entries",
    "load_profile_source",
    "programmatic_profile_source",
]


def _iter_entries(entries: Iterable[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    """Public helper used by test fixtures to flatten compose_entries output."""
    return entries
