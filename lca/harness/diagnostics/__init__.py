"""Harness diagnostics — inspect, replay, doctor."""

from lca.harness.diagnostics.inspect import (
    format_plugin_tree,
    inspect_profile_tree,
    why_capability,
    why_plugin,
)
from lca.harness.diagnostics.tree import render_tree

__all__ = [
    "format_plugin_tree",
    "inspect_profile_tree",
    "render_tree",
    "why_capability",
    "why_plugin",
]
