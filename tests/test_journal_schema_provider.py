"""schema-v2.0.0 provider —— ADR-0096 MVA-1.

``EnvelopeV2Schema.serialize`` maps JournalRecord ``data`` → EnvelopeV2
``payload`` and ``schema: lca.journal/2`` → ``schema_version: v2.0.0``.
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    DescriptorRef,
    JournalRecord,
    RunScope,
)
from lca.plugins.providers.journal_schema.v2 import EnvelopeV2Schema


def test_v2_provider_registered_on_seam() -> None:
    """Seam setup registers EnvelopeV2Schema at version v2.0.0."""
    import asyncio

    from lca.plugins.seam_definitions.observability.journal_schema import (
        Config,
        JournalSchemaRegistry,
    )
    from lca.plugins.seam_definitions.observability.journal_schema import (
        setup as seam_setup,
    )

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    setup_fn = getattr(seam_setup, "setup", seam_setup)
    asyncio.run(setup_fn(FakeCtx(), Config()))
    registry = provided["journal_schemas"]
    assert isinstance(registry, JournalSchemaRegistry)
    schema = registry.get("v2.0.0")
    assert isinstance(schema, EnvelopeV2Schema)
    assert schema.version == "v2.0.0"


def test_v2_provider_serializes_to_envelope() -> None:
    record = JournalRecord(
        event_id="abc",
        schema="lca.journal/2",
        run_id="r",
        run_seq=1,
        plan_ref="",
        scope=RunScope(trace_id="t", run_id="r"),
        data={"foo": "bar"},
        descriptor=DescriptorRef(type="StepTextDelta", payload_schema_version=1),
        occurred_at=0.0,
    )
    schema = EnvelopeV2Schema()
    env = schema.serialize(record)
    assert env["schema_version"] == "v2.0.0"
    assert env["payload"] == {"foo": "bar"}
