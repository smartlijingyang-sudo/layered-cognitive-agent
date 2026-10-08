"""RA-055: activate_skill refuses retired / unverified packages.

Pins the closed ungated-activate path. Content injection is gated by:
1. ``package.retired`` → refuse (mirrors the run_skill_script/exec path).
2. Home manifest ``artifact_state`` (when the store exposes it via the
   duck-typed ``package_artifact_state`` seam) → must satisfy
   ``is_activatable_state``, the SAME predicate
   ``AssistantSkillOverlay.activate`` uses.

A store without the seam (e.g. the global disk store) skips check 2 —
that path is covered by test_skill_tool_events.py's ``_Store``, which
has no such method.
"""

from __future__ import annotations

import asyncio

from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
)
from lca.infrastructure.skills.activation.scope import activated_skills_scope
from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool


def _package(skill_id: str, *, retired: bool = False) -> SkillPackage:
    return SkillPackage(
        skill_id=skill_id,
        name=skill_id,
        summary="",
        content="# test skill",
        resource_paths=(),
        source_url="test",
        content_hash="sha256:deadbeef",
        retired=retired,
    )


class _GatingStore:
    """Fake store exposing the RA-055 manifest-state seam."""

    def __init__(self, packages: dict[str, SkillPackage], states: dict[str, str]) -> None:
        self._packages = packages
        self._states = states

    def get(self, skill_id: str) -> SkillPackage:
        try:
            return self._packages[skill_id]
        except KeyError:
            raise SkillNotFoundError(skill_id) from None

    def list_installed(self) -> tuple:
        return ()

    def package_artifact_state(self, skill_id: str) -> str | None:
        return self._states.get(skill_id)


def _run(tool: SkillActivateTool, skill_id: str):
    # Fresh budget per test: other test modules activate real skills in the
    # same process and the per-run cap (8) is a process-wide ContextVar.
    with activated_skills_scope(()):
        return asyncio.run(tool.execute({"skill_id": skill_id}))


def test_retired_package_is_refused() -> None:
    store = _GatingStore({"s-ret": _package("s-ret", retired=True)}, {"s-ret": "verified"})
    obs = _run(SkillActivateTool(store), "s-ret")
    assert obs.success is False
    assert "退役" in (obs.error or "")


def test_draft_manifest_state_is_refused() -> None:
    store = _GatingStore({"s-draft": _package("s-draft")}, {"s-draft": "draft"})
    obs = _run(SkillActivateTool(store), "s-draft")
    assert obs.success is False
    assert "0067" in (obs.error or "")


def test_verified_package_is_allowed() -> None:
    store = _GatingStore({"s-ok": _package("s-ok")}, {"s-ok": "verified"})
    obs = _run(SkillActivateTool(store), "s-ok")
    assert obs.success is True, obs.error


def test_active_package_is_allowed() -> None:
    store = _GatingStore({"s-active": _package("s-active")}, {"s-active": "active"})
    obs = _run(SkillActivateTool(store), "s-active")
    assert obs.success is True, obs.error


def test_unknown_manifest_state_skips_gate() -> None:
    """Stores without the seam (global disk store) skip the state gate."""

    class _NoSeamStore:
        def get(self, skill_id: str) -> SkillPackage:
            return _package("s-global")

        def list_installed(self) -> tuple:
            return ()

    obs = _run(SkillActivateTool(_NoSeamStore()), "s-global")
    assert obs.success is True, obs.error
