"""cordis.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of :mod:`cordis` so other
packages in the taiyi workspace can declare a stable dependency on the
contract without coupling to the implementation layout.

1:1 with upstream `vendor/cordis/src/invariant/` (which in TS is just a
re-export barrel; we mirror that pattern as a Python subpackage).
"""

from __future__ import annotations

from cordis.context import Context, Hook
from cordis.disposer import Disposer, DisposableMixin, Effect, dispose_all, run_disposer
from cordis.events import EventsService, Hook as EventHook, is_bailed
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