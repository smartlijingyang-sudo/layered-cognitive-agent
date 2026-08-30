"""Profile YAML 输入的装配与规范化。

此 module 是 Profile 输入的文件读取 adapter，负责 YAML 文件、Bundle 与来源信息。
内存声明的 Patch 合并和环境引用展开由 ``declarations`` module 负责；本 module
不导入插件，也不校验 capability 或层级，这些语义规则留在 ``resolve`` 的领域解析阶段。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from lca.harness.profile.declarations import (
    apply_patches,
    deep_copy_value,
    expand_entry_environment,
)
from lca.harness.profile.errors import ProfileResolveError
from lca.harness.profile.runtime_closure import FallbackPolicy


@dataclass(frozen=True, slots=True)
class ProfileSource:
    """已经完成输入适配、但尚未导入插件的 Profile 事实。

    ``entries`` 保留稳定的 bundle 声明顺序；``sources`` 与每个 entry 的
    ``_config_sources`` 则保留 patch 产生的 provenance。下游解析器只需将这些
    事实转换为 ``ResolvedPlugin``，无需再次理解 YAML 的便利语法。
    """

    profile_path: Path
    bundles: tuple[str, ...]
    entries: tuple[dict[str, Any], ...]
    sources: Mapping[str, str]
    fallback_policy: Mapping[str, str]


def programmatic_profile_source(entries: Sequence[Mapping[str, Any]]) -> ProfileSource:
    """将兼容 ``boot_entries`` 输入适配为与 YAML 相同的 Profile 事实。

    程序化入口只负责复制调用方提供的声明、记录稳定来源，并把历史上的
    ``config.disabled`` 便利写法规范为顶层 ``disabled``。它不导入插件，也不
    判断 capability；这些语义统一由 Resolve 接缝处理，避免测试入口另行演化
    Manifest、配置和 DAG 规则。
    """

    normalized: list[dict[str, Any]] = []
    sources: dict[str, str] = {}
    for index, raw_entry in enumerate(entries):
        entry = dict(raw_entry)
        config = entry.get("config")
        if isinstance(config, Mapping) and config.get("disabled"):
            entry["disabled"] = True
        entry_id = str(entry.get("id") or "")
        if entry_id:
            sources[entry_id] = f"<programmatic entries>[{index}]"
        normalized.append(entry)
    return ProfileSource(
        profile_path=Path("<programmatic entries>"),
        bundles=(),
        entries=tuple(normalized),
        sources=MappingProxyType(sources),
        fallback_policy=MappingProxyType({}),
    )


def load_profile_source(
    profile_path: Path | str,
    *,
    env: Mapping[str, str] | None = None,
) -> ProfileSource:
    """读取并规范化一个 Profile 的外部输入。

    读取顺序固定为：Profile 文件 → Bundle 展开 → Profile Patch 合并 → 配置中的
    环境引用展开 → 顶层 fallback policy 规范化。该函数不触发插件导入，因此是
    可独立测试、无业务对象的输入适配 seam。
    """
    path = Path(profile_path)
    raw = _load_profile_mapping(path)
    bundles_raw = _bundle_entries(raw)
    entries, sources = _expand_bundles(path, bundles_raw)
    entries = apply_patches(
        entries,
        sources,
        raw.get("patch") or [],
        profile_path=str(path),
    )
    env_map = dict(os.environ if env is None else env)
    expand_entry_environment(entries, env_map)
    return ProfileSource(
        profile_path=_profile_identity(path),
        bundles=tuple(str(bundle) for bundle in bundles_raw),
        entries=tuple(entries),
        sources=MappingProxyType(dict(sources)),
        fallback_policy=_normalize_fallback_policy(
            raw.get("fallback_policy"), profile_path=str(path)
        ),
    )


def _profile_identity(path: Path) -> Path:
    """Return a portable Profile identity without changing physical file lookup.

    A Profile located beneath the active checkout has the same declaration
    meaning whether callers supplied a relative or absolute filesystem path.
    Normalize only that ambient checkout prefix after all file and Bundle reads
    are complete. Profiles outside the checkout retain their absolute identity,
    so distinct deployment-owned configuration files cannot collide.
    """

    if not path.is_absolute():
        return path
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def load_profile_entries(
    profile_path: Path | str,
    *,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Expose mutable programmatic input without crossing the Resolve seam.

    The compatibility caller receives the same bundle-expanded, patch-applied
    declarations that a file Profile contributes to Resolve.  This adapter does
    not import plugin modules, validate Manifest identity, or serialize a
    ``ResolvedProfile`` back into a reduced entry shape; ``resolve_entries``
    remains the sole module that gives such input Profile semantics.  Each
    returned declaration is an isolated copy and excludes source-internal
    provenance fields, so test fixtures can edit their input without mutating
    another load or depending on input-adapter implementation details.
    """

    source = load_profile_source(profile_path, env=env)
    return [
        {key: deep_copy_value(value) for key, value in entry.items() if not key.startswith("_")}
        for entry in source.entries
    ]


def _load_profile_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ProfileResolveError(f"profile {path} must be a mapping")
    return raw


def _bundle_entries(raw: Mapping[str, Any]) -> list[Any]:
    bundles = raw.get("bundles") or []
    if not isinstance(bundles, list):
        raise ProfileResolveError("bundles must be a list")
    return bundles


def _resolve_bundle_path(bundle_path: Path, profile_path: Path) -> Path:
    """解析 bundle 路径：绝对 / 相对 profile 父目录 / 相对 cwd。

    支持两种语法糖：裸名自动补 ``.yaml``，以及无目录裸名自动尝试
    ``bundles/<name>.yaml``。
    """
    candidates: list[Path] = []
    if not bundle_path.is_absolute():
        candidates.append(profile_path.parent / bundle_path)
        candidates.append(Path.cwd() / bundle_path)
    else:
        candidates.append(bundle_path)
    if bundle_path.suffix == "":
        for original in list(candidates):
            candidates.append(original.with_suffix(".yaml"))
    if "/" not in str(bundle_path):
        candidates.append(Path.cwd() / "bundles" / f"{bundle_path.name}.yaml")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _expand_bundles(
    profile_path: Path, bundles: list[Any]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    all_entries: list[dict[str, Any]] = []
    sources: dict[str, str] = {}
    for bundle_path in bundles:
        bundle_full = _resolve_bundle_path(Path(bundle_path), profile_path)
        if not bundle_full.exists():
            raise ProfileResolveError(f"bundle not found: {bundle_path}")
        bundle_data = yaml.safe_load(bundle_full.read_text()) or {}
        for entry in bundle_data.get("entries") or []:
            if not isinstance(entry, dict) or "id" not in entry:
                raise ProfileResolveError(f"invalid entry in {bundle_full}")
            cleaned = {key: value for key, value in entry.items() if key != "inject"}
            cleaned = dict(cleaned)
            cleaned.setdefault("config", {})
            if not isinstance(cleaned["config"], dict):
                raise ProfileResolveError(
                    f"{cleaned['id']}: config must be a mapping ({bundle_full})"
                )
            cleaned["config"] = deep_copy_value(cleaned["config"])
            plugin_id = str(cleaned["id"])
            if plugin_id in sources:
                raise ProfileResolveError(
                    f"duplicate plugin id {plugin_id!r} across bundles "
                    f"({sources[plugin_id]} and {bundle_full})"
                )
            sources[plugin_id] = str(bundle_full)
            all_entries.append(cleaned)
    return all_entries, sources


def _normalize_fallback_policy(raw: Any, *, profile_path: str) -> Mapping[str, str]:
    """规范化 profile.fallback_policy 为只读 ``Mapping[str, str]``。"""
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise ProfileResolveError(
            f"{profile_path}: fallback_policy must be a mapping, got {type(raw).__name__}"
        )
    normalized_policy: dict[str, str] = {}
    for capability, policy in raw.items():
        if not isinstance(capability, str) or not capability:
            raise ProfileResolveError(
                f"{profile_path}: fallback_policy key must be non-empty str, got {capability!r}"
            )
        if type(policy) is bool and policy is False:
            normalized = FallbackPolicy.OFF.value
        elif isinstance(policy, str):
            normalized = policy
        else:
            raise ProfileResolveError(
                f"{profile_path}: fallback_policy[{capability!r}] must be str or bool, "
                f"got {type(policy).__name__}"
            )
        try:
            FallbackPolicy(normalized)
        except ValueError as error:
            valid_policies = sorted(value.value for value in FallbackPolicy)
            raise ProfileResolveError(
                f"{profile_path}: fallback_policy[{capability!r}] must be one of "
                f"{valid_policies}, got {policy!r}"
            ) from error
        normalized_policy[capability] = normalized
    return MappingProxyType(normalized_policy)


__all__ = ["ProfileSource", "load_profile_entries", "load_profile_source"]
