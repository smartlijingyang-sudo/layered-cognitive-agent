"""``spine.sink.file`` — L0 FileSink capability provider.

Provides the ``file_sink`` capability backed by the infrastructure
``FileSink`` (append-only JSONL under a run directory). Profile config
supplies ``path`` (default ``.lca/spine/events.jsonl``) and optional
``run_id`` (default ``boot``).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

_DEFAULT_PATH = ".lca/spine/events.jsonl"
_DEFAULT_RUN_ID = "boot"


def _register_sink_close(ctx: PluginContext, sink: FileSink) -> None:
    """Register ``sink.close`` on the Cordis disposer chain when reachable.

    ``AuditedPluginContext`` does not expose ``effect`` on its public
    surface; try the facade first, then the wrapped inner context.
    """
    effect = getattr(ctx, "effect", None)
    if callable(effect):
        effect(sink.close, label="spine.sink.file:close")
        return
    inner = getattr(ctx, "_AuditedPluginContext__inner", None)
    inner_effect = getattr(inner, "effect", None) if inner is not None else None
    if callable(inner_effect):
        inner_effect(sink.close, label="spine.sink.file:close")


@plugin(
    id="spine.sink.file",
    provides=("file_sink",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.FILESYSTEM,
    description=(
        "File sink — append-only events.jsonl truth store for the spine; "
        "provides file_sink for spine.core and EmitPipeline consumers."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_sinks",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_source",)),
        observability=EvidenceContract(
            descriptors=("spine.file_sink",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("file_sink",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Construct a ``FileSink`` from profile config and provide ``file_sink``."""
    cfg: Mapping[str, Any] = config if isinstance(config, Mapping) else {}
    path = Path(str(cfg.get("path", _DEFAULT_PATH)))
    run_id = str(cfg.get("run_id", _DEFAULT_RUN_ID))

    run_dir = path.parent if str(path.parent) not in ("", ".") else Path(".")
    file_name = path.name or "events.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)

    sink = FileSink(run_dir, run_id=run_id, file_name=file_name)
    ctx.provide("file_sink", sink)
    _register_sink_close(ctx, sink)


__all__ = ["setup"]
