"""spine_reflector_composio publisher tests."""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.observability.composio_ep_closure import COMPOSIO_CONNECTION_CREATED


def test_emit_composio_connection_created(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_composio.plugin import (
        emit_composio_domain_event,
    )

    ref = emit_composio_domain_event(
        execution_point=COMPOSIO_CONNECTION_CREATED,
        payload={
            "identifier": "google-drive",
            "app_slug": "GOOGLEDRIVE",
            "status": "PENDING",
            "connected_account_id": "ca_1",
            "user_id": "default",
        },
    )
    assert ref is not None
    assert ref.category == "spine.composio.connection.created"


def test_emit_without_session(caplog: pytest.LogCaptureFixture) -> None:
    from lca.plugins.events.publishers.spine_reflector_composio.plugin import (
        emit_composio_domain_event,
    )

    ref = emit_composio_domain_event(
        execution_point=COMPOSIO_CONNECTION_CREATED,
        payload={"identifier": "slack"},
    )
    assert ref is None
