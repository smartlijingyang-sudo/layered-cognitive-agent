"""``spine.sink.console`` — L0 stdout sink for development.

Provides ``console_sink``. ``write`` never raises — serialization or I/O
failures are swallowed so a console sink cannot break the spine hot path.

Two formats, selected by bundle ``config.format``: ``jsonl`` (default) emits one
JSON object per ``EventRecord``; ``graph_timeline`` emits only graph lifecycle
records as compact lines, for reading a live run.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, TextIO

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.graph_timeline import (
    is_graph_event,
    render_line,
)
from lca.infrastructure.observability.spine.event.record import EventRecord

log = logging.getLogger(__name__)


class ConsoleSink:
    """Best-effort stdout sink.

    ``jsonl`` (default) writes one JSON object per ``EventRecord``, which is what
    a machine consumer wants. ``graph_timeline`` writes only graph lifecycle
    records, one compact line each, which is what a person watching a live run
    wants; the full-payload JSONL of the same events stays in the run's spine
    file, so nothing is lost by narrowing the stream.

    Both formats render through
    :func:`lca.infrastructure.observability.graph_timeline.render_line`, so a
    line seen here is byte-identical to the one ``trace-show`` later prints for
    the same ``run_id`` + ``seq``.
    """

    def __init__(self, stream: TextIO | None = None, *, format: str = "jsonl") -> None:
        self._stream: TextIO = stream if stream is not None else sys.stdout
        self._format = format

    def write(self, record: EventRecord) -> None:
        try:
            if self._format == "graph_timeline":
                if not is_graph_event(record.execution_point):
                    return
                line = render_line(
                    record.execution_point,
                    record.payload,
                    run_id=record.run_id,
                    seq=record.sequence,
                )
            else:
                line = json.dumps(asdict(record), default=str, sort_keys=False)
            self._stream.write(line + "\n")
            self._stream.flush()
        except Exception:
            # INTENTIONAL: sink 写入失败必须 swallow(否则会从 spine 冒泡到
            # K6 fail-loud)。Broken pipe / encoding 错误是预期环境噪声,
            # 留 structlog 兜底,console 输出不应阻塞主路径。
            log.exception("spine.console.write failed record_id=%s", id(record))

    def close(self) -> None:
        return


@plugin(
    id="spine.sink.console",
    provides=("console_sink",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "Console sink — stdout EventRecord JSON lines, or compact phase_graph "
        "lines via config.format; provides console_sink. write() never raises."
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
    fmt = config.get("format", "jsonl") if isinstance(config, Mapping) else "jsonl"
    ctx.provide("console_sink", ConsoleSink(format=fmt))


__all__ = ["ConsoleSink", "setup"]
