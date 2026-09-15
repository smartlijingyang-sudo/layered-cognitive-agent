"""Directory-ancestor admission in ``_profile_explicitly_admits``.

A plugin that lives under the profile's directory tree is admitted even when
neither path string contains the other. That branch used two
``Path.relative_to`` calls wrapped in ``except ValueError: pass`` and is now
``Path.is_relative_to``, so the accepted and rejected shapes are pinned here.

The comparison is path-object based after ``Path(plugin_source).resolve()``, so a
relative profile path never matches an absolute plugin source — the last two
cases pin that asymmetry as current behavior rather than intent.
"""

from __future__ import annotations

from pathlib import Path

from lca.harness.profile.resolve.resolve import _profile_explicitly_admits


def _admits(profile: str, plugin_source: str) -> bool:
    return _profile_explicitly_admits(
        profile_path_str=profile,
        profile_path_obj=Path(profile),
        plugin_source=plugin_source,
        discovered_at="",
    )


def test_plugin_under_the_profile_directory_is_admitted() -> None:
    assert _admits("/abs/profiles/web-standard.yaml", "/abs/profiles/plugins/foo.py") is True


def test_deeper_nested_plugin_is_admitted() -> None:
    assert _admits("/abs/profiles/web-standard.yaml", "/abs/profiles/bundles/x/p.py") is True


def test_plugin_outside_the_profile_tree_is_not_admitted() -> None:
    assert _admits("/abs/profiles/web-standard.yaml", "/abs/other/p.py") is False


def test_profile_under_plugin_parent_is_admitted() -> None:
    """The reverse ancestor direction counts too."""
    assert _admits("/abs/profiles/sub/a.yaml", "/abs/profiles/bundle.py") is True


def test_identical_paths_are_admitted() -> None:
    assert _admits("/abs/profiles/a.yaml", "/abs/profiles/a.yaml") is True


def test_relative_profile_does_not_match_absolute_plugin_source() -> None:
    assert _admits("/abs/profiles/web-standard.yaml", "profiles/plugins/foo.py") is False


def test_both_relative_paths_do_not_reach_the_directory_branch() -> None:
    assert _admits("profiles/a.yaml", "profiles/plugins/foo.py") is False


def test_empty_profile_path_never_admits() -> None:
    assert _admits("", "profiles/plugins/foo.py") is False
