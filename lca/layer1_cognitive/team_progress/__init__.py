"""Compat re-export — use ``lca.layer1_cognitive.member_status``.

# DEPRECATED: remove after one release cycle.
"""

from lca.layer1_cognitive.member_status import (
    InMemoryMemberStatus,
    ledger_tracking_hook,
    track_member_status_hook,
)

# Old names
DelegationLedger = InMemoryMemberStatus
progress_injection_hook = None  # removed: use MemberStatus.as_prompt_text()

__all__ = [
    "DelegationLedger",
    "InMemoryMemberStatus",
    "ledger_tracking_hook",
    "progress_injection_hook",
    "track_member_status_hook",
]
