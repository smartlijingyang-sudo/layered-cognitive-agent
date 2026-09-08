"""agent_lab.plugins — graph plugin system.

Every cross-cutting concern (event emission, metrics, control binding,
parse rules, memory policy, stop policy, LLM provider selection) is a
plugin, not inline code in the runner or node files. Importing this
package triggers ``discover()`` so the runner can resolve plugin kinds.

Public surface:
  GraphPlugin, HookContext, HookEvent, Bind, register_plugin, discover,
  resolve_plugin, fanout_hooks
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
    discover,
    fanout_hooks,
    get_fixture_instance,
    get_instance,
    get_plugin_class,
    register_fixture_instance,
    register_instance,
    register_plugin,
    resolve_plugin,
    unregister_fixture_instance,
    unregister_instance,
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
    "discover",
    "fanout_hooks",
    "get_fixture_instance",
    "get_instance",
    "get_plugin_class",
    "register_fixture_instance",
    "register_instance",
    "register_plugin",
    "resolve_plugin",
    "unregister_fixture_instance",
    "unregister_instance",
]
