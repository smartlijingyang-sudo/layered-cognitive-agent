"""Mutable session for one stack command run."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from deploy.lobehub.stack.config import StackConfig
from deploy.lobehub.stack.types import BoundSurface, ProcessSnapshot, Section


@dataclass
class StackSession:
    root: Path
    config: StackConfig
    command: str
    previous: ProcessSnapshot | None = None
    current: ProcessSnapshot | None = None
    surfaces: list[BoundSurface] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    newer: list[Path] = field(default_factory=list)
    json_mode: bool = False
    failed: bool = False
    stream: TextIO = field(default_factory=lambda: sys.stdout)

    def emit(self, line: str) -> None:
        if self.json_mode:
            return
        self.stream.write(line.rstrip() + "\n")
        self.stream.flush()
