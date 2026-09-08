"""Adapter: agent_lab toolbox graph ↔ LCA ToolRegistry.

agent_lab provides (this file):
  - LcaToolboxRegistryProvider: loads a YAML registry and emits a
    registry_payload FACT artifact listing name → ref/kwargs/capability/scope.
  - LcaToolboxResolveProvider: resolves a tool name to a Tool instance from
    a ToolRegistry (fixture or built from registry_payload).

Fixture registry helpers:
  - register_fixture_tool_registry(name, registry)
  - unregister_fixture_tool_registry(name)

Node.config stays JSON-serializable: fixture_tool_registry_name is a string
key into the process-local fixture map. No live ToolRegistry in config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Shared: process-local fixture ToolRegistry map
# ---------------------------------------------------------------------------
_FIXTURE_TOOL_REGISTRIES: dict[str, Any] = {}


def register_fixture_tool_registry(name: str, registry: Any) -> None:
    """Register a ToolRegistry instance under a fixture name for tests."""
    _FIXTURE_TOOL_REGISTRIES[name] = registry


def unregister_fixture_tool_registry(name: str) -> None:
    """Remove a fixture ToolRegistry by name."""
    _FIXTURE_TOOL_REGISTRIES.pop(name, None)


# ---------------------------------------------------------------------------
# Registry provider — loads YAML, emits registry_payload
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaToolboxRegistryProvider:
    """Load tool entries from a YAML registry file.

    Config keys:
      - registry_path: path to YAML file (default: agent_lab/tools/registry.yaml)

    Emits a registry_payload FACT artifact with tool metadata.
    """

    _registry_path: str

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaToolboxRegistryProvider:
        registry_path = config.get("registry_path", "agent_lab/tools/registry.yaml")
        return cls(_registry_path=registry_path)

    def load(self, config: dict[str, Any]) -> Artifact:
        """Load the YAML registry and emit a registry_payload artifact."""
        registry_path = config.get("registry_path", self._registry_path)
        entries = _load_registry_yaml(registry_path)
        return Artifact(
            kind=ArtifactKind.FACT,
            content={"entries": entries, "source": registry_path},
            schema_ref="toolbox.registry_payload.v1",
        )


# ---------------------------------------------------------------------------
# Resolve provider — tool name → Tool instance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaToolboxResolveProvider:
    """Resolve a tool name to a Tool instance from a ToolRegistry.

    Resolution order:
      1. provider_config.fixture_tool_registry_name (process-local fixture map)
      2. Build a ToolRegistry from registry_payload artifact
      3. Fall back to the default singleton ToolRegistry

    Config keys:
      - provider_config.fixture_tool_registry_name: string key
    """

    _fixture_name: str | None

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaToolboxResolveProvider:
        provider_config = config.get("provider_config") or {}
        fixture_name = provider_config.get("fixture_tool_registry_name")
        return cls(_fixture_name=fixture_name)

    def resolve(
        self,
        *,
        tool_name_artifact: Artifact | None = None,
        registry_artifact: Artifact | None = None,
    ) -> Artifact:
        """Resolve a tool name and emit a tool_instance artifact."""
        tool_name = _extract_tool_name(tool_name_artifact)
        registry = self._resolve_registry(registry_artifact)
        tool = registry.get(tool_name)
        return Artifact(
            kind=ArtifactKind.FACT,
            content=_tool_to_dict(tool),
            schema_ref="toolbox.tool_instance.v1",
        )

    def _resolve_registry(self, registry_artifact: Artifact | None) -> Any:
        """Resolve the ToolRegistry to use."""
        # 1. Fixture registry (test path)
        if self._fixture_name and self._fixture_name in _FIXTURE_TOOL_REGISTRIES:
            return _FIXTURE_TOOL_REGISTRIES[self._fixture_name]
        # 2. Build from registry_payload artifact
        if registry_artifact is not None and registry_artifact.content:
            entries = (
                registry_artifact.content.get("entries")
                if isinstance(registry_artifact.content, dict)
                else None
            )
            if entries:
                return _build_registry_from_entries(entries)
        # 3. Default singleton
        return _default_registry()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_registry_yaml(path_str: str) -> list[dict[str, Any]]:
    """Load tool entries from a YAML file. Returns list of entry dicts."""
    import yaml

    path = Path(path_str)
    if not path.is_absolute():
        # Resolve relative to repo root
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / path
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "tools" not in raw:
        return []
    entries: list[dict[str, Any]] = []
    for entry in raw["tools"]:
        if not isinstance(entry, dict):
            continue
        entries.append(
            {
                "ref": entry.get("ref", ""),
                "kwargs": dict(entry.get("kwargs") or {}),
            }
        )
    return entries


def _build_registry_from_entries(entries: list[dict[str, Any]]) -> Any:
    """Build a ToolRegistry from registry_payload entries (best-effort)."""
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for entry in entries:
        ref = entry.get("ref", "")
        if not ref:
            continue
        try:
            tool = ToolRegistry._resolve_factory(entry)
            registry.register(tool)
        except Exception:
            # Skip entries that can't be resolved (e.g. missing deps)
            logging.getLogger(__name__).debug(
                "Skipping unresolvable tool entry: %s",
                entry,
            )
            continue
    return registry


def _default_registry() -> Any:
    """Return the default ToolRegistry loaded from the standard path."""
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    repo_root = Path(__file__).resolve().parents[2]
    default_path = repo_root / "agent_lab" / "tools" / "registry.yaml"
    if default_path.exists():
        registry.load_from_yaml(default_path)
    return registry


def _extract_tool_name(artifact: Artifact | None) -> str:
    """Extract the tool name string from an artifact."""
    if artifact is None:
        return ""
    content = artifact.content
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("name") or content.get("tool_name") or "")
    return str(content)


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    """Convert a Tool instance to a serializable dict."""
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", ""),
        "parameters": dict(getattr(tool, "parameters", {}) or {}),
        "is_idempotent": bool(getattr(tool, "is_idempotent", False)),
        "effect_kind": getattr(tool, "effect_kind", "ephemeral"),
        "default_timeout_s": int(getattr(tool, "default_timeout_s", 60)),
    }


def schemas_from_inventory(
    *,
    registry_payload: Artifact | None = None,
    registry_path: str | None = None,
) -> list[dict[str, Any]]:
    """Build openai-style tool schemas from inventory.

    Resolution order:
      1. ``registry_payload`` artifact (entries from load_registry)
      2. ``registry_path`` YAML (default: agent_lab/tools/registry.yaml)

    Fail-loud when an entry cannot be resolved to a Tool — inventory that
    cannot be shown to the model must not silently shrink.
    """
    from lca.infrastructure.llm_adapter.openai_compat.chat import to_openai_chat_tool_spec

    registry = _registry_for_schemas(registry_payload, registry_path)
    return [to_openai_chat_tool_spec(registry.get(name)) for name in registry.names()]


def _registry_for_schemas(
    registry_payload: Artifact | None,
    registry_path: str | None,
) -> Any:
    if registry_payload is not None and registry_payload.content:
        content = registry_payload.content
        entries = content.get("entries") if isinstance(content, dict) else None
        if isinstance(entries, list) and entries:
            return _build_registry_from_entries_strict(entries)
    path = registry_path or "agent_lab/tools/registry.yaml"
    registry = _default_registry_from_path(path)
    if not registry.names():
        raise ValueError(f"expose_schemas: tool inventory empty at {path!r}")
    return registry


def _build_registry_from_entries_strict(entries: list[dict[str, Any]]) -> Any:
    """Like ``_build_registry_from_entries`` but fail-loud on any bad entry."""
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for entry in entries:
        ref = entry.get("ref", "")
        if not ref:
            raise ValueError(f"expose_schemas: registry entry missing ref: {entry!r}")
        tool = ToolRegistry._resolve_factory(entry)
        registry.register(tool)
    return registry


def _default_registry_from_path(path_str: str) -> Any:
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        raise ValueError(f"expose_schemas: registry YAML not found: {path}")
    registry.load_from_yaml(path)
    return registry


__all__ = [
    "LcaToolboxRegistryProvider",
    "LcaToolboxResolveProvider",
    "register_fixture_tool_registry",
    "schemas_from_inventory",
    "unregister_fixture_tool_registry",
]
