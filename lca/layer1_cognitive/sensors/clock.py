"""ClockSensor — emits a ``clock`` ContextItem (PR3b).

Single source of truth for the ``current_date`` line in the prompt.  The
Reasoner no longer calls ``datetime.now()`` directly — it reads the
manifest's ``clock`` item (PR3c).

The clock factory ``build_clock_sensor`` is the named factory consumed by
the Composer (per spec §5.5: 固定组合顺序).
"""

from __future__ import annotations

from datetime import datetime, timezone

from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Sensor


class ClockSensor(Sensor):
    """Capture current UTC time as a single clock item."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now

    async def read(self, state: AgentState) -> list[ContextItem]:
        now = self._now or datetime.now(timezone.utc)
        return [
            ContextItem(
                kind="clock",
                payload=now.strftime("%Y-%m-%d %A"),
                provenance="clock_sensor",
            )
        ]


def build_clock_sensor() -> Sensor:
    """Named factory: ``sensor.clock`` (PR3b).

    Used by the Composer when wiring ``SequentialPerceiveHub``.  Default
    behavior reads ``datetime.now()``; tests can pass a fixed time via
    ``ClockSensor(now=...)``.
    """
    return ClockSensor()
