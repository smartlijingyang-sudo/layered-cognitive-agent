"""Profile 组合器 —— 委托到 cordis.Loader.

向后兼容: ``from lca.layer4_app.profile import load_profile`` 仍然有效。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cordis.loader import load_yaml

__all__ = ["ProfileError", "ProfileLoader", "load_profile"]


class ProfileError(Exception):
    """Profile composition failure."""


class ProfileLoader:
    """Thin wrapper around cordis.Loader.load_yaml for back-compat."""

    def load_profile(self, path: Path | str) -> Any:
        """Load a profile YAML via cordis."""
        try:
            return load_yaml(path)
        except Exception as exc:
            raise ProfileError(f"failed to load profile {path}: {exc}") from exc


def load_profile(path: Path | str) -> Any:
    """Module-level convenience."""
    return ProfileLoader().load_profile(path)


def expand_profile(path: Path | str) -> Any:
    """Stub for back-compat (cordis.Loader handles expansion internally)."""
    return load_profile(path)


def compose_bundles(*paths: Path | str) -> Any:
    """Stub for back-compat (cordis.Loader handles bundle composition)."""
    import warnings
    warnings.warn("compose_bundles is deprecated; use cordis.Loader.merge_bundles", DeprecationWarning, stacklevel=2)
    return load_yaml(paths[0]) if paths else None
