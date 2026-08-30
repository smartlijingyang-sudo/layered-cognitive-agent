"""Default profile must expose one independently replaceable composer per plane."""

from __future__ import annotations

import asyncio
from pathlib import Path

from lca.harness.profile.boot import boot_profile
from lca.plugins.composer.body_composer import BodyComposer
from lca.plugins.composer.brain_composer import BrainComposer
from lca.plugins.composer.perceive_composer import PerceiveComposer
from lca.plugins.composer.team_composer import TeamComposer

REPO = Path(__file__).resolve().parents[2]
WEB_APP_BUNDLE_PATH = REPO / "bundles" / "web-app.yaml"


def test_web_bundle_registers_one_entry_per_plan_composer() -> None:
    """Each graph contribution has its own profile-visible replacement seam."""

    bundle = WEB_APP_BUNDLE_PATH.read_text(encoding="utf-8")

    assert "lca-plan-sub-composers" not in bundle
    for plugin_id, module in (
        ("lca-plan-brain-composer", "lca.plugins.composer.brain_provider"),
        ("lca-plan-body-composer", "lca.plugins.composer.body_provider"),
        ("lca-plan-perceive-composer", "lca.plugins.composer.perceive_provider"),
        ("lca-plan-team-composer", "lca.plugins.composer.team_provider"),
    ):
        assert f"id: {plugin_id}" in bundle
        assert f"$module: {module}" in bundle


def test_booted_web_profile_exposes_all_plane_composers() -> None:
    """The default profile closes each graph contribution through its own provider."""

    context = asyncio.run(boot_profile("profiles/web-standard.yaml"))

    assert isinstance(context.inject("composer.brain"), BrainComposer)
    assert isinstance(context.inject("composer.body"), BodyComposer)
    assert isinstance(context.inject("composer.perceive"), PerceiveComposer)
    assert isinstance(context.inject("composer.team"), TeamComposer)
