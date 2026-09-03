"""Journal sink plugin 包（ADR-0180 / plugin-universe PR-4）。

PR-4 可见性：本 ``__init__.py`` re-export ``setup_journal_sink`` 为 ``setup``，
使 ``bundles/event-bus-components.yaml`` 的 ``$module: lca.plugins.events.sinks.journal``
能被 profile resolver 经 ``getattr(module, "setup")`` 取到 plugin Manifest。
机制仍按 yaml SSOT 鉴权（journal 装载即抛；本 PR 不改此行为，由 PR-6 收口）。
"""
from lca.plugins.events.sinks.journal.manifest import setup_journal_sink as setup
from lca.plugins.events.sinks.journal.sink import JournalSink

__all__ = ["JournalSink", "setup"]
