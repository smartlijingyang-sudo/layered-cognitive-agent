"""MVA-3: RuntimeObserved plugin.inventory must not enter the journal stream.

RuntimeObserved has no ``scope`` / ``payload`` fields; inventory lives in
``output`` (production: ``record_runtime(..., output={"plugins": ...})``).
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import RuntimeObserved
from lca.layer0_infra.observability.journal.engine import RunStore


def test_plugin_inventory_event_not_appended_to_journal() -> None:
    store = RunStore(run_id="r1")
    event = RuntimeObserved(
        kind="plugin",
        operation="plugin.inventory",
        output={"plugins": ["a", "b", "c"]},
    )
    result = store.append(event)
    # MVA-3: append returns None for filtered events
    assert result is None
    # No event was added to ledger
    assert store.run_seq == 0


def test_other_runtime_observed_events_still_appended() -> None:
    """plugin.inventory is filtered; other RuntimeObserved events pass through."""
    store = RunStore(run_id="r1")
    event = RuntimeObserved(
        kind="permission",
        operation="policy.decision",
        output={"decision": "allow"},
    )
    result = store.append(event)
    assert result is not None
    assert store.run_seq == 1

    same_kind_other_op = RuntimeObserved(
        kind="plugin",
        operation="plugin.interaction",
        output={"ok": True},
    )
    other = store.append(same_kind_other_op)
    assert other is not None
    assert store.run_seq == 2


def test_plugin_inventory_filter_incremental() -> None:
    """Multiple plugin.inventory events don't pollute ledger."""
    store = RunStore(run_id="r1")
    for _ in range(10):
        store.append(
            RuntimeObserved(
                kind="plugin",
                operation="plugin.inventory",
                output={"plugins": []},
            )
        )
    assert store.run_seq == 0  # all filtered
