"""RA-139 pin: the two verbatim ``_required_grant`` probes converged onto the
shared ``required_grant_of`` access seam.

One Tool object yields the same grant string through both former call sites
(now both delegate to the one seam), and no private twin remains in either
module.
"""

from __future__ import annotations

from lca.infrastructure.runtime_plane import access
from lca.infrastructure.runtime_plane.access import required_grant_of
from lca.infrastructure.tools.assistant import filter as filter_module
from lca.nodes.act.authorize import authorize as authorize_module


class _GrantTool:
    required_grant = "  ops.read  "


class _NoGrantTool:
    pass


class _NoneGrantTool:
    required_grant = None


def test_required_grant_of_reads_declared_grant_and_strips() -> None:
    assert required_grant_of(_GrantTool()) == "ops.read"


def test_required_grant_of_empty_when_undeclared() -> None:
    assert required_grant_of(_NoGrantTool()) == ""


def test_required_grant_of_empty_when_none() -> None:
    assert required_grant_of(_NoneGrantTool()) == ""


def test_former_twins_converged_on_shared_seam() -> None:
    """Both former call sites use the one shared seam; no private twin remains."""
    assert not hasattr(filter_module, "_required_grant")
    assert not hasattr(authorize_module, "_required_grant_of")
    assert filter_module.required_grant_of is access.required_grant_of
    assert authorize_module.required_grant_of is access.required_grant_of
