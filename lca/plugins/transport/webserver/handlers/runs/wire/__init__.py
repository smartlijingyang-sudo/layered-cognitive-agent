"""wire subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Re-exports WIRE for callers using ``from lca.plugins.transport.webserver.handlers.runs.wire import WIRE``.
"""

from lca.plugins.transport.webserver.handlers.runs.wire.wire import WIRE

__all__ = ["WIRE"]
