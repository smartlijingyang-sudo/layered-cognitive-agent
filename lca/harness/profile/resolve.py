"""将已规范化的 Profile 输入解析为不可变运行时声明。

``resolve_profile`` 只承担插件 Manifest 导入、配置模型校验、依赖图验证与不可变
``ResolvedProfile`` 构造。YAML、Bundle、Patch、环境引用和 fallback policy 的输入适配
统一由 ``profile.source`` 处理，避免语义解析器泄漏外部文件格式细节。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import warnings
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from pydantic import BaseModel, SecretStr

from lca.harness.plugin_api import PluginDefinition, PluginSetupFn, definition_from_plugin
from lca.harness.plugin_spec_projection import native_spec_from_declaration
from lca.harness.profile.errors import ProfileResolveError
from lca.harness.profile.source import (
    ProfileSource,
    load_profile_source,
    programmatic_profile_source,
)

_LAYER_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
_REDACTED = "***"


@dataclass(frozen=True, slots=True)
class ResolvedPlugin:
    id: str
    module: str
    definition: PluginDefinition
    config: Any
    config_sources: dict[str, str]
    disabled: bool
    source: str
    index: int


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    profile_path: str
    bundles: tuple[str, ...]
    plugins: tuple[ResolvedPlugin, ...]
    dag_edges: tuple[tuple[str, str], ...]
    manifest_hash: str
    env_refs: tuple[tuple[str, str, bool], ...]
    fallback_policy: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


def resolve_profile(
    profile_path: Path | str,
    *,
    env: Mapping[str, str] | None = None,
) -> ResolvedProfile:
    """解析文件 Profile 为不变量已验证、拓扑稳定的不可变声明。"""

    return _resolve_source(load_profile_source(profile_path, env=env))


def resolve_entries(entries: Sequence[Mapping[str, Any]]) -> ResolvedProfile:
    """解析程序化 entries，复用生产 Profile 的唯一领域语义。

    此兼容入口仅接受已由 ``programmatic_profile_source`` 适配的内存声明；Manifest
    身份、配置模型、单一 provider、层级和 DAG 的判断全部委托给同一 Resolve
    模块。调用方因此不需要理解另一套测试专用错误、排序或配置规则。
    """

    return _resolve_source(programmatic_profile_source(entries))


def _resolve_source(source: ProfileSource) -> ResolvedProfile:
    """将一种输入事实解析为唯一的不可变 Profile 声明。"""

    resolved_plugins, env_refs = _resolve_plugins(source)
    enabled = [plugin for plugin in resolved_plugins if not plugin.disabled]
    _validate_capability_owners(enabled)
    _validate_layer_edges(enabled)
    order, edges = _topo_sort(enabled)
    disabled_plugins = sorted(
        (plugin for plugin in resolved_plugins if plugin.disabled), key=lambda plugin: plugin.index
    )
    ordered = tuple(order) + tuple(disabled_plugins)
    digest = hashlib.sha256(
        json.dumps(_canonical_payload(ordered), sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return ResolvedProfile(
        profile_path=str(source.profile_path),
        bundles=source.bundles,
        plugins=ordered,
        dag_edges=tuple(edges),
        manifest_hash=digest,
        env_refs=tuple(env_refs),
        fallback_policy=source.fallback_policy,
    )


def _resolve_plugins(
    source: ProfileSource,
) -> tuple[list[ResolvedPlugin], list[tuple[str, str, bool]]]:
    """把输入 adapter 产出的 entries 转换为已校验的插件声明。

    输入 adapter 已完成文件读取、Patch 和环境引用；此函数只处理 Manifest、Pydantic
    配置与插件来源。删除它会把插件导入和配置语义重新散落到 YAML 处理路径，因此它
    构成 Profile 领域的深模块。
    """
    resolved_plugins: list[ResolvedPlugin] = []
    seen_ids: set[str] = set()
    env_refs: list[tuple[str, str, bool]] = []

    for index, entry in enumerate(source.entries):
        plugin_id = str(entry.get("id") or "")
        if not plugin_id:
            raise ProfileResolveError(f"entry at index {index} missing id")
        if plugin_id in seen_ids:
            raise ProfileResolveError(f"duplicate plugin id: {plugin_id!r}")
        seen_ids.add(plugin_id)

        module_path = entry.get("$module")
        if not module_path:
            raise ProfileResolveError(
                f"bundle entry {plugin_id!r} has no $module; bare-name resolution was removed"
            )
        module_name = str(module_path)
        plugin_source = source.sources.get(plugin_id, str(source.profile_path))
        if bool(entry.get("disabled")):
            resolved_plugins.append(
                ResolvedPlugin(
                    id=plugin_id,
                    module=module_name,
                    definition=_disabled_stub(plugin_id, module_name),
                    config={},
                    config_sources={},
                    disabled=True,
                    source=plugin_source,
                    index=index,
                )
            )
            continue

        module = importlib.import_module(module_name)
        setup_obj = getattr(module, "setup", None)
        if setup_obj is None:
            raise ProfileResolveError(f"module {module_path} has no setup")
        definition = definition_from_plugin(setup_obj, module=module_name)
        if definition.spec.id != plugin_id:
            raise ProfileResolveError(
                f"profile id {plugin_id!r} != native PluginSpec id {definition.spec.id!r} "
                f"({module_path})"
            )

        expanded = entry.get("config") or {}
        if not isinstance(expanded, dict):
            raise ProfileResolveError(f"{plugin_id}: config must be a mapping")
        env_refs.extend(entry.get("_env_refs", ()))
        config_sources = {key: f"{plugin_source}#config.{key}" for key in expanded}
        patch_sources = entry.get("_config_sources", {})
        if isinstance(patch_sources, Mapping):
            for key in expanded:
                patch_source = patch_sources.get(key)
                if patch_source:
                    config_sources[key] = str(patch_source)

        config_obj: Any = expanded
        config_cls = (
            definition.Config
            or getattr(setup_obj, "Config", None)
            or getattr(module, "Config", None)
        )
        if config_cls is not None and definition.Config is None:
            definition = definition.with_config(config_cls)
        if config_cls is not None:
            try:
                config_obj = config_cls.model_validate(expanded)
            except Exception as exc:
                raise ProfileResolveError(f"{plugin_id}: config validation failed: {exc}") from exc

        resolved_plugins.append(
            ResolvedPlugin(
                id=plugin_id,
                module=module_name,
                definition=definition,
                config=config_obj,
                config_sources=config_sources,
                disabled=False,
                source=plugin_source,
                index=index,
            )
        )
    return resolved_plugins, env_refs


def dump_resolved(
    resolved: ResolvedProfile,
    *,
    redact: bool = True,
) -> dict[str, Any]:
    """返回 ``ResolvedProfile`` 的脱敏、规范化诊断视图。"""
    plugins = []
    for item in resolved.plugins:
        config = _config_as_dict(item.config)
        if redact:
            config = _redact_secrets(config)
        plugins.append(
            {
                "id": item.id,
                "module": item.module,
                "disabled": item.disabled,
                "kind": item.definition.spec.kind.value,
                "layer": item.definition.spec.layer,
                "provides": list(item.definition.provided_capability_keys),
                "requires": list(item.definition.required_capability_keys),
                "config": config,
                "config_sources": dict(item.config_sources),
                "source": item.source,
                "test_suite": item.definition.spec.verification.test_suite,
            }
        )
    return {
        "profile": resolved.profile_path,
        "bundles": list(resolved.bundles),
        "manifest_hash": resolved.manifest_hash,
        "dag_edges": [list(edge) for edge in resolved.dag_edges],
        "plugins": plugins,
    }


def _disabled_stub(plugin_id: str, module: str) -> PluginDefinition:
    from lca.harness.plugin_api import EffectClass, PluginKind

    return PluginDefinition[Any](
        Config=None,
        setup=cast("PluginSetupFn[Any]", lambda *_args, **_kwargs: None),
        spec=native_spec_from_declaration(
            plugin_id=plugin_id,
            config_cls=None,
            provides=(),
            requires=(),
            implements=(),
            layer="L0",
            kind=PluginKind.PRIMITIVE,
            effects=frozenset({EffectClass.NONE}),
            test_suite="",
            functional_group=None,
            module=module,
        ),
        description="disabled",
    )


def _requirement_matches(requirement: str, provided_keys: set[str]) -> bool:
    """Return True if ``requirement`` is satisfied by some key in ``provided_keys``.

    The only supported wildcard is a single trailing ``*`` (e.g.
    ``field_producer.*``), matching any key that shares the same prefix
    before the dot. This covers the EventSpine composition where an L1
    assembler needs every L0 ``field_producer.<name>`` producer without
    forcing the profile to enumerate each one.
    """
    if requirement in provided_keys:
        return True
    if requirement.endswith(".*"):
        prefix = requirement[:-2] + "."
        return any(key.startswith(prefix) for key in provided_keys)
    return False


def _validate_capability_owners(plugins: list[ResolvedPlugin]) -> None:
    owners: dict[str, list[str]] = defaultdict(list)
    provided: set[str] = set()
    for plugin in plugins:
        for key in plugin.definition.provided_capability_keys:
            owners[key].append(plugin.id)
            provided.add(key)

    for key, ids in owners.items():
        if len(ids) > 1:
            raise ProfileResolveError(f"duplicate providers for capability {key!r}: {ids}")

    for plugin in plugins:
        missing = [
            key
            for key in plugin.definition.required_capability_keys
            if not _requirement_matches(key, provided)
        ]
        if missing:
            raise ProfileResolveError(
                f"Missing capability: {missing[0]}\n"
                f"required by: {plugin.id}\n"
                f"configured at: {plugin.source}\n"
                f"resolution: enable a plugin that provides {missing[0]!r} "
                "or remove the dependent target"
            )


def _validate_layer_edges(plugins: list[ResolvedPlugin]) -> None:
    by_provide: dict[str, ResolvedPlugin] = {}
    for plugin in plugins:
        for key in plugin.definition.provided_capability_keys:
            by_provide[key] = plugin
    for consumer in plugins:
        consumer_rank = _LAYER_RANK.get(consumer.definition.spec.layer, 0)
        for key in consumer.definition.required_capability_keys:
            if key.endswith(".*"):
                # Wildcard requirements span many providers; per-provider
                # layer ranks are not meaningful here.
                continue
            provider = by_provide.get(key)
            if provider is None:
                continue
            provider_rank = _LAYER_RANK.get(provider.definition.spec.layer, 0)
            if consumer_rank < provider_rank:
                raise ProfileResolveError(
                    f"layer violation: {consumer.id} ({consumer.definition.spec.layer}) "
                    f"requires {key} from {provider.id} ({provider.definition.spec.layer})"
                )


def _topo_sort(
    plugins: list[ResolvedPlugin],
) -> tuple[list[ResolvedPlugin], list[tuple[str, str]]]:
    by_id = {plugin.id: plugin for plugin in plugins}
    provide_owner = {
        key: plugin.id for plugin in plugins for key in plugin.definition.provided_capability_keys
    }
    dependents: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    edges: list[tuple[str, str]] = []
    for consumer in plugins:
        for key in consumer.definition.required_capability_keys:
            if key.endswith(".*"):
                # Wildcard requirements span many providers; the DAG sort
                # cannot pin a single ordering edge for them.
                continue
            owner = provide_owner.get(key)
            if owner is None or owner == consumer.id:
                continue
            dependents[owner].add(consumer.id)
            reverse[consumer.id].add(owner)
            edges.append((owner, consumer.id))

    indegree = {plugin.id: len(reverse[plugin.id]) for plugin in plugins}
    ready = deque(
        sorted(
            (plugin.id for plugin in plugins if indegree[plugin.id] == 0),
            key=lambda item: by_id[item].index,
        )
    )
    ordered: list[ResolvedPlugin] = []
    while ready:
        plugin_id = ready.popleft()
        ordered.append(by_id[plugin_id])
        for child in sorted(dependents[plugin_id], key=lambda item: by_id[item].index):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        if len(ready) > 1:
            ready = deque(sorted(ready, key=lambda item: by_id[item].index))

    if len(ordered) != len(plugins):
        leftover = [plugin.id for plugin in plugins if plugin not in ordered]
        raise ProfileResolveError(f"cyclic plugin dependency involving: {leftover}")
    seen: set[tuple[str, str]] = set()
    unique_edges: list[tuple[str, str]] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            unique_edges.append(edge)
    return ordered, unique_edges


def _config_as_dict(config: Any) -> dict[str, Any]:
    if isinstance(config, BaseModel):
        dumped = config.model_dump(mode="python")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(config, dict):
        return dict(config)
    return {}


def _redact_secrets(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, SecretStr):
            out[key] = _REDACTED
        elif isinstance(value, dict):
            out[key] = _redact_secrets(value)
        elif isinstance(value, str) and any(
            token in key.lower() for token in ("key", "secret", "token", "password")
        ):
            out[key] = _REDACTED if value else value
        else:
            out[key] = value
    return out


def _canonical_payload(
    plugins: tuple[ResolvedPlugin, ...] | list[ResolvedPlugin],
) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "module": item.module,
            "disabled": item.disabled,
            "provides": list(item.definition.provided_capability_keys),
            "requires": list(item.definition.required_capability_keys),
            "layer": item.definition.spec.layer,
            "kind": item.definition.spec.kind.value,
        }
        for item in plugins
    ]


# === Deprecation (ADR-0115) ===
warnings.warn(
    "lca.harness.profile.resolve is deprecated, use lca_kernel.resolve (ADR-0115)",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ProfileResolveError",
    "ResolvedPlugin",
    "ResolvedProfile",
    "dump_resolved",
    "resolve_entries",
    "resolve_profile",
]
