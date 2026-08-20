"""Observability Provider plugin — Tier-2.

Owns run-hub construction. Execute injects ``observability`` and calls
``create(...)``; it does not call ``create_observability`` itself.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from lca.contracts.protocols import ObservabilityBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer0_infra.observability import ObservabilitySettings, create_observability

_SKIP_BACKENDS = frozenset({"console", "jsonl"})


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["console"])


def _make_hub(**kwargs: Any) -> Any:
    settings = kwargs.get("settings")
    extra_projectors = tuple(kwargs.get("extra_projectors") or ())
    diagnostic_sinks = tuple(kwargs.get("diagnostic_sinks") or ())
    cfg = settings if settings is not None else ObservabilitySettings()
    names = [name for name in cfg.backend_names() if name not in _SKIP_BACKENDS]
    return create_observability(
        "+".join(names),
        settings=cfg,
        extra_projectors=extra_projectors,
        diagnostic_sinks=diagnostic_sinks,
    )


@plugin(
    id="lca-observability-provider",
    requires=["observability"],
    implements=[ObservabilityBackend],
    layer="L0",
    effects="none",
    description="Register ObservabilityBackend factories on the ObservabilityService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if "console" in config.providers:
        ctx.inject("observability").register("console", _make_hub)
