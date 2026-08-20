"""ConsoleJournalProjector factory plugin (Tier-2).

把 ``ConsoleJournalProjector`` 注册为 ``fact_readers`` 的 factory。
人类视图场景卡 + 角色叙事 + Run Card + 序列图。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols import JournalProjector
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-reader-console-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Register ConsoleJournalProjector factory as fact_readers['console'].",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_console_reader",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry, ObservabilitySettings
    from lca.layer0_infra.observability.journal.console_projector import (
        ConsoleJournalProjector,
    )

    registry: NamedRegistry = ctx.require("fact_readers")

    def _make_console(settings: ObservabilitySettings | None = None, **_: Any) -> JournalProjector:
        cfg = settings or ObservabilitySettings()
        return ConsoleJournalProjector(verbosity=cfg.verbosity)

    registry.register("console", _make_console)
