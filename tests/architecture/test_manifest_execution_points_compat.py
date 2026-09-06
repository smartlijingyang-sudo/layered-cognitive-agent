"""P1-18 — manifest.py EXECUTION_POINTS COMPAT freeze (ADR-0195 O1).

``lca/infrastructure/observability/spine/manifest.py`` must re-export yaml SSOT
(``SPINE_EXECUTION_POINTS``) and must not grow an inline EP tuple.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.observability.spine import manifest as manifest_mod
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "lca/infrastructure/observability/spine/manifest.py"


def test_execution_points_reexports_yaml_ssot() -> None:
    """COMPAT shim mirrors ``SPINE_EXECUTION_POINTS`` — no parallel tuple."""
    from lca_kernel.events.payloads_spine import SPINE_EXECUTION_POINTS

    assert tuple(EXECUTION_POINTS) == SPINE_EXECUTION_POINTS


def test_manifest_module_has_no_inline_execution_points_tuple() -> None:
    """P1-18: forbid resurrecting the deleted inline ``EXECUTION_POINTS`` tuple."""
    source = _MANIFEST_PATH.read_text(encoding="utf-8")
    assert "EXECUTION_POINTS: tuple[str, ...] = (" not in source
    assert "forbidden_new_usage" in source
    assert "SPINE_EXECUTION_POINTS" in source
    assert "__getattr__" in source


def test_manifest_forbids_new_bare_ep_literals() -> None:
    """New EP strings must not be added to manifest.py (yaml-only registration)."""
    source = _MANIFEST_PATH.read_text(encoding="utf-8")
    # Legacy inline tuple entries — must not reappear in COMPAT module.
    legacy_samples = (
        '"brain.think.start"',
        '"phase.act.fold.start"',
        '"spine.i17.rejected"',
    )
    offenders = [sample for sample in legacy_samples if sample in source]
    assert offenders == [], (
        "manifest.py must not contain bare EP literals; register in spine.yaml:\n"
        + "\n".join(f"  - {s}" for s in offenders)
    )


def test_manifest_exports_only_execution_points() -> None:
    assert manifest_mod.__all__ == ["EXECUTION_POINTS"]
