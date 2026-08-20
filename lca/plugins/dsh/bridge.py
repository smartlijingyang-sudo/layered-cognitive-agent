"""DSH Bridge plugin — Tier-3 (alien loop driver)."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-dsh-bridge")
async def setup(ctx: Context, config: Config) -> None:
    """Register the DSH bridge factory as a fallback loop provider."""
    from lca.layer0_infra.dsh.launch import build_harness_env
    from lca.layer0_infra.dsh.settings import DshSettings

    settings = DshSettings()

    def dsh_bridge_factory(
        machine: object,
        *,
        run_id: str,
        session_root: object,
        attachment_ids: list[str] | None = None,
        store: object | None = None,
    ) -> object:
        return build_harness_env(
            machine,
            run_id=run_id,
            session_root=session_root,
            attachment_ids=attachment_ids,
            settings=settings,
            store=store,
        )

    ctx.provide("dsh_bridge_factory", dsh_bridge_factory)
