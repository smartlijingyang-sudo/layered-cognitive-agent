from __future__ import annotations

import pytest

from lca.contracts.harness.delegation_grant import derive_child_grant
from lca.contracts.protocols.command_envelope import CapabilityGrant


def test_child_grant_must_remain_within_parent() -> None:
    parent = CapabilityGrant("crm.read", "run", "read")

    assert derive_child_grant(parent, CapabilityGrant("crm.read", "run", "read")) == parent


@pytest.mark.parametrize(
    "requested",
    [
        CapabilityGrant("crm.write", "run", "read"),
        CapabilityGrant("crm.read", "session", "read"),
        CapabilityGrant("crm.read", "run", "write"),
    ],
)
def test_child_grant_rejects_escalation(requested: CapabilityGrant) -> None:
    with pytest.raises(PermissionError):
        derive_child_grant(CapabilityGrant("crm.read", "run", "read"), requested)
