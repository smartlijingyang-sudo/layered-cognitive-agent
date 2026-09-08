"""agent_lab.plugins — graph plugin system.

Every cross-cutting concern (event emission, metrics, control binding,
parse rules, memory policy, stop policy, LLM provider selection) is a
plugin, not inline code in the runner or node files.

PR-A.3 status:
  The plugin registration surface (register_plugin, discover, resolve_plugin,
  etc.) has been removed. Plugin resolution now uses lca.plugins.lab.internal.loader.
  The 9 Plugin subclasses remain as marker interfaces (until PR-D rewrites
  the hook subclasses into handler functions).

Public surface:
  GraphPlugin, HookContext, HookEvent, Bind, fanout_hooks
  ControlSlotsPlugin     (agent_lab.plugins.control_slots)
  SemanticRouterPlugin   (agent_lab.plugins.semantic_router)
  EventSinkPlugin        (agent_lab.plugins.events)
  ObserverPlugin         (agent_lab.plugins.observers)
  ParseDecisionPlugin    (agent_lab.plugins.parsers)
  ObservationRenderPlugin (agent_lab.plugins.observation)
  MemoryExtractPlugin    (agent_lab.plugins.memory_extract)
  ToolDispatchGuardPlugin (agent_lab.plugins.tool_guard)
"""

from agent_lab.plugins.base import (
    Bind,
    GraphPlugin,
    HookContext,
    HookEvent,
    fanout_hooks,
)
from agent_lab.plugins.control_slots import ControlSlotsPlugin
from agent_lab.plugins.events import EventSinkPlugin
from agent_lab.plugins.memory_extract import MemoryExtractPlugin
from agent_lab.plugins.observation import ObservationRenderPlugin
from agent_lab.plugins.observers import ObserverPlugin
from agent_lab.plugins.parsers import ParseDecisionPlugin
from agent_lab.plugins.semantic_router import SemanticRouterPlugin
from agent_lab.plugins.tool_guard import ToolDispatchGuardPlugin

__all__ = [
    "Bind",
    "ControlSlotsPlugin",
    "EventSinkPlugin",
    "GraphPlugin",
    "HookContext",
    "HookEvent",
    "MemoryExtractPlugin",
    "ObservationRenderPlugin",
    "ObserverPlugin",
    "ParseDecisionPlugin",
    "SemanticRouterPlugin",
    "ToolDispatchGuardPlugin",
    "fanout_hooks",
]
