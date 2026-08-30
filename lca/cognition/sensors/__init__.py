"""L1 sensor implementations (PR3a / PR3b / PR8 / PR9 / PR13 / PR14).

Each sensor implements the ``Sensor`` Protocol and is paired with a
named factory (per spec §5.5: plugins provide named factories — not
lists).  The Composer pulls factories by name and assembles
``SequentialPerceiveHub`` in a fixed composition order.
"""

from lca.cognition.sensors.clock import ClockSensor, build_clock_sensor
from lca.cognition.sensors.journal_backed import (
    INBOX_FACTS_KIND,
    TEAM_INBOX_KIND,
    InboxFactsSensor,
    TeamInboxSensor,
    build_inbox_facts_sensor,
    build_team_inbox_sensor,
)
from lca.cognition.sensors.workspace_artifacts import (
    WorkspaceArtifactsSensor,
    build_workspace_artifacts_sensor,
)

__all__ = [
    "INBOX_FACTS_KIND",
    "TEAM_INBOX_KIND",
    "ClockSensor",
    "InboxFactsSensor",
    "TeamInboxSensor",
    "WorkspaceArtifactsSensor",
    "build_clock_sensor",
    "build_inbox_facts_sensor",
    "build_team_inbox_sensor",
    "build_workspace_artifacts_sensor",
]
