"""``spine.sink.console`` — L0 stdout JSONL sink for development.

Provides ``console_sink``. Writes one JSON object per ``EventRecord`` to
stdout. ``write`` never raises — serialization or I/O failures are
swallowed so a console sink cannot break the spine hot path.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any, TextIO

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
from lca.infrastructure.observability.spine.event_record import EventRecord


class ConsoleSink:
    """Best-effort stdout sink — one JSON line per EventRecord."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream: TextIO = stream if stream is not None else sys.stdout

    def write(self, record: EventRecord) -> None:
        try:
            line = json.dumps(asdict(record), default=str, sort_keys=False)
            self._stream.write(line + "\n")
            self._stream.flush()
        except Exception:
            return

    def close(self) -> None:
        return


@plugin(
    id="spine.sink.console",
    provides=("console_sink",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "Console sink — stdout JSON lines of EventRecord for development; "
        "provides console_sink. write() never raises."
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
            descriptors=("spine.console_sink",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("console_sink",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide a singleton ``ConsoleSink`` under ``console_sink``."""
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("console_sink", ConsoleSink())


__all__ = ["ConsoleSink", "setup"]
