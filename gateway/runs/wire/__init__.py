"""wire subpackage of gateway.runs — split per ADR-0105 §11.2.

Re-exports WIRE for callers using ``from gateway.runs.wire import WIRE``.
"""

from gateway.runs.wire.wire import WIRE

__all__ = ["WIRE"]
