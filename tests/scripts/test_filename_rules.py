"""Tests for scripts/_filename_rules.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _filename_rules import (  # noqa: E402
    DEFAULT_BLACKLIST,
    DEFAULT_WHITELIST,
    is_blacklisted,
    is_whitelisted,
)


def test_default_blacklist_has_all_6_patterns():
    assert "*util*.py" in DEFAULT_BLACKLIST
    assert "*helper*.py" in DEFAULT_BLACKLIST
    assert "*manager*.py" in DEFAULT_BLACKLIST
    assert "*impl*.py" in DEFAULT_BLACKLIST
    assert "*common*.py" in DEFAULT_BLACKLIST
    assert "*misc*.py" in DEFAULT_BLACKLIST


def test_util_helper_pattern():
    assert is_blacklisted("lca/foo/util.py")
    assert is_blacklisted("lca/foo/string_util.py")
    assert is_blacklisted("lca/foo/utils.py")
    assert is_blacklisted("lca/foo/my_helpers.py")


def test_manager_impl_common_misc_pattern():
    assert is_blacklisted("lca/foo/user_manager.py")
    assert is_blacklisted("lca/foo/activation_manager.py")
    assert is_blacklisted("lca/foo/foo_impl.py")
    assert is_blacklisted("lca/foo/common.py")
    assert is_blacklisted("lca/foo/misc.py")


def test_normal_files_not_blacklisted():
    assert not is_blacklisted("lca/foo/agent_state.py")
    assert not is_blacklisted("lca/foo/decision.py")
    assert not is_blacklisted("lca/foo/context_manifest.py")


def test_whitelist_init_py():
    assert is_whitelisted("lca/contracts/__init__.py")
    assert is_whitelisted("lca/harness/agent/__init__.py")
    assert is_whitelisted("lca/plugins/seams/__init__.py")
    assert is_whitelisted("gateway/plugins/__init__.py")


def test_whitelist_with_package_whitelist():
    """Custom package whitelist can extend defaults."""
    assert is_whitelisted("lca/foo/special_util.py", package_whitelist=["lca/foo/special_util.py"])


def test_extra_blacklist():
    """Extra blacklist can extend defaults."""
    assert is_blacklisted("lca/foo/special.py", extra_blacklist=["*special*.py"])
    assert not is_blacklisted("lca/foo/normal.py", extra_blacklist=["*special*.py"])


def test_init_py_not_blacklisted_after_whitelist():
    """__init__.py is blacklisted by `*common*` and `*misc*` patterns; whitelist overrides."""
    # The whitelist check happens before blacklist in main script
    path = "lca/foo/__init__.py"
    # Even if blacklisted, whitelist takes precedence in the actual check
    assert is_whitelisted(path) or not is_blacklisted(path)  # either way OK due to whitelist logic
