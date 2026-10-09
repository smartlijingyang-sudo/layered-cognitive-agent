"""RA-093: per-kind payload-type contract tests for ContextManifest.payload_of.

The kind->payload-type knowledge lives in one place (KIND_PAYLOAD_TYPES on
the contract side); the cognition helpers converge onto payload_of.
"""

from lca.cognition.brain.sections.types import (
    ManifestArtifacts,
    ManifestClock,
    ManifestSubtasks,
    artifacts_from_manifest,
    clock_from_manifest,
    memory_records_from_manifest,
    subtasks_from_manifest,
)
from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import (
    KIND_PAYLOAD_TYPES,
    ContextItem,
    ContextManifest,
    ItemKind,
)


def _manifest(*items: ContextItem) -> ContextManifest:
    return ContextManifest(items=tuple(items))


def _item(kind: ItemKind, payload: object) -> ContextItem:
    return ContextItem(kind=kind, payload=payload, provenance="test")


def test_kind_payload_types_covers_every_item_kind():
    # one pairing point: every closed-set kind has a declared payload shape
    kinds = (
        "clock",
        "workspace_artifacts",
        "workspace_instructions",
        "skill_catalog",
        "inbox_facts",
        "team_inbox",
        "policy_fact",
        "memory",
        "subtasks",
    )
    for kind in kinds:
        assert KIND_PAYLOAD_TYPES[kind], f"kind {kind} lacks a payload-type entry"


def test_payload_of_filters_non_conforming_payloads():
    m = _manifest(
        _item("clock", "2026-10-09"),
        _item("clock", {"not": "a string"}),  # legacy producer shape -> filtered
        _item("memory", "not a list either"),
    )
    assert m.payload_of("clock") == ["2026-10-09"]
    assert m.payload_of("memory") == []
    assert m.payload_of("policy_fact") == []


def test_clock_from_manifest_converges():
    m = _manifest(_item("clock", "2026-10-09 星期五"))
    got = clock_from_manifest(m)
    assert got == ManifestClock(text="2026-10-09 星期五")
    assert clock_from_manifest(None) is None  # unbound manifest -> empty
    assert clock_from_manifest(_manifest(_item("clock", 123))) is None


def test_subtasks_from_manifest_converges():
    m = _manifest(_item("subtasks", ["a", 1]))
    got = subtasks_from_manifest(m)
    assert got == ManifestSubtasks(items=("a", "1"))
    assert subtasks_from_manifest(None) == ManifestSubtasks(items=())


def test_artifacts_from_manifest_converges():
    m = _manifest(
        _item("workspace_artifacts", [{"path": "a.md"}, "not-a-mapping"]),
        _item("workspace_artifacts", {"name": "legacy-dict-shape"}),  # filtered
    )
    got = artifacts_from_manifest(m)
    assert got == ManifestArtifacts(items=({"path": "a.md"},))
    assert artifacts_from_manifest(None) == ManifestArtifacts(items=())


def test_memory_records_from_manifest_converges():
    record = MemoryRecord(
        record_id="r1", content="hi", memory_type=MemoryLayer.EPISODIC, importance=0.5
    )
    m = _manifest(
        _item("memory", [record, "junk"]),
        _item("memory", "legacy-string-shape"),  # filtered
    )
    got = memory_records_from_manifest(m)
    assert got == (record,)
    assert memory_records_from_manifest(None) == ()
