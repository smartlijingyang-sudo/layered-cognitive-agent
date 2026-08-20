"""Profile resolve phase — Manifest validation, deep merge, DAG (ADR-0061).

Pure: no business objects, no network, no silent fallback. Output is an
immutable :class:`ResolvedProfile` consumed by ``boot_resolved_profile``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, SecretStr

from lca.harness.plugin_api import PluginDefinition, definition_from_plugin

_LAYER_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
_REDACTED = "***"


class ProfileResolveError(ValueError):
    """Structural / config / dependency failure before any setup() runs."""


@dataclass(frozen=True, slots=True)
class FieldSource:
    path: str  # e.g. bundles/base.yaml or profiles/web-standard.yaml#patch
    value: Any


@dataclass(frozen=True, slots=True)
class ResolvedPlugin:
    id: str
    module: str
    definition: PluginDefinition
    config: Any  # validated Pydantic model or empty dict
    config_sources: dict[str, str]
    disabled: bool
    source: str  # bundle path that introduced the entry
    index: int  # stable profile order among peers


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    profile_path: str
    bundles: tuple[str, ...]
    plugins: tuple[ResolvedPlugin, ...]  # topological order
    dag_edges: tuple[tuple[str, str], ...]  # (provider_id, consumer_id)
    manifest_hash: str
    env_refs: tuple[tuple[str, str, bool], ...]  # (plugin_id, field, required)


def resolve_profile(
    profile_path: Path | str,
    *,
    env: MappingLike | None = None,
) -> ResolvedProfile:
    """Load profile → deep-merge → import Manifests → validate DAG → freeze."""
    path = Path(profile_path)
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ProfileResolveError(f"profile {path} must be a mapping")

    bundles_raw = raw.get("bundles") or []
    if not isinstance(bundles_raw, list):
        raise ProfileResolveError("bundles must be a list")

    entries, sources = _expand_bundles(path, bundles_raw)
    patches = raw.get("patch") or []
    if not isinstance(patches, list):
        raise ProfileResolveError("patch must be a list")
    entries = _apply_patches(entries, sources, patches, profile_path=str(path))

    env_map = dict(os.environ if env is None else env)
    resolved_plugins: list[ResolvedPlugin] = []
    seen_ids: set[str] = set()
    env_refs: list[tuple[str, str, bool]] = []

    for index, entry in enumerate(entries):
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

        disabled = bool(entry.get("disabled"))
        source = sources.get(plugin_id, str(path))
        if disabled:
            # Still import to keep dump/inspect accurate? Skip import for disabled
            # unless something requires it — resolve will fail consumers later.
            resolved_plugins.append(
                ResolvedPlugin(
                    id=plugin_id,
                    module=str(module_path),
                    definition=_disabled_stub(plugin_id, str(module_path)),
                    config={},
                    config_sources={},
                    disabled=True,
                    source=source,
                    index=index,
                )
            )
            continue

        module = importlib.import_module(str(module_path))
        setup_obj = getattr(module, "setup", None)
        if setup_obj is None:
            raise ProfileResolveError(f"module {module_path} has no setup")
        definition = definition_from_plugin(setup_obj, module=str(module_path))
        if definition.id != plugin_id:
            raise ProfileResolveError(
                f"profile id {plugin_id!r} != module Manifest id {definition.id!r} ({module_path})"
            )

        raw_config = entry.get("config") or {}
        if not isinstance(raw_config, dict):
            raise ProfileResolveError(f"{plugin_id}: config must be a mapping")
        expanded, refs = _expand_env_refs(raw_config, env_map, plugin_id=plugin_id)
        env_refs.extend(refs)
        config_sources = {key: f"{source}#config.{key}" for key in expanded}
        # Overlay patch provenance when present.
        for key in expanded:
            patch_src = entry.get("_config_sources", {}).get(key)
            if patch_src:
                config_sources[key] = patch_src

        config_obj: Any = expanded
        config_cls = (
            definition.Config
            or getattr(setup_obj, "Config", None)
            or getattr(module, "Config", None)
        )
        if config_cls is not None and definition.Config is None:
            definition = PluginDefinition(
                id=definition.id,
                Config=config_cls,
                provides=definition.provides,
                requires=definition.requires,
                implements=definition.implements,
                layer=definition.layer,
                kind=definition.kind,
                effects=definition.effects,
                test_suite=definition.test_suite,
                description=definition.description,
                setup=definition.setup,
                module=definition.module,
            )
        if config_cls is not None:
            try:
                config_obj = config_cls.model_validate(expanded)
            except Exception as exc:
                raise ProfileResolveError(f"{plugin_id}: config validation failed: {exc}") from exc

        resolved_plugins.append(
            ResolvedPlugin(
                id=plugin_id,
                module=str(module_path),
                definition=definition,
                config=config_obj,
                config_sources=config_sources,
                disabled=False,
                source=source,
                index=index,
            )
        )

    enabled = [p for p in resolved_plugins if not p.disabled]
    _validate_capability_owners(enabled)
    _validate_layer_edges(enabled)
    order, edges = _topo_sort(enabled)
    # Append disabled at end (stable by index) so dump still lists them.
    disabled_plugins = sorted((p for p in resolved_plugins if p.disabled), key=lambda p: p.index)
    ordered = tuple(order) + tuple(disabled_plugins)
    payload = _canonical_payload(ordered)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]

    return ResolvedProfile(
        profile_path=str(path),
        bundles=tuple(str(b) for b in bundles_raw),
        plugins=ordered,
        dag_edges=tuple(edges),
        manifest_hash=digest,
        env_refs=tuple(env_refs),
    )


# Typing alias without importing Mapping everywhere for env override.
MappingLike = Any


def dump_resolved(
    resolved: ResolvedProfile,
    *,
    redact: bool = True,
) -> dict[str, Any]:
    """Redacted canonical dump of a ResolvedProfile (no secret plaintext)."""
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
                "kind": item.definition.kind.value,
                "layer": item.definition.layer,
                "provides": list(item.definition.provides),
                "requires": list(item.definition.requires),
                "config": config,
                "config_sources": dict(item.config_sources),
                "source": item.source,
                "test_suite": item.definition.test_suite,
            }
        )
    return {
        "profile": resolved.profile_path,
        "bundles": list(resolved.bundles),
        "manifest_hash": resolved.manifest_hash,
        "dag_edges": [list(e) for e in resolved.dag_edges],
        "plugins": plugins,
    }


# ── Internals ───────────────────────────────────────────────────────


def _disabled_stub(plugin_id: str, module: str) -> PluginDefinition:
    from lca.harness.plugin_api import EffectClass, PluginKind

    return PluginDefinition(
        id=plugin_id,
        Config=None,
        provides=(),
        requires=(),
        implements=(),
        layer="L0",
        kind=PluginKind.PRIMITIVE,
        effects=frozenset({EffectClass.NONE}),
        test_suite="",
        description="disabled",
        setup=lambda *_a, **_k: None,
        module=module,
    )


def _expand_bundles(
    profile_path: Path, bundles: list[Any]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    all_entries: list[dict[str, Any]] = []
    sources: dict[str, str] = {}
    for bundle_path in bundles:
        bundle_full = Path(bundle_path)
        if not bundle_full.is_absolute():
            candidate = profile_path.parent / bundle_path
            bundle_full = candidate if candidate.exists() else Path.cwd() / bundle_path
        if not bundle_full.exists():
            raise ProfileResolveError(f"bundle not found: {bundle_path}")
        bundle_data = yaml.safe_load(bundle_full.read_text()) or {}
        for entry in bundle_data.get("entries") or []:
            if not isinstance(entry, dict) or "id" not in entry:
                raise ProfileResolveError(f"invalid entry in {bundle_full}")
            # Drop YAML inject — Manifest requires is the fact source (ADR-0061).
            cleaned = {k: v for k, v in entry.items() if k != "inject"}
            cleaned = dict(cleaned)
            cleaned.setdefault("config", {})
            if not isinstance(cleaned["config"], dict):
                raise ProfileResolveError(
                    f"{cleaned['id']}: config must be a mapping ({bundle_full})"
                )
            # Deep-copy so patch merge cannot mutate YAML-derived shared state.
            cleaned["config"] = _deep_copy_mapping(cleaned["config"])
            eid = str(cleaned["id"])
            if eid in sources:
                raise ProfileResolveError(
                    f"duplicate plugin id {eid!r} across bundles ({sources[eid]} and {bundle_full})"
                )
            sources[eid] = str(bundle_full)
            all_entries.append(cleaned)
    return all_entries, sources


def _apply_patches(
    entries: list[dict[str, Any]],
    sources: dict[str, str],
    patches: list[Any],
    *,
    profile_path: str,
) -> list[dict[str, Any]]:
    by_id = {str(e["id"]): e for e in entries}
    for patch in patches:
        if not isinstance(patch, dict) or "id" not in patch:
            raise ProfileResolveError("each patch entry requires id")
        pid = str(patch["id"])
        target = by_id.get(pid)
        if target is None:
            raise ProfileResolveError(f"patch id {pid!r} does not match any bundled plugin")
        # Structural metadata cannot be overridden by profile patch.
        for forbidden in ("provides", "requires", "layer", "kind", "$module", "name"):
            if forbidden in patch and forbidden != "id":
                raise ProfileResolveError(
                    f"patch must not override structural field {forbidden!r} on {pid}"
                )
        if "$module" in patch:
            raise ProfileResolveError(f"patch must not replace $module on {pid}")
        if "disabled" in patch:
            target["disabled"] = bool(patch["disabled"])
        patch_config = patch.get("config")
        if patch_config is not None:
            if not isinstance(patch_config, dict):
                raise ProfileResolveError(f"patch config for {pid} must be a mapping")
            target["config"] = _deep_merge(target.get("config") or {}, patch_config)
            provenance = target.setdefault("_config_sources", {})
            for key in _flatten_keys(patch_config):
                provenance[key.split(".", 1)[0]] = f"{profile_path}#patch.{pid}.{key}"
        sources[pid] = f"{sources.get(pid, '')}+patch"
    return entries


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: _deep_copy_mapping(v) for k, v in base.items()}
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = _deep_copy_mapping(value) if isinstance(value, dict) else value
    return out


def _deep_copy_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy_mapping(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_mapping(v) for v in value]
    return value


def _flatten_keys(mapping: dict[str, Any], prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in mapping.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict) and "from_env" not in value and "literal" not in value:
            keys.extend(_flatten_keys(value, path))
        else:
            keys.append(path)
    return keys


def _expand_env_refs(
    config: dict[str, Any],
    env: dict[str, str],
    *,
    plugin_id: str,
) -> tuple[dict[str, Any], list[tuple[str, str, bool]]]:
    refs: list[tuple[str, str, bool]] = []

    def walk(node: Any, field_path: str) -> Any:
        if isinstance(node, dict):
            if "from_env" in node:
                env_name = str(node["from_env"])
                required = bool(node.get("required", False))
                refs.append((plugin_id, field_path, required))
                raw = env.get(env_name)
                if raw is None or raw == "":
                    if required:
                        raise ProfileResolveError(
                            f"{plugin_id}.{field_path}: required env {env_name!r} missing"
                        )
                    return None
                # Secret-shaped: wrap as SecretStr when field looks sensitive.
                if any(s in field_path.lower() for s in ("key", "secret", "token", "password")):
                    return SecretStr(raw)
                return raw
            if set(node.keys()) <= {"literal"} and "literal" in node:
                return node["literal"]
            return {k: walk(v, f"{field_path}.{k}" if field_path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, field_path) for v in node]
        return node

    return walk(config, ""), refs


def _validate_capability_owners(plugins: list[ResolvedPlugin]) -> None:
    owners: dict[str, list[str]] = defaultdict(list)
    provided: set[str] = set()
    for plugin in plugins:
        for key in plugin.definition.provides:
            owners[key].append(plugin.id)
            provided.add(key)

    for key, ids in owners.items():
        # registry cardinality allows one seam owner; multiple providers register into it
        # and do not re-provide the same singleton key. Duplicate provide of same key = error
        # unless all but one are clearly factory/register-only — we treat any duplicate
        # provide as error (providers should require the seam, not provide it).
        if len(ids) > 1:
            raise ProfileResolveError(f"duplicate providers for capability {key!r}: {ids}")

    for plugin in plugins:
        missing = [k for k in plugin.definition.requires if k not in provided]
        if missing:
            raise ProfileResolveError(
                f"Missing capability: {missing[0]}\n"
                f"required by: {plugin.id}\n"
                f"configured at: {plugin.source}\n"
                f"resolution: enable a plugin that provides {missing[0]!r} "
                f"or remove the dependent target"
            )


def _validate_layer_edges(plugins: list[ResolvedPlugin]) -> None:
    by_provide: dict[str, ResolvedPlugin] = {}
    for plugin in plugins:
        for key in plugin.definition.provides:
            by_provide[key] = plugin
    for consumer in plugins:
        c_rank = _LAYER_RANK.get(consumer.definition.layer, 0)
        for key in consumer.definition.requires:
            provider = by_provide.get(key)
            if provider is None:
                continue
            p_rank = _LAYER_RANK.get(provider.definition.layer, 0)
            # Dependency direction: lower/equal layer may provide to higher;
            # a lower layer must not require a higher-layer capability.
            if c_rank < p_rank:
                raise ProfileResolveError(
                    f"layer violation: {consumer.id} ({consumer.definition.layer}) "
                    f"requires {key} from {provider.id} ({provider.definition.layer})"
                )


def _topo_sort(
    plugins: list[ResolvedPlugin],
) -> tuple[list[ResolvedPlugin], list[tuple[str, str]]]:
    by_id = {p.id: p for p in plugins}
    provide_owner = {key: p.id for p in plugins for key in p.definition.provides}
    # Edge: provider → consumer (provider must boot first).
    dependents: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    edges: list[tuple[str, str]] = []
    for consumer in plugins:
        for key in consumer.definition.requires:
            owner = provide_owner.get(key)
            if owner is None or owner == consumer.id:
                continue
            dependents[owner].add(consumer.id)
            reverse[consumer.id].add(owner)
            edges.append((owner, consumer.id))

    indegree = {p.id: len(reverse[p.id]) for p in plugins}
    # Kahn with stable tie-break by original index.
    ready = deque(
        sorted(
            (p.id for p in plugins if indegree[p.id] == 0),
            key=lambda i: by_id[i].index,
        )
    )
    ordered: list[ResolvedPlugin] = []
    while ready:
        nid = ready.popleft()
        ordered.append(by_id[nid])
        for child in sorted(dependents[nid], key=lambda i: by_id[i].index):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        # Keep ready queue ordered by index.
        if len(ready) > 1:
            ready = deque(sorted(ready, key=lambda i: by_id[i].index))

    if len(ordered) != len(plugins):
        leftover = [p.id for p in plugins if p not in ordered]
        raise ProfileResolveError(f"cyclic plugin dependency involving: {leftover}")
    # Deduplicate edges while preserving order.
    seen: set[tuple[str, str]] = set()
    uniq_edges: list[tuple[str, str]] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            uniq_edges.append(edge)
    return ordered, uniq_edges


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
            s in key.lower() for s in ("key", "secret", "token", "password")
        ):
            out[key] = _REDACTED if value else value
        else:
            out[key] = value
    return out


def _canonical_payload(
    plugins: tuple[ResolvedPlugin, ...] | list[ResolvedPlugin],
) -> list[dict[str, Any]]:
    rows = []
    for item in plugins:
        rows.append(
            {
                "id": item.id,
                "module": item.module,
                "disabled": item.disabled,
                "provides": list(item.definition.provides),
                "requires": list(item.definition.requires),
                "layer": item.definition.layer,
                "kind": item.definition.kind.value,
            }
        )
    return rows
