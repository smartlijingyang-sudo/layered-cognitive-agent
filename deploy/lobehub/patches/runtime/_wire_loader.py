"""Lazy WIRE table loader for patch modules.

Patch discovery imports every ``deploy/lobehub/patches/runtime/*.py`` module.
Importing ``lca.plugins.transport.webserver.handlers.runs.wire`` at module
level pulls the full plugin graph (including optional redis). Defer the import
to ``apply()`` time when ``uv run`` is available.
"""

from __future__ import annotations

from collections.abc import Mapping


def load_wire() -> Mapping[str, tuple[str, str]]:
    from lca.plugins.transport.webserver.handlers.runs.wire import WIRE

    return WIRE
