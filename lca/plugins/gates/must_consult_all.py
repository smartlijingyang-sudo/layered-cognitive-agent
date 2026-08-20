"""MustConsultAllMembers plugin — named factory ``gate.must-consult-all``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.must-consult-all")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.must-consult-all``."""
    ctx.provide("gate.must-consult-all", MustConsultAllMembers)
