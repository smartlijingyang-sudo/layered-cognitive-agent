"""spine_reflector_skill publisher tests."""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.skill_meta_ep_closure import SKILL_PACKAGE_INSTALLED


def test_emit_skill_package_installed(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_skill.plugin import emit_skill_meta_event

    ref = emit_skill_meta_event(
        execution_point=SKILL_PACKAGE_INSTALLED,
        payload={"skill_id": "demo-skill", "content_hash": "sha256:abc"},
    )
    assert ref is not None
    assert ref.category == "spine.skill.package.installed"
