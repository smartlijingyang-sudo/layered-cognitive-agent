"""1:1 port of ``@deepseek-ai/dsh-session/index``.

Event-sourced session service: append-only session log, in-memory store, and
the derived LLM message history.  Persistence is a plugin concern (subscribe
to ``session/event``, drain on ``session/flush``).
"""

from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable
from typing import Any, Literal, Union

from lca.layer0_infra.dsh_core.session._llm_types import Message
from lca.layer0_infra.dsh_core.session.json_ import snapshot_json_value
from lca.layer0_infra.dsh_core.session.request_header import fold_request_header
from lca.layer0_infra.dsh_core.session.surface import (
    SessionSurface,
    SurfaceManager,
    derive_event_message,
)
from lca.layer0_infra.dsh_core.session.types import (
    SESSION_FORMAT_VERSION,
    CreateSessionOptions,
    EpochHeader,
    PrepareSessionOptions,
    RequestContext,
    RestoredSessionOptions,
    SessionEvent,
    SessionHeader,
    SessionId,
    SurfaceIntent,
)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_session_header(id: SessionId, input_: Any) -> SessionHeader:
    if input_ is None or not isinstance(input_, dict):
        raise ValueError("session header is not a plain JSON record")
    record = input_
    if record.get("version") != SESSION_FORMAT_VERSION:
        raise ValueError(
            f"session header version must be {SESSION_FORMAT_VERSION}, "
            f"got {record.get('version')!r}"
        )
    if record.get("id") != id:
        raise ValueError(
            f'session header id "{record.get("id")}" does not match session id "{id}"'
        )
    created_at = record.get("createdAt")
    if (
        not isinstance(created_at, int)
        or isinstance(created_at, bool)
        or created_at < 0
    ):
        raise ValueError("session header createdAt must be a non-negative safe integer")
    cwd = record.get("cwd")
    if cwd is not None:
        if not isinstance(cwd, str):
            raise ValueError("session header cwd must be a string")
        if not os.path.isabs(cwd):
            raise ValueError(f'session header cwd must be an absolute path, got "{cwd}"')
    parent_session = record.get("parentSession")
    if parent_session is not None and not isinstance(parent_session, str):
        raise ValueError("session header parentSession must be a string")
    seed_length = record.get("seedLength")
    if seed_length is not None:
        if not isinstance(seed_length, int) or isinstance(seed_length, bool) or seed_length < 0:
            raise ValueError("session header seedLength must be a non-negative safe integer")
    origin = record.get("origin")
    if origin is not None and origin != "subagent":
        raise ValueError('session header origin must be "subagent"')
    delegation_depth = record.get("delegationDepth")
    if delegation_depth is not None:
        if not isinstance(delegation_depth, int) or isinstance(delegation_depth, bool) or delegation_depth < 0:
            raise ValueError("session header delegationDepth must be a non-negative safe integer")
    agent_preset = record.get("agentPreset")
    if agent_preset is not None and not isinstance(agent_preset, str):
        raise ValueError("session header agentPreset must be a string")
    return SessionHeader(
        version=record["version"],
        id=SessionId(record["id"]),
        createdAt=record["createdAt"],
        cwd=cwd,
        parentSession=SessionId(parent_session) if parent_session else None,
        seedLength=seed_length,
        origin=origin,
        delegationDepth=delegation_depth,
        agentPreset=agent_preset,
    )


def _validate_restored_session_header(id: SessionId, input_: Any) -> SessionHeader:
    if input_ is not None and isinstance(input_, dict):
        pass  # plain dict already
    return _validate_session_header(id, input_)


def _snapshot_session_header(
    id: SessionId, source: SessionHeader | None = None
) -> SessionHeader:
    if source is None:
        input_: Any = {
            "version": SESSION_FORMAT_VERSION,
            "id": id,
            "createdAt": _now_ms(),
        }
    else:
        input_ = {
            "version": source.version,
            "id": source.id,
            "createdAt": source.createdAt,
        }
        if source.cwd is not None:
            input_["cwd"] = source.cwd
        if source.parentSession is not None:
            input_["parentSession"] = source.parentSession
        if source.seedLength is not None:
            input_["seedLength"] = source.seedLength
        if source.origin is not None:
            input_["origin"] = source.origin
        if source.delegationDepth is not None:
            input_["delegationDepth"] = source.delegationDepth
        if source.agentPreset is not None:
            input_["agentPreset"] = source.agentPreset
    snap = snapshot_json_value(input_)
    if snap is None:
        raise ValueError("session header is not losslessly JSON-serializable")
    return _validate_session_header(id, snap)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Event adoption / snapshot
# ---------------------------------------------------------------------------


def _assert_message_event_shape(event: dict[str, Any], subject: str) -> None:
    """Validate only the event-specific invariants needed to safely replay a message."""
    type_ = event.get("type")
    if type_ not in ("user/message", "assistant/message", "tool/result"):
        return
    data = event.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"{subject} lacks message data")
    message = data if type_ == "user/message" else data.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"{subject} lacks an identified message")
    msg_id = message.get("id")
    if not isinstance(msg_id, str) or msg_id == "":
        raise ValueError(f"{subject} lacks an identified message")
    expected_role = "assistant" if type_ == "assistant/message" else "user"
    if message.get("role") != expected_role:
        raise ValueError(f'{subject} message must have role "{expected_role}"')
    source = message.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"{subject} message has invalid source")
    source_kind = source.get("kind")
    if not isinstance(source_kind, str) or source_kind == "":
        raise ValueError(f"{subject} message has invalid source")
    content = message.get("content")
    if not isinstance(content, list):
        raise ValueError(f"{subject} message has invalid content")
    if type_ == "assistant/message":
        if source_kind != "model":
            raise ValueError(f"{subject} message must have model source")
        return
    if type_ != "tool/result":
        return
    if source_kind != "tool":
        raise ValueError(f"{subject} message must have tool source")
    call_id = source.get("callId")
    if not isinstance(call_id, str) or call_id == "":
        raise ValueError(f"{subject} message must have tool source")
    if len(content) != 1:
        raise ValueError(f"{subject} message must contain one tool-result block")
    block = content[0]
    if not isinstance(block, dict):
        raise ValueError(f"{subject} message must contain one tool-result block")
    if block.get("type") != "tool-result":
        raise ValueError(f"{subject} message must contain one tool-result block")
    if not isinstance(block.get("content"), list):
        raise ValueError(f"{subject} message must contain one tool-result block")
    if block.get("toolCallId") != call_id:
        raise ValueError(f"{subject} message has mismatched tool call ids")


def _assert_supported_request_header(type_: str, data: Any, location: str) -> None:
    if type_ == "request/header-delta":
        raise ValueError(f"{location} uses unsupported legacy request/header-delta format")
    if type_ == "request/header" and isinstance(data, dict):
        if data.get("reason") == "fallback":
            raise ValueError(
                f'{location} uses unsupported legacy request/header reason "fallback"'
            )


def _assert_session_event_envelope(value: dict[str, Any], index: int) -> None:
    """Validate the fixed event envelope after one-pass JSON materialization."""
    if value.get("type") == "request/header-delta":
        raise ValueError(
            f"seed event at index {index} uses unsupported legacy request/header-delta format"
        )
    allowed_keys = {"type", "seq", "time", "data", "surfaceOp", "sourceEventSeqs", "ignorable"}
    for key in value:
        if key not in allowed_keys:
            raise ValueError(f"seed event at index {index} has an invalid event envelope")
    type_ = value.get("type")
    seq = value.get("seq")
    time_ = value.get("time")
    data = value.get("data")
    ignorable = value.get("ignorable")
    if (
        not isinstance(type_, str)
        or not isinstance(seq, int)
        or isinstance(seq, bool)
        or seq < 0
        or not isinstance(time_, int)
        or isinstance(time_, bool)
        or data is None
        or (ignorable is not None and ignorable is not True)
    ):
        raise ValueError(f"seed event at index {index} has an invalid event envelope")
    if type_ in ("request/header", "user/message", "assistant/message", "tool/result"):
        _assert_current_llm_shape(value, index)


def _assert_current_llm_shape(event: dict[str, Any], index: int) -> None:
    data = event.get("data")
    record = data if isinstance(data, dict) else None
    if event.get("type") == "request/header":
        header = record.get("header") if record else None
        header_record = header if isinstance(header, dict) else None
        config = header_record.get("config") if header_record else None
        if not _has_provider_model(config):
            raise ValueError(f"seed request/header at index {index} lacks provider/model")
    type_ = event.get("type")
    if type_ not in ("user/message", "assistant/message", "tool/result"):
        return
    _assert_message_event_shape(event, f"seed {type_} at index {index}")


def _has_provider_model(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    provider = value.get("provider")
    model = value.get("model")
    return isinstance(provider, str) and len(provider) > 0 and isinstance(model, str) and len(model) > 0


def _freeze_restored_object(value: Any) -> Any:
    """Deep-freeze one acyclic JSON tree without consuming the call stack."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, dict):
        frozen: dict[str, Any] = {}
        for k, v in value.items():
            frozen[k] = _freeze_restored_object(v)
        return frozen
    if isinstance(value, list):
        return [_freeze_restored_object(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# adopt_session_event / snapshot_session_event
# ---------------------------------------------------------------------------


def adopt_session_event(event: SessionEvent) -> SessionEvent:
    """Validate and freeze one exclusively owned event."""
    event_dict = _event_to_dict(event)
    _assert_message_event_shape(event_dict, f"session event at seq {event.seq}")
    return event


def snapshot_session_event(event: SessionEvent) -> SessionEvent:
    """Detach one event while preserving deep immutability."""
    return adopt_session_event(copy.deepcopy(event))


def _event_to_dict(event: SessionEvent) -> dict[str, Any]:
    return {
        "type": event.type,
        "seq": event.seq,
        "time": event.time,
        "data": event.data,
        "surfaceOp": event.surfaceOp,
        "sourceEventSeqs": event.sourceEventSeqs,
        "ignorable": event.ignorable,
    }


# ---------------------------------------------------------------------------
# SessionForkError
# ---------------------------------------------------------------------------

SessionForkErrorCode = Literal[
    "SESSION_NOT_FOUND",
    "SESSION_NOT_LIVE",
    "SESSION_ALREADY_EXISTS",
    "INVALID_BOUNDARY",
    "OPEN_TURN",
]


class SessionForkError(Exception):
    """Typed error for session fork rejections."""

    def __init__(self, message: str, code: SessionForkErrorCode) -> None:
        super().__init__(message)
        self.code = code
        self.name = "SessionForkError"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class Session:
    """An event-sourced session: an append-only log of SessionEvents."""

    def __init__(
        self,
        id: SessionId,
        seed: list[SessionEvent] | None = None,
        header: SessionHeader | None = None,
        mode: Literal["snapshot", "restore"] = "snapshot",
    ) -> None:
        self._log: list[SessionEvent] = []
        self._surface_manager = SurfaceManager(self._log)
        self._events_snapshot: list[SessionEvent] | None = None

        # Validate / snapshot header
        if mode == "restore":
            restored_header = _validate_restored_session_header(id, header)
        else:
            restored_header = None

        if seed is not None:
            for index, source in enumerate(seed):
                if mode == "restore":
                    snap = source
                else:
                    snap_data = snapshot_json_value(_event_to_plain(source))
                    if snap_data is None:
                        raise ValueError(
                            f"seed event at index {index} is not losslessly JSON-serializable"
                        )
                    snap = _dict_to_event(snap_data)
                event_dict = _event_to_dict(snap)
                _assert_session_event_envelope(event_dict, index)
                _assert_supported_request_header(
                    snap.type, snap.data, f"seed event at index {index}"
                )
                if snap.seq != index:
                    raise ValueError(
                        f"seed event at index {index} has seq {snap.seq} "
                        f"(expected {index}); seed must be contiguous from 0"
                    )
                try:
                    self._surface_manager.validateNext(snap)
                except Exception as error:
                    raise ValueError(
                        f"invalid seed event at index {index}: {error}"
                    ) from error
                if mode == "restore":
                    self._log.append(_freeze_restored_object(snap))  # type: ignore[arg-type]
                else:
                    self._log.append(snap)

        self.firstLiveSeq: int = len(self._log)
        self.header: SessionHeader = restored_header or _snapshot_session_header(id, header)

        # Header fold cache
        self._header_fold: EpochHeader | None = None
        self._header_fold_seq: int = 0

        # Context fold cache
        self._context_fold: RequestContext | None = None
        self._context_fold_seq: int = 0

        # Derived message cache
        self._derived: list[Message] = []
        self._derived_nodes: int = 0
        self._derived_generation: int = 0

        # Append session/end-seed marker if needed
        if seed is not None and self._log:
            last = self._log[-1]
            if last.type != "session/end-seed":
                self.append("session/end-seed", {})

    @staticmethod
    def create(
        id: SessionId,
        seed: list[SessionEvent] | None = None,
        header: SessionHeader | None = None,
    ) -> Session:
        return Session(id, seed, header, "snapshot")

    @staticmethod
    def fromRestore(
        id: SessionId,
        seed: list[SessionEvent],
        header: SessionHeader,
    ) -> Session:
        return Session(id, seed, header, "restore")

    @property
    def surface(self) -> SessionSurface:
        return self._surface_manager

    @property
    def id(self) -> SessionId:
        return self.header.id

    @property
    def events(self) -> list[SessionEvent]:
        if self._events_snapshot is None:
            self._events_snapshot = list(self._log)
        return self._events_snapshot

    @property
    def seq(self) -> int:
        return len(self._log)

    def append(
        self,
        type_: str,
        data: Any,
        opts: SurfaceIntent | None = None,
    ) -> SessionEvent:
        """Append one typed event to the log."""
        surface_metadata: dict[str, Any] = {}
        if opts is not None:
            if opts.sourceEventSeqs is not None:
                surface_metadata["sourceEventSeqs"] = opts.sourceEventSeqs
            if opts.surfaceOp is not None:
                surface_metadata["surfaceOp"] = opts.surfaceOp

        data_snapshot = snapshot_json_value(data)
        if data_snapshot is None:
            raise ValueError(
                f'session event "{type_}" carries non-JSON-serializable data'
            )
        _assert_supported_request_header(type_, data_snapshot, f'session event "{type_}"')

        surface_metadata_snapshot = snapshot_json_value(surface_metadata)
        if surface_metadata_snapshot is None and surface_metadata:
            raise ValueError(
                f'session event "{type_}" carries non-JSON-serializable surface metadata'
            )

        event = SessionEvent(
            type=type_,
            seq=len(self._log),
            time=_now_ms(),
            data=data_snapshot,
            surfaceOp=surface_metadata.get("surfaceOp"),  # type: ignore[arg-type]
            sourceEventSeqs=surface_metadata.get("sourceEventSeqs"),  # type: ignore[arg-type]
        )
        self._surface_manager.validateNext(event)

        self._log.append(event)
        self._events_snapshot = None

        # Dispatch session/event to observers
        entry = _attachments.get(id(self))
        if entry is not None and entry["observers"]:
            for observer in entry["observers"]:
                try:
                    observer(self, event)
                except Exception:  # noqa: S110 — observer failures are contained
                    pass
        return event

    def requestHeader(self) -> EpochHeader | None:
        if self._header_fold_seq < len(self._log):
            self._header_fold = fold_request_header(
                self._log[self._header_fold_seq :], self._header_fold
            )
            self._header_fold_seq = len(self._log)
        return self._header_fold

    def requestContext(self) -> RequestContext | None:
        if self._context_fold_seq < len(self._log):
            for event in self._log[self._context_fold_seq :]:
                if event.type == "request/context":
                    self._context_fold = event.data  # type: ignore[assignment]
            self._context_fold_seq = len(self._log)
        return self._context_fold

    def deriveMessages(self) -> list[Message]:
        surface = self.surface
        nodes = surface.nodes
        generation = surface.replaceGeneration
        if generation != self._derived_generation:
            self._derived = []
            self._derived_nodes = 0
            self._derived_generation = generation
        for seq in nodes[self._derived_nodes :]:
            msg = self.deriveEventMessage(self._log[seq])
            if msg is not None:
                self._derived.append(msg)
        self._derived_nodes = len(nodes)
        return list(self._derived)

    def deriveEventMessage(self, event: SessionEvent) -> Message | None:
        return derive_event_message(event)


# ---------------------------------------------------------------------------
# Internal helpers for event serialization
# ---------------------------------------------------------------------------


def _event_to_plain(event: SessionEvent) -> dict[str, Any]:
    return _event_to_dict(event)


def _dict_to_event(d: Any) -> SessionEvent:
    if isinstance(d, dict):
        return SessionEvent(
            type=d.get("type", ""),
            seq=d.get("seq", 0),
            time=d.get("time", 0),
            data=d.get("data"),
            surfaceOp=d.get("surfaceOp"),
            sourceEventSeqs=d.get("sourceEventSeqs"),
            ignorable=d.get("ignorable"),
        )
    return d  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Module-private store attachment registry
# ---------------------------------------------------------------------------

_attachments: dict[int, dict[str, Any]] = {}

SessionForkSource = Union[Session, SessionId]


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """In-memory session store."""

    def __init__(self, ctx: Any | None = None) -> None:
        self._store: dict[SessionId, dict[str, Any]] = {}
        self._counter: int = 0
        self._ctx = ctx

    def create(
        self,
        id: SessionId | None = None,
        options: CreateSessionOptions | None = None,
    ) -> Session:
        session = self.prepare(id, options)
        self._enter(session)
        self._announce(session)
        return session

    def prepare(
        self,
        id: SessionId | None = None,
        options: PrepareSessionOptions | None = None,
    ) -> Session:
        if id is None:
            while True:
                self._counter += 1
                session_id = SessionId(f"session-{self._counter}")
                if session_id not in self._store:
                    break
        else:
            session_id = id

        if session_id in self._store:
            raise ValueError(f'session "{session_id}" already exists')

        if options is not None and isinstance(options, RestoredSessionOptions):
            return Session.fromRestore(session_id, options.seed, options.meta)

        seed = None
        meta = None
        if options is not None and isinstance(options, CreateSessionOptions):
            seed = list(options.seed) if options.seed else None
            meta_obj = options.meta
            if meta_obj is not None:
                meta = SessionHeader(
                    version=SESSION_FORMAT_VERSION,
                    id=session_id,
                    createdAt=meta_obj.createdAt or _now_ms(),
                    cwd=meta_obj.cwd,
                    parentSession=meta_obj.parentSession,
                    seedLength=meta_obj.seedLength,
                    origin=meta_obj.origin,
                    delegationDepth=meta_obj.delegationDepth,
                    agentPreset=meta_obj.agentPreset,
                )

        if meta is None:
            meta = SessionHeader(
                version=SESSION_FORMAT_VERSION,
                id=session_id,
                createdAt=_now_ms(),
            )
        return Session.create(session_id, seed, meta)

    def _enter(self, session: Session) -> Callable[[], None]:
        id_ = session.id
        if id_ in self._store:
            raise ValueError(f'session "{id_}" already exists')
        entry: dict[str, Any] = {
            "id": id_,
            "session": session,
            "announced": False,
            "observers": [],
        }
        self._store[id_] = entry
        _attachments[id(session)] = entry

        def detach() -> None:
            if self._store.get(id_) is entry:
                del self._store[id_]
                _attachments.pop(id(session), None)

        return detach

    def _announce(self, session: Session) -> None:
        entry = _attachments.get(id(session))
        if entry is None or self._store.get(session.id) is not entry:
            raise ValueError(f'session "{session.id}" is not live in this store')
        if entry["announced"]:
            raise ValueError(f'session "{entry["id"]}" was already announced')
        entry["announced"] = True

    def get(self, id: SessionId) -> Session | None:
        entry = self._store.get(id)
        return entry["session"] if entry else None

    def list(self) -> list[Session]:
        return [entry["session"] for entry in self._store.values()]

    def fork(
        self,
        source: SessionForkSource,
        boundary: int | None = None,
        childSessionId: SessionId | None = None,
    ) -> Session:
        if childSessionId is not None and self.get(childSessionId) is not None:
            raise SessionForkError(
                f'session "{childSessionId}" already exists',
                "SESSION_ALREADY_EXISTS",
            )
        live_source = self._resolve_fork_source(source)
        seed = self._fork_seed(live_source, boundary)
        return self.create(
            childSessionId,
            CreateSessionOptions(
                seed=tuple(seed),
                meta=_SessionEventMeta(
                    cwd=live_source.header.cwd,
                    parentSession=live_source.id,
                    seedLength=len(seed),
                ),
            ),
        )

    def _fork_seed(
        self, session: Session, requested_boundary: int | None
    ) -> list[SessionEvent]:
        events = session.events
        if requested_boundary is not None:
            boundary = requested_boundary
        else:
            if not events:
                return []
            boundary = events[-1].seq
        if not isinstance(boundary, int) or isinstance(boundary, bool) or boundary < 0:
            raise SessionForkError(
                f'fork boundary for session "{session.id}" must be a non-negative '
                f"safe integer, got {boundary!r}",
                "INVALID_BOUNDARY",
            )
        if boundary >= len(events):
            last_seq = events[-1].seq if events else None
            raise SessionForkError(
                f"fork boundary {boundary} does not exist in session "
                f'"{session.id}" (last seq: {last_seq if last_seq is not None else "none"})',
                "INVALID_BOUNDARY",
            )
        boundary_event = events[boundary]
        if boundary_event is None or boundary_event.seq != boundary:
            raise SessionForkError(
                f"fork boundary {boundary} does not match a contiguous event seq "
                f'in session "{session.id}"',
                "INVALID_BOUNDARY",
            )
        # Check for open turn
        last_turn_boundary = None
        for event in events[: boundary + 1]:
            if event.type in ("turn/start", "turn/end"):
                last_turn_boundary = event
        if last_turn_boundary is not None and last_turn_boundary.type == "turn/start":
            turn_num = (
                last_turn_boundary.data.turn
                if hasattr(last_turn_boundary.data, "turn")
                else last_turn_boundary.data["turn"]
            )
            raise SessionForkError(
                f"fork boundary {boundary} in session \"{session.id}\" "
                f"ends inside open turn {turn_num}",
                "OPEN_TURN",
            )
        return list(events[: boundary + 1])

    def _resolve_fork_source(self, source: SessionForkSource) -> Session:
        if isinstance(source, str):
            session = self.get(source)
            if session is None:
                raise SessionForkError(f'session "{source}" not found', "SESSION_NOT_FOUND")
            return session
        live = self.get(source.id)
        if live is None:
            raise SessionForkError(f'session "{source.id}" not found', "SESSION_NOT_FOUND")
        if live is not source:
            raise SessionForkError(
                f'session "{source.id}" is not the live store instance',
                "SESSION_NOT_LIVE",
            )
        return source


# Avoid circular import for _SessionEventMeta
from lca.layer0_infra.dsh_core.session.types import _SessionEventMeta  # noqa: E402
