"""Composio EP closure regression tests."""

from __future__ import annotations

from lca.contracts.observability.composio_ep_closure import (
    COMPOSIO_EVENT_POINTS,
    all_composio_event_descriptors,
)
from lca.contracts.observability.cordis_event_table import lookup_cordis_name


def test_composio_closure_count() -> None:
    assert len(COMPOSIO_EVENT_POINTS) == 11
    assert len(set(COMPOSIO_EVENT_POINTS)) == 11


def test_composio_descriptors_match_closure() -> None:
    descriptors = all_composio_event_descriptors()
    assert {d.type_name for d in descriptors} == set(COMPOSIO_EVENT_POINTS)


def test_composio_cordis_table() -> None:
    for ep in COMPOSIO_EVENT_POINTS:
        entry = lookup_cordis_name(ep)
        assert entry.cordis_name == f"agent.{ep}"
