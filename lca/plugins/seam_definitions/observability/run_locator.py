"""RunLocator seam plugin (Tier-1) —— ADR-0065 §七 / PR-5。

声明 ``run_locator`` capability;boot 后由 provider 注入 fs 默认实现。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from lca.contracts.observability.run_locator import RunLocator
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-run-locator-seam",
    provides=["run_locator"],
    implements=[RunLocator],
    layer="L0",
    effects="filesystem",
    description="Provide run_locator capability seam (ADR-0065 §七 / PR-5).",
    test_suite="tests/test_seam_run_locator.py::test_seam_provides_filesystem_locator",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability.run_locator_fs import FilesystemRunLocator

    del config
    root = Path("traces")
    locator = FilesystemRunLocator(root=root)
    ctx.provide("run_locator", locator)
