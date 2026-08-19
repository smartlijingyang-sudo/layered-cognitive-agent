"""Clock sensor plugin — Tier-2 named factory ``sensor.clock`` (PR3b)."""

from __future__ import annotations

from cordis import plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.clock import build_clock_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.clock")
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.clock``.

    The Composer pulls this when assembling ``SequentialPerceiveHub``.
    Plugins provide named factories — not lists — so the Hub composition
    order is fixed (per spec §5.5).
    """
    ctx.provide("sensor.clock", build_clock_sensor)
