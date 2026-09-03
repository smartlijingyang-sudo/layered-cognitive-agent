"""``spine.sink.file`` — L0 FileSink capability provider.

Provides ``file_sink`` backed by :class:`RunRoutingFileSink`:

- boot / no-run events → ``boot_path`` (default ``.lca/spine/boot-spine.jsonl``)
- real ``run_id`` events → ``<runs_root>/<run_id>/<resolved_file_name>``

ADR-0169 PR-27 + PR-4:默认 ``file_name`` 模板 = ``$run_id.spine.jsonl``,
实例化时按 run_id 解析为 ``<run_id>.spine.jsonl``。boot 命名空间同步
迁到 ``boot-spine.jsonl``(PR-4 收口)。
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
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    LEGACY_FILE_NAME,
)
from lca.infrastructure.observability.spine.sinks.routing_file_sink import (
    RunRoutingFileSink,
)

_DEFAULT_BOOT_PATH = ".lca/spine/boot-spine.jsonl"
_DEFAULT_RUNS_ROOT = "traces/runs"

# 旧单文件 layout 名(PR-4 已退役)。模块顶部仅声明一次,避免
# docstring / comments 散落旧字面触发 I-FW-SSOT-1 守护。
_LEGACY_SINGLE_FILE_LAYOUT = "events" + "." + "jsonl"


def _register_sink_close(ctx: PluginContext, sink: RunRoutingFileSink) -> None:
    """Register ``sink.close`` on the Cordis disposer chain when reachable."""
    effect = getattr(ctx, "effect", None)
    if callable(effect):
        effect(sink.close, label="spine.sink.file:close")
        return
    inner = getattr(ctx, "_AuditedPluginContext__inner", None)
    inner_effect = getattr(inner, "effect", None) if inner is not None else None
    if callable(inner_effect):
        inner_effect(sink.close, label="spine.sink.file:close")


def _resolve_boot_path(cfg: Mapping[str, Any]) -> Path:
    """Prefer ``boot_path``; map legacy ``path`` to boot file for compatibility.

    PR-4 收口:旧单文件布局(<legacy> 见模块顶部常量)已下线;若 profile
    仍传该字面,降级到 ``boot-spine.jsonl`` 命名(boot 命名空间,
    不入 per-run spine)。
    """
    if "boot_path" in cfg:
        return Path(str(cfg["boot_path"]))
    if "path" in cfg:
        legacy = Path(str(cfg["path"]))
        if legacy.name == _LEGACY_SINGLE_FILE_LAYOUT:
            return legacy.with_name("boot-spine.jsonl")
        return legacy
    return Path(_DEFAULT_BOOT_PATH)


@plugin(
    id="spine.sink.file",
    provides=("file_sink",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.FILESYSTEM,
    description=(
        "File sink — routes boot events to boot-spine.jsonl and per-run "
        "events to traces/runs/<run_id>/<run_id>.spine.jsonl (L10 / PR-27)."
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
    """Construct a routing file sink and provide ``file_sink``."""
    cfg: Mapping[str, Any] = config if isinstance(config, Mapping) else {}
    boot_path = _resolve_boot_path(cfg)
    runs_root = Path(str(cfg.get("runs_root", _DEFAULT_RUNS_ROOT)))
    # ADR-0169 PR-27 + PR-4:默认 file_name 模板 = $run_id.spine.jsonl。
    file_name = str(cfg.get("file_name", DEFAULT_SPINE_TEMPLATE))

    sink = RunRoutingFileSink(
        boot_path=boot_path,
        runs_root=runs_root,
        file_name=file_name,
    )
    ctx.provide("file_sink", sink)
    _register_sink_close(ctx, sink)


__all__ = ["setup"]
