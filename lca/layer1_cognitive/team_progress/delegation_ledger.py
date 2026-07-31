"""Compat re-export — use member_status.in_memory."""

from lca.layer1_cognitive.member_status.in_memory import InMemoryMemberStatus

DelegationLedger = InMemoryMemberStatus

__all__ = ["DelegationLedger", "InMemoryMemberStatus"]
