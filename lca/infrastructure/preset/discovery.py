"""Assistant autonomous preset and plugin discovery and prompt perception."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.contracts.protocols import Tool
from lca.contracts.protocols.preset.repository import PresetRepositoryProtocol
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository
from lca.infrastructure.tools.dynamic.bridge import DynamicToolBridge

_log = structlog.get_logger(__name__)


class PresetStatus(StrEnum):
    """Lifecycle status of a discovered preset."""

    ACTIVE = "active"
    BROKEN = "broken"


@dataclass(frozen=True, slots=True)
class DiscoveredPreset:
    """A discovered preset package with runtime status and materialized tools."""

    preset_id: str
    scope: PresetScope
    package: PresetPackage | None
    status: PresetStatus
    tools: tuple[Tool, ...] = ()
    error_message: str | None = None


class AssistantPresetDiscovery:
    """Discovers, validates and materializes autonomous presets for an assistant."""

    def __init__(
        self,
        assistant_home: Path | str | None = None,
        *,
        repository: PresetRepositoryProtocol | None = None,
    ) -> None:
        self._assistant_home = Path(assistant_home) if assistant_home else None
        self._repo = repository or FileSystemPresetRepository()

    def discover_presets(
        self,
        assistant_home: Path | str | None = None,
    ) -> tuple[DiscoveredPreset, ...]:
        """Scan assistant presets directory and return discovered presets with status.

        Fault-isolated (INV-RESILIENCE): Corrupted or syntax-broken presets are
        quarantined with status=BROKEN, allowing healthy presets to load safely.
        """
        home = Path(assistant_home) if assistant_home else self._assistant_home
        if home is None:
            return ()

        presets_dir = home / "presets"
        if not presets_dir.is_dir():
            return ()

        discovered: list[DiscoveredPreset] = []
        for child in sorted(presets_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            preset_id = child.name
            try:
                package = self._repo.find_by_id(
                    preset_id, assistant_home=home, scope=PresetScope.PRIVATE
                )
                if package is None:
                    # Missing bundle or invalid structure
                    raise ValueError(f"Preset {preset_id!r} has no valid bundle or metadata")

                tools: list[Tool] = []
                for plugin in package.plugins:
                    tool = self._load_plugin_tool(child, plugin)
                    if tool is not None:
                        tools.append(tool)

                discovered.append(
                    DiscoveredPreset(
                        preset_id=preset_id,
                        scope=package.scope,
                        package=package,
                        status=PresetStatus.ACTIVE,
                        tools=tuple(tools),
                    )
                )
            except Exception as exc:
                _log.warning(
                    "preset_discovery.quarantined_broken_preset",
                    preset_id=preset_id,
                    error=str(exc),
                    exc_info=True,
                )
                discovered.append(
                    DiscoveredPreset(
                        preset_id=preset_id,
                        scope=PresetScope.PRIVATE,
                        package=None,
                        status=PresetStatus.BROKEN,
                        tools=(),
                        error_message=str(exc),
                    )
                )

        return tuple(discovered)

    def discover_tools(
        self,
        assistant_home: Path | str | None = None,
    ) -> tuple[Tool, ...]:
        """Discover and materialize all valid tools from active presets."""
        presets = self.discover_presets(assistant_home)
        tools: list[Tool] = []
        for preset in presets:
            if preset.status == PresetStatus.ACTIVE:
                tools.extend(preset.tools)
        return tuple(tools)

    def render_prompt_overview(
        self,
        assistant_home: Path | str | None = None,
    ) -> str:
        """Render a structured Markdown block describing available autonomous tools."""
        presets = self.discover_presets(assistant_home)
        active_presets = [p for p in presets if p.status == PresetStatus.ACTIVE and p.package]
        if not active_presets:
            return ""

        lines = [
            "## Autonomous Presets & Custom Tools",
            "The following custom presets and tools are available in your autonomous workspace:",
        ]
        for item in active_presets:
            pkg = item.package
            if pkg is None:
                continue
            desc = f" — {pkg.description}" if pkg.description else ""
            lines.append(f"- **{pkg.preset_id}** ({pkg.scope.value}{desc})")
            if item.tools:
                for tool in item.tools:
                    tool_desc = tool.description or "No description provided."
                    lines.append(f"  - `{tool.name}`: {tool_desc}")
            elif pkg.plugins:
                for pl in pkg.plugins:
                    lines.append(f"  - `{pl.name}`: Custom authored plugin")

        return "\n".join(lines)

    def _load_plugin_tool(self, preset_dir: Path, plugin: AuthoredPlugin) -> Tool | None:
        """Dynamically load and adapt a plugin into a Tool instance."""
        plugin_file = preset_dir / "plugins" / f"{plugin.name}.py"
        if not plugin_file.is_file():
            return None

        module_name = f"lca_presets._autonomous.{preset_dir.name}.{plugin.name}"
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_file))
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to create spec for {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 1. Check for factory
        factory_fn = getattr(module, "factory", None) or getattr(module, f"{plugin.name}_factory", None)
        target_fn: Any = None
        if factory_fn is not None and callable(factory_fn):
            target_fn = factory_fn()
        else:
            target_fn = getattr(module, plugin.name, None) or getattr(module, "run", None)

        if target_fn is None:
            raise AttributeError(
                f"Plugin {plugin.name!r} does not expose a callable factory, "
                f"function {plugin.name!r}, or run()"
            )

        meta: dict[str, Any] = getattr(module, "plugin_meta", {}) or {}
        desc = (
            meta.get("description")
            or getattr(target_fn, "__doc__", "")
            or f"Autonomous tool {plugin.name}"
        ).strip()
        params = meta.get("parameters")
        caps = tuple(meta.get("capabilities", plugin.capabilities))

        if callable(target_fn):
            return DynamicToolBridge.bridge_callable(
                name=plugin.name,
                func=target_fn,
                description=desc,
                parameters=params,
                capabilities=caps,
            )
        return DynamicToolBridge.bridge_instance(
            name=plugin.name,
            instance=target_fn,
            meta=meta,
        )


__all__ = [
    "AssistantPresetDiscovery",
    "DiscoveredPreset",
    "PresetStatus",
]
