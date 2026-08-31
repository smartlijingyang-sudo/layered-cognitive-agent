"""Profile 声明的纯处理逻辑。

该 module 只负责已经读入内存的 Profile 声明：合并 Patch、复制嵌套值、
展开环境引用并保留 provenance。它不读取文件、不解析 YAML，也不承担
插件导入或 capability 解析，从而让输入读取与声明语义拥有清晰的 seam。
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from lca.harness.profile.errors import ProfileResolveError


def apply_patches(
    entries: list[dict[str, Any]],
    sources: dict[str, str],
    patches: Any,
    *,
    profile_path: str,
) -> list[dict[str, Any]]:
    """Apply non-structural profile patches to bundle-expanded declarations."""
    if not isinstance(patches, list):
        raise ProfileResolveError("patch must be a list")
    by_id = {str(entry["id"]): entry for entry in entries}
    for patch in patches:
        if not isinstance(patch, dict) or "id" not in patch:
            raise ProfileResolveError("each patch entry requires id")
        plugin_id = str(patch["id"])
        target = by_id.get(plugin_id)
        if target is None:
            raise ProfileResolveError(f"patch id {plugin_id!r} does not match any bundled plugin")
        for forbidden in ("provides", "requires", "layer", "kind", "$module", "name"):
            if forbidden in patch and forbidden != "id":
                raise ProfileResolveError(
                    f"patch must not override structural field {forbidden!r} on {plugin_id}"
                )
        if "$module" in patch:
            raise ProfileResolveError(f"patch must not replace $module on {plugin_id}")
        if "disabled" in patch:
            target["disabled"] = bool(patch["disabled"])
        patch_config = patch.get("config")
        if patch_config is not None:
            if not isinstance(patch_config, dict):
                raise ProfileResolveError(f"patch config for {plugin_id} must be a mapping")
            target["config"] = deep_merge(target.get("config") or {}, patch_config)
            provenance = target.setdefault("_config_sources", {})
            for key in flatten_keys(patch_config):
                provenance[key.split(".", 1)[0]] = f"{profile_path}#patch.{plugin_id}.{key}"
        sources[plugin_id] = f"{sources.get(plugin_id, '')}+patch"
    return entries


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge declaration config while isolating mutable input values."""
    out = {key: deep_copy_value(value) for key, value in base.items()}
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deep_copy_value(value)
    return out


def deep_copy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: deep_copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_copy_value(item) for item in value]
    return value


def flatten_keys(mapping: dict[str, Any], prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in mapping.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict) and "from_env" not in value and "literal" not in value:
            keys.extend(flatten_keys(value, path))
        else:
            keys.append(path)
    return keys


def expand_entry_environment(entries: list[dict[str, Any]], env: Mapping[str, str]) -> None:
    """Resolve enabled declaration environment references in place."""
    for entry in entries:
        if bool(entry.get("disabled")):
            continue
        plugin_id = str(entry.get("id") or "")
        raw_config = entry.get("config") or {}
        if not isinstance(raw_config, dict):
            raise ProfileResolveError(f"{plugin_id}: config must be a mapping")
        expanded, refs = expand_env_refs(raw_config, env, plugin_id=plugin_id)
        entry["config"] = expanded
        entry["_env_refs"] = refs


def expand_env_refs(
    config: dict[str, Any],
    env: Mapping[str, str],
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
                if any(
                    token in field_path.lower() for token in ("key", "secret", "token", "password")
                ):
                    return SecretStr(raw)
                return raw
            if set(node.keys()) <= {"literal"} and "literal" in node:
                return node["literal"]
            return {
                key: walk(value, f"{field_path}.{key}" if field_path else key)
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [walk(value, field_path) for value in node]
        return node

    return walk(config, ""), refs


# === Deprecation (ADR-0115) ===
warnings.warn(
    "lca.harness.profile.declarations is deprecated, use lca_kernel.declarations (ADR-0115)",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "apply_patches",
    "deep_copy_value",
    "deep_merge",
    "expand_entry_environment",
    "expand_env_refs",
    "flatten_keys",
]
