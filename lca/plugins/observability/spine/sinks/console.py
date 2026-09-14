"""``spine.sink.console`` — L0 stdout sink for development.

Provides ``console_sink``. ``write`` never raises — serialization or I/O
failures are swallowed so a console sink cannot break the spine hot path.

Two formats, selected by bundle ``config.format``: ``jsonl`` (default) emits one
JSON object per ``EventRecord``; ``graph_timeline`` emits only graph lifecycle
records as compact lines, for reading a live run.

Production wiring: after ADR-0186 the live spine writes flow through
``Session.observe`` (the spine_file_sink pattern, see
``lca.plugins.events._session_observe``); the sink therefore registers
itself as a Session observer from ``setup`` so the live EventSpine does not
have to wire it. The ``EventSink.write`` surface stays for tests.
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
from lca.contracts.event import EventPayload
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
    split_event_id,
)
from lca.infrastructure.observability.spine.event.record import EventRecord
from lca_kernel.events.bus.bus import EventRef

log = logging.getLogger(__name__)


# marker class for ``register_as_session_observer``: identifies this sink
# in the observer catalog (one slot per plugin marker, last write wins).
_CONSOLE_SINK_PLUGIN_MARKER = type("SpineConsoleSinkObserver", (), {})


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

    def write_event(
        self,
        execution_point: str,
        payload: Mapping[str, Any],
        event_id: str,
    ) -> None:
        """Session-observer entrypoint.

        Bypasses the strict ``EventRecord.__post_init__`` checks by going
        straight to ``render_line`` / JSON. The join keys
        (``run_id=``, ``seq=``) are parsed from ``event_id`` so the live
        line stays byte-identical to the post-hoc ``trace-show`` output.
        """
        try:
            if self._format == "graph_timeline":
                if not is_graph_event(execution_point):
                    return
                run_id, seq = split_event_id(event_id)
                line = render_line(execution_point, payload, run_id=run_id, seq=seq)
            else:
                line = json.dumps(
                    {
                        "execution_point": execution_point,
                        "payload": dict(payload),
                        "event_id": event_id,
                    },
                    default=str,
                    sort_keys=False,
                )
            self._stream.write(line + "\n")
            self._stream.flush()
        except Exception:
            log.exception(
                "spine.console.write_event failed event_id=%s", event_id
            )

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
    """Provide a singleton ``ConsoleSink`` and register it as a Session observer.

    The live EventSpine does not wire this sink (its topo order runs
    ``spine.core`` before this plugin's setup, so the ``soft_get`` is empty
    and the live ``EventSpine._sinks`` collapses to ``_NoOpSink``). The
    spine_file_sink works around the same DAG shape by registering through
    ``lca.plugins.events._session_observe.register_as_session_observer``;
    we follow that pattern.
    """
    fmt = config.get("format", "jsonl") if isinstance(config, Mapping) else "jsonl"
    sink = ConsoleSink(format=fmt)
    ctx.provide("console_sink", sink)

    from lca.plugins.events._session_observe import register_as_session_observer

    def _observer(payload: EventPayload, ref: EventRef) -> None:
        execution_point = getattr(payload, "execution_point", None)
        if not isinstance(execution_point, str):
            return
        payload_dict = getattr(payload, "payload", None)
        if not isinstance(payload_dict, Mapping):
            payload_dict = {}
        sink.write_event(execution_point, payload_dict, ref.event_id)

    register_as_session_observer(_CONSOLE_SINK_PLUGIN_MARKER, _observer)


__all__ = ["ConsoleSink", "setup"]
