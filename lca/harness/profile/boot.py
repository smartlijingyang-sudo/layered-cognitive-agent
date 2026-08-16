"""Boot a harness plugin tree from a profile YAML."""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.plugin.include._profile import ProfileLoader
from lca.layer0_infra.plugin.loader._entry import BootedTree
from lca.layer0_infra.plugin.loader._loader import Loader


async def boot_profile(
    profile_path: Path | str,
    *,
    check_seam_completeness: bool = True,
) -> BootedTree:
    """Load profile YAML → resolve modules → Loader.reconcile.

    This is the production composition entry point that replaces
    ``boot_capabilities()`` for profile-driven deployments.
    """
    path = Path(profile_path)
    entries = ProfileLoader().load_profile(path)
    loader = Loader(check_seam_completeness=check_seam_completeness)
    return await loader.load(entries)
