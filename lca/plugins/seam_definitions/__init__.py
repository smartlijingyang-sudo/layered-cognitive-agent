"""Seam definitions plugin — declarative replacement for ``register_seam_catalog()``.

This is a pure-declaration bundle plugin (no logic). It declares all
extension points (seam keys) that the LCA capability system uses.

Spec reference: §4 A.7 of ``docs/specs/harness-spine-spec.md``.
"""

from typing import Any

from lca.contracts.harness.plugin import (
    ExtensionPoint,
    PluginKind,
    PluginManifest,
)

manifest = PluginManifest(
    id="lca.seam.definitions",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.BUNDLE,
    extension_points=(
        ExtensionPoint(seam_key="llm", description="LLM adapter"),
        ExtensionPoint(seam_key="sandbox", description="Sandbox runtime"),
        ExtensionPoint(seam_key="memory", description="Memory system"),
        ExtensionPoint(seam_key="state_store", description="State store"),
        ExtensionPoint(seam_key="search", description="Search provider"),
        ExtensionPoint(seam_key="tools", description="Tool executor"),
        ExtensionPoint(seam_key="transport", description="Agent transport"),
        ExtensionPoint(seam_key="skills", description="Skill store"),
        ExtensionPoint(seam_key="file_store", description="File store"),
        ExtensionPoint(seam_key="observability", description="Observability backend"),
        ExtensionPoint(seam_key="agent_loop", description="Agent loop factory"),
        ExtensionPoint(
            seam_key="session_service", description="Session event sourcing and projection"
        ),
        ExtensionPoint(
            seam_key="system_prompt",
            description="Composable prompt assembly",
        ),
    ),
)

name = "lca.seam.definitions"


def apply(ctx: Any, config: Any) -> None:
    """No-op: this plugin is pure declaration."""
