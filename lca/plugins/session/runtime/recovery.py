# COMPAT(owner: ADR-0195 P4-S04, from: lca.plugins.session.runtime.recovery,
# to: lca.session.recovery,
# delete_when: rg 'plugins\.session\.runtime\.recovery' lca/ tests/ = 0 except COMPAT,
# forbidden_new_usage: true)
"""Deprecated shim — use :mod:`lca.session.recovery`."""

from __future__ import annotations

from lca.session.recovery import SessionRecoveryError, recover_live_agent

__all__ = ["SessionRecoveryError", "recover_live_agent"]
