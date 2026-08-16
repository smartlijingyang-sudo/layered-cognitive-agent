"""ServiceRecord — one service in the host service table."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceRecord:
    """Service ownership + availability tracking."""

    name: str
    value: Any
    owner_id: str
    check: Callable[[], bool] | None = None

    @property
    def available(self) -> bool:
        return self.check is None or bool(self.check())
