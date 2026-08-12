"""Agent Timeline wire contract (timeline.v1).

Closed event set for UI consumption. Journal remains full SSOT on disk;
only events listed here leave the gateway toward LobeHub.

Canonical definitions live in sse_encode.py; this module re-exports for
backward-compatible imports.
"""

from __future__ import annotations

from gateway.timeline.sse_encode import EVENT_TYPES, TIMELINE_V

# Re-export for backward compatibility
__all__ = ["EVENT_TYPES", "TIMELINE_V"]
