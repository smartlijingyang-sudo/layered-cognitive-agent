"""perceive.sense — Sensor.fold(state) → sensor_items.

worker: sense(*, sensors_artifact, state_artifact) -> sensor_items
kind: TRANSFORMER
out_port: sensor_items
in: sensors=sensors_artifact state=state_artifact
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import fold_sensor_items


def sense(
    *,
    sensors_artifact: Artifact | None,
    state_artifact: Artifact | None,
) -> dict[str, Artifact]:
    """Call Sensor.read(state) for each resolved sensor."""
    return fold_sensor_items(
        sensors_artifact=sensors_artifact,
        state_artifact=state_artifact,
    )


__all__ = ["sense"]
