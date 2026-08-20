"""DSH Bridge plugin — Tier-3 (alien loop driver)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from lca.contracts.models.core.plane import PlaneRef
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer0_infra.file_store import FileStore


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-dsh-bridge",
    provides=["dsh_bridge_factory"],
    layer="L1",
    effects="tools",
    description="Register the DSH bridge factory as a fallback loop provider.",
    test_suite="tests/test_dsh_driver.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the DSH bridge factory as a fallback loop provider."""
    from lca.layer0_infra.dsh.launch import build_harness_env
    from lca.layer0_infra.dsh.settings import DshSettings

    settings = DshSettings()

    def dsh_bridge_factory(
        machine: PlaneRef,
        *,
        run_id: str,
        session_root: Path | str,
        attachment_ids: Sequence[str] | None = None,
        store: FileStore | None = None,
    ) -> dict[str, str]:
        return build_harness_env(
            machine,
            run_id=run_id,
            session_root=session_root,
            attachment_ids=attachment_ids,
            settings=settings,
            store=store,
        )

    ctx.provide("dsh_bridge_factory", dsh_bridge_factory)
