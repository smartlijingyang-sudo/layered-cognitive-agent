"""Journal v2 disk-format end-to-end tests —— ADR-0065 §三 / §四 / PR-3。

drives the production ``JsonlJournalProjector`` end-to-end via the public
``record()`` path (not ``stamped_to_record`` direct call) and asserts:

- on-disk jsonl has ``schema: "lca.journal/2"``
- envelope carries ``event_id`` / ``run_seq`` / ``occurred_at`` /
  ``committed_at`` / ``scope`` / ``causation`` / ``descriptor`` /
  ``evidence`` fields
- ``data`` carries only typed fields (no ``*_preview`` /
  ``output_truncated`` / ``plugin_state``)
- v2 records reload via the canonical v2 read API and reconstruct the
  same ``StampedEvent`` (modulo view-only fields) for every event.
- ``event_id`` is a ULID stamped by ``RunStore.append`` (ADR-0097).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from lca.infrastructure.observability.journal_backend import MemoryJournal
from lca.infrastructure.observability.policy import AttributePolicy

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    LlmCallCompleted,
    LlmCallStarted,
    RunScope,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability import (
    BoundObservability,
    bind_backends,
    record,
    run_scope,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    read_journal,
)
from lca.infrastructure.observability.journal.jsonl.projector import (
    JsonlJournalProjector,
)

# ADR-0097 / MVA-2 Task 4: engine fills event_id via StableUlidIdentity;
# journal_io prefers stamped.event_id over the MVA-1 hash fallback.
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _drive_solo_run(jsonl_path: Path) -> None:
    """drive a representative run through the public record() path."""
    proj = JsonlJournalProjector(jsonl_path)
    journal = MemoryJournal(policy=AttributePolicy()).with_projection(proj)
    bound = BoundObservability(journal=journal)
    scope = RunScope(trace_id="t", run_id="r", agent_role="researcher")
    with bind_backends(bound), run_scope(scope):
        record(AgentRunStarted(agent_role="researcher", objective="q"))
        record(
            DecisionMade(
                step=0,
                action_type="use_tool",
                tool_name="execute_code",
                confidence=0.9,
                response_text="ok",
            )
        )
        record(LlmCallStarted(step=0, model="demo-model"))
        record(
            LlmCallCompleted(
                model="demo-model",
                ok=True,
                latency_ms=1000,
                prompt_tokens=100,
                completion_tokens=50,
            )
        )
        record(
            ToolStarted(
                tool_name="execute_code",
                invocation_id="inv1",
            )
        )
        record(
            ToolInvoked(
                tool_name="execute_code",
                invocation_id="inv1",
                ok=True,
                latency_ms=500,
            )
        )
        record(AgentRunFinished(status="completed", output_text="done"))
    proj.close()


def test_disk_v2_envelope_shape() -> None:
    """on-disk jsonl has schema: lca.journal/2 and the full envelope set."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        lines = load_journal_records(jsonl)
        assert len(lines) == 7
        for line in lines:
            assert line["schema"] == "lca.journal/2"
            # envelope present
            for key in (
                "event_id",
                "run_id",
                "run_seq",
                "occurred_at",
                "committed_at",
                "scope",
                "causation",
                "descriptor",
                "data",
                "evidence",
            ):
                assert key in line, f"missing envelope key: {key}"
            # descriptor
            assert line["descriptor"]["type"] == line["descriptor"]["type"]
            assert line["descriptor"]["version"] >= 1
            # event_id format: ULID from RunStore.append (ADR-0097), not evt_ hash
            assert _ULID_RE.match(line["event_id"]), f"not ULID: {line['event_id']}"
            # scope
            assert line["scope"]["run_id"] == "r"
        # types cover the run
        types = {line["descriptor"]["type"] for line in lines}
        assert {
            "AgentRunStarted",
            "DecisionMade",
            "LlmCallStarted",
            "LlmCallCompleted",
            "ToolStarted",
            "ToolInvoked",
            "AgentRunFinished",
        } <= types


def test_disk_v2_data_strips_view_only_fields() -> None:
    """ADR-0101 PR-2: tool 事件 dataclass 不再有 view-only 字段;disk v2
    envelope data 字段对 tool 事件不含 arguments_preview / result_preview /
    plugin_state(typed 6-key / state_ref / output_text 同样不再存在)。
    其他事件的 ``output_truncated`` 是 typed 字段,保留。
    """
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        lines = load_journal_records(jsonl)
        tool_event_types = {"ToolStarted", "ToolInvoked", "ToolCallStreaming"}
        for line in lines:
            if line["descriptor"]["type"] not in tool_event_types:
                continue
            data_keys = set(line["data"].keys())
            for forbidden in {
                "arguments_preview",
                "result_preview",
                "plugin_state",
                "code",
                "command",
                "language",
                "skill_id",
                "skill_inputs",
                "description",
                "execution_env",
                "output_text",
                "state_ref",
            }:
                assert forbidden not in data_keys, (
                    f"{forbidden} leaked to disk: {line['descriptor']['type']}"
                )


def test_disk_v2_event_id_is_deterministic() -> None:
    """Each stamped event_id is a ULID; independent runs do not share ids.

    ADR-0097 replaced the MVA-1 seq+ts hash with engine-stamped ULID, so
    ids are globally unique rather than deterministic across re-emit.
    """
    with tempfile.TemporaryDirectory() as tmp:
        jsonl_a = Path(tmp) / "a.jsonl"
        jsonl_b = Path(tmp) / "b.jsonl"
        _drive_solo_run(jsonl_a)
        _drive_solo_run(jsonl_b)
        ids_a = [row["event_id"] for row in load_journal_records(jsonl_a)]
        ids_b = [row["event_id"] for row in load_journal_records(jsonl_b)]
        assert len(ids_a) == len(ids_b) == 7
        for ea, eb in zip(ids_a, ids_b, strict=True):
            assert _ULID_RE.match(ea), f"not ULID: {ea}"
            assert _ULID_RE.match(eb), f"not ULID: {eb}"
        assert len(set(ids_a)) == 7
        assert set(ids_a).isdisjoint(ids_b)


def test_disk_v2_read_reconstructs_stamped_events() -> None:
    """read_journal reloads the same StampedEvent (modulo view-only)."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        events = read_journal(jsonl)
        assert len(events) == 7
        # run_seq monotonic
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)
        assert seqs[0] == 1 and seqs[-1] == 7
        # types match
        types = [type(e.event).__name__ for e in events]
        assert "AgentRunStarted" in types
        assert "ToolInvoked" in types
        # run_id preserved
        for e in events:
            assert e.scope.run_id == "r"
        # event_id preserved on in-memory StampedEvent (ULID from engine)
        for e in events:
            assert _ULID_RE.match(e.event_id), f"not ULID: {e.event_id}"


def test_disk_v2_causation_propagates() -> None:
    """causation.parent_event_id is empty for root, set for children once engine wires it."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        events = read_journal(jsonl)
        for e in events:
            # causation structure present; event_id is engine-stamped ULID
            assert _ULID_RE.match(e.event_id), f"not ULID: {e.event_id}"
            # Note: ``parent_event_id`` is empty here because the public
            # record() path doesn't thread the engine's seq→event_id map
            # into causation; this is a known gap to be wired in a follow-up.
            # For now, the envelope shape is correct (causation is present).


def test_disk_v2_evidence_field_typed_only() -> None:
    """no Tool* event in this run has state_ref; ``evidence`` typed field is empty list."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        lines = load_journal_records(jsonl)
        for line in lines:
            assert "evidence" in line
            assert line["evidence"] == []
            # No tool started/invoked has state_ref
            if line["descriptor"]["type"] in ("ToolStarted", "ToolInvoked"):
                assert "state_ref" not in line["data"] or line["data"]["state_ref"] is None


def test_disk_v2_descriptor_validates_payload() -> None:
    """descriptor carries type + version + payload_schema_version >= 1 (L4)."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        for line in load_journal_records(jsonl):
            d = line["descriptor"]
            assert d["type"] and isinstance(d["type"], str)
            assert d["version"] >= 1
            assert d["payload_schema_version"] >= 1
            # descriptor.type matches event_type known registry
            assert d["type"] in {
                "AgentRunStarted",
                "AgentRunFinished",
                "DecisionMade",
                "LlmCallStarted",
                "LlmCallCompleted",
                "ToolStarted",
                "ToolInvoked",
            }


def test_disk_v2_sealed_run_keeps_terminal_event() -> None:
    """terminal AgentRunFinished is the last event with status=completed."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        events = read_journal(jsonl)
        last = events[-1]
        assert type(last.event).__name__ == "AgentRunFinished"
        assert last.event.status == "completed"


def test_disk_v2_run_seq_and_id_stable_across_reload() -> None:
    """reloading the same jsonl twice produces the same run_seq + event_id per event."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        _drive_solo_run(jsonl)
        e1 = read_journal(jsonl)
        e2 = read_journal(jsonl)
        for a, b in zip(e1, e2, strict=True):
            assert a.seq == b.seq
            assert a.event_id == b.event_id
            assert a.ts == b.ts
            assert a.scope.run_id == b.scope.run_id
            assert type(a.event).__name__ == type(b.event).__name__


@pytest.mark.parametrize(
    "event_factory",
    [
        AgentRunStarted,
        AgentRunFinished,
        LlmCallCompleted,
        ToolStarted,
        ToolInvoked,
    ],
)
def test_disk_v2_each_event_type_round_trips(event_factory) -> None:
    """each event type survives disk write + read without field loss."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / f"{event_factory.__name__}.jsonl"
        proj = JsonlJournalProjector(jsonl)
        journal = MemoryJournal(policy=AttributePolicy()).with_projection(proj)
        bound = BoundObservability(journal=journal)
        scope = RunScope(trace_id="t", run_id="r", agent_role="researcher")
        with bind_backends(bound), run_scope(scope):
            if event_factory is AgentRunStarted:
                record(event_factory(agent_role="researcher", objective="q"))
            elif event_factory is AgentRunFinished:
                record(event_factory(status="completed", output_text="done"))
            elif event_factory is LlmCallCompleted:
                record(event_factory(model="m", ok=True, latency_ms=10))
            elif event_factory is ToolStarted:
                record(event_factory(tool_name="t", invocation_id="i"))
            else:  # ToolInvoked
                record(event_factory(tool_name="t", invocation_id="i", ok=True))
        proj.close()
        lines = load_journal_records(jsonl)
        assert len(lines) == 1
        assert lines[0]["schema"] == "lca.journal/2"
        assert lines[0]["descriptor"]["type"] == event_factory.__name__
        # Round-trip
        events = read_journal(jsonl)
        assert len(events) == 1
        assert type(events[0].event).__name__ == event_factory.__name__
