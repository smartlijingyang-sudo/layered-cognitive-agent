"""Tests for real user home detection and path locator (ADR-0195 / Path Governance)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

from lca.infrastructure.path import (
    expand_user_path,
    get_lca_home,
    get_real_user_home,
)


def test_get_real_user_home_honors_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_USER_HOME", "/custom/user/home")
    assert get_real_user_home() == Path("/custom/user/home")


def test_get_real_user_home_rejects_agy_sandbox_and_uses_pwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LCA_USER_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/lichao/.agy-accounts/b")

    mock_pwd = MagicMock()
    mock_pwd.getpwuid.return_value.pw_dir = "/home/lichao"
    monkeypatch.setattr("pwd.getpwuid", mock_pwd.getpwuid)

    home = get_real_user_home()
    assert home == Path("/home/lichao")
    assert ".agy-accounts" not in str(home)


def test_get_real_user_home_fallback_when_pwd_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_USER_HOME", raising=False)
    monkeypatch.setenv("HOME", "/workspace/fallback-home")

    def _raise_key_error(_uid: int):
        raise KeyError("user not found")

    monkeypatch.setattr("pwd.getpwuid", _raise_key_error)

    home = get_real_user_home()
    assert home == Path("/workspace/fallback-home")


def test_get_lca_home_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_HOME", "/custom/lca/root")
    assert get_lca_home() == Path("/custom/lca/root")


def test_get_lca_home_defaults_to_real_user_home_dot_lca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_HOME", raising=False)
    monkeypatch.setenv("LCA_USER_HOME", "/home/testuser")
    assert get_lca_home() == Path("/home/testuser/.lca")


def test_expand_user_path_expands_tilde_to_real_user_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_HOME", raising=False)
    monkeypatch.setenv("LCA_USER_HOME", "/home/testuser")

    assert expand_user_path("~") == Path("/home/testuser")
    assert expand_user_path("~/documents") == Path("/home/testuser/documents")
    assert expand_user_path("~/.lca/assistants") == Path("/home/testuser/.lca/assistants")


def test_expand_user_path_honors_lca_home_for_dot_lca_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LCA_HOME", "/mnt/shared/lca")
    monkeypatch.setenv("LCA_USER_HOME", "/home/testuser")

    assert expand_user_path("~/.lca") == Path("/mnt/shared/lca")
    assert expand_user_path("~/.lca/assistants") == Path("/mnt/shared/lca/assistants")
    # Non .lca path still resolves under user home
    assert expand_user_path("~/other") == Path("/home/testuser/other")


def test_expand_user_path_preserves_absolute_and_relative_paths() -> None:
    assert expand_user_path("/opt/data") == Path("/opt/data")
    assert expand_user_path("relative/path") == Path("relative/path")
