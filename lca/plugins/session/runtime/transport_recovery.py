# COMPAT(owner: ADR-0195 P4-S04, from: lca.plugins.session.runtime.transport_recovery,
# to: lca.session.recovery,
# delete_when: rg 'plugins\.session\.runtime\.transport_recovery' lca/ tests/ = 0,
# forbidden_new_usage: true)
"""Deprecated shim — use :mod:`lca.session.recovery`."""

from __future__ import annotations

from lca.session.recovery import (
    append_approval_resolved_if_pending,
    assert_resume_allowed,
    recovery_from_events,
    sync_run_status_from_recovery,
)

__all__ = [
    "append_approval_resolved_if_pending",
    "assert_resume_allowed",
    "recovery_from_events",
    "sync_run_status_from_recovery",
]
