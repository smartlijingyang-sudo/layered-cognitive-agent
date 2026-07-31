"""Compat re-export — use ``lca.contracts.member_status.MemberStatus``.

# DEPRECATED: remove after one release cycle.
"""

from __future__ import annotations

from lca.contracts.member_status import MemberStatus

# Transitional alias — remove after one release cycle.
DelegationLedgerProtocol = MemberStatus

__all__ = ["DelegationLedgerProtocol", "MemberStatus"]
