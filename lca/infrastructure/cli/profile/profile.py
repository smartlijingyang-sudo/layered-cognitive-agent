"""Gateway profile selection policy.

This module owns only the policy for selecting a harness profile. It deliberately
has no Starlette or runtime dependencies, which makes profile precedence testable
without constructing an application or booting a profile.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DEFAULT_PROFILE = "profiles/web-standard.yaml"


def resolve_profile_path(
    profile_path: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    working_directory: Path | None = None,
) -> str | None:
    """Resolve an explicit, environment, or repository-local profile path.

    Precedence is intentionally explicit: a caller-provided path wins over
    ``LCA_PROFILE``; the environment wins over the local default. The filesystem
    check is limited to the final fallback so callers can inject a working
    directory in tests.
    """
    if profile_path is not None:
        return profile_path

    environment = os.environ if environ is None else environ
    env_profile = environment.get("LCA_PROFILE")
    if env_profile is not None:
        return env_profile

    root = Path.cwd() if working_directory is None else working_directory
    if (root / DEFAULT_PROFILE).exists():
        return DEFAULT_PROFILE
    return None


__all__ = ["DEFAULT_PROFILE", "resolve_profile_path"]
