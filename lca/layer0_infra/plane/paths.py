"""Kind-agnostic path derivation. Re-exports the contracts join rule.

Machine ``PlaneRef.outputs_dir`` is ``outputs_under(root)``.
Sandbox guest disks use ``GuestLayout``, not these helpers.
"""

from __future__ import annotations

from lca.contracts.models.core.guest_layout import join_under, outputs_under

__all__ = ["join_under", "outputs_under"]
