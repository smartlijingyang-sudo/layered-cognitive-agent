"""Onlyboxes guest layout instance.

Callers read ``ONLYBOXES`` (or a ``GuestLayout`` they were given).
Do not import ``SANDBOX_MOUNT_ROOT`` outside ``GuestLayout.onlyboxes()``.
"""

from __future__ import annotations

from lca.contracts.models.core.guest_layout import GuestLayout, join_under, outputs_under

ONLYBOXES: GuestLayout = GuestLayout.onlyboxes()

__all__ = ["ONLYBOXES", "GuestLayout", "join_under", "outputs_under"]
