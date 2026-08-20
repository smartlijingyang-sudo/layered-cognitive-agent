"""Inbox-facts sensor plugin — Tier-2 named factory ``sensor.inbox-facts`` (PR8)."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.sensors.journal_backed import build_inbox_facts_sensor


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="sensor.inbox-facts")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named sensor factory ``sensor.inbox-facts``."""
    ctx.provide("sensor.inbox-facts", build_inbox_facts_sensor)
