"""Joiner — collect all upstream outputs before downstream node fires.

Pure: holds nothing besides an artifact-by-port dictionary.
"""

from __future__ import annotations

from agent_lab.primitives.artifact import Artifact


class Joiner:
    """Per-node input accumulator. drop() returns the ready inputs dict."""

    def __init__(self, expected_ports: tuple[str, ...]):
        self.expected = set(expected_ports)
        self.buffer: dict[str, Artifact] = {}

    def feed(self, port_id: str, artifact: Artifact) -> bool:
        if port_id in self.buffer:
            return False
        self.buffer[port_id] = artifact
        return self.is_ready()

    def is_ready(self) -> bool:
        if not self.expected:
            return True
        return self.expected.issubset(self.buffer.keys())

    def drop(self) -> dict[str, Artifact]:
        ready, self.buffer = self.buffer, {}
        return ready
