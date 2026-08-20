"""taiyi-cordis — Python port of @deepseek-ai/cordis plugin framework.

Public API is re-exported here for convenience. The stable contract is
defined in :mod:`cordis.invariant`; consumers should depend on that submodule
when they need a stable API surface.

1:1 alignment with `~/deepseek-harness/vendor/cordis/src/`.
"""

from __future__ import annotations

from cordis.context import Context, Hook
from cordis.disposer import DisposableMixin, Disposer, Effect, dispose_all, run_disposer
from cordis.events import EventsService, is_bailed
from cordis.events import Hook as EventHook
from cordis.fiber import CordisError, Fiber, FiberState, ValidationError
from cordis.loader import (
    Bundle,
    Entry,
    EntryGroup,
    EntryTree,
    Loader,
    dump_config,
    interpolate,
    load_config,
    load_yaml,
    merge_bundles,
)
from cordis.logger import (
    Exporter,
    Logger,
    LoggerLevel,
    LoggerService,
    Message,
    default_formatters,
)
from cordis.plugin import Plugin, get_plugin_inject, get_plugin_meta, get_plugin_name, is_plugin, plugin
from cordis.reflect import Impl, Property, ReflectService
from cordis.registry import (
    PluginRuntime,
    RegistryService,
)
from cordis.service import Service
from cordis.utils import DisposableList, Tracker, is_constructor, is_object, symbols

__all__ = [
    # Context
    "Context",
    "Hook",
    # Disposer
    "Disposer",
    "DisposableMixin",
    "Effect",
    "dispose_all",
    "run_disposer",
    # Events
    "EventsService",
    "EventHook",
    "is_bailed",
    # Fiber
    "CordisError",
    "Fiber",
    "FiberState",
    "ValidationError",
    # Loader
    "Bundle",
    "Entry",
    "EntryGroup",
    "EntryTree",
    "Loader",
    "dump_config",
    "interpolate",
    "load_config",
    "load_yaml",
    "merge_bundles",
    # Logger
    "Exporter",
    "Logger",
    "LoggerLevel",
    "LoggerService",
    "Message",
    "default_formatters",
    # Plugin
    "Plugin",
    "get_plugin_inject",
    "get_plugin_meta",
    "get_plugin_name",
    "is_plugin",
    "plugin",
    # Reflect
    "Impl",
    "Property",
    "ReflectService",
    # Registry
    "PluginRuntime",
    "RegistryService",
    # Service
    "Service",
    # Utils
    "DisposableList",
    "Tracker",
    "is_constructor",
    "is_object",
    "symbols",
]
