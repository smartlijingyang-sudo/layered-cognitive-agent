"""K7 facade tests — load_layered_env + EnvSnapshot.

Covers the four rules from ADR-0117 §决定 4:

1. ``.env`` overrides bootstrap names already in ambient.
2. ``.env`` introduces keys matching BOOTSTRAP_PREFIXES.
3. ``BOOTSTRAP_FORBIDDEN`` keys are always blocked.
4. Unknown keys blocked unless ``allow_unknown=True``.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from lca_kernel.env import EnvSnapshot, load_layered_env
from lca_kernel.errors import KernelError


def _write_dotenv(path: Path, content: str) -> None:
    path.write_text(content)


def test_load_layered_env_returns_frozen_snapshot(tmp_path: Path) -> None:
    """load_layered_env returns an immutable EnvSnapshot dataclass."""
    _write_dotenv(tmp_path / ".env", "LCA_TEST_KEY=hello\nPATH=/custom\n")
    snapshot = load_layered_env("test-bin", tmp_path, allow_unknown=True)
    assert isinstance(snapshot, EnvSnapshot)
    assert isinstance(snapshot.allowed_keys, frozenset)
    assert isinstance(snapshot.blocked_keys, frozenset)


def test_load_layered_env_fail_loud_default(tmp_path: Path) -> None:
    """Default behaviour rejects unknown env keys in .env."""
    _write_dotenv(tmp_path / ".env", "MYSTERY_KEY=value\n")
    with pytest.raises(KernelError) as excinfo:
        load_layered_env("test-bin", tmp_path)
    assert "MYSTERY_KEY" in str(excinfo.value)
    assert "blocked env keys" in str(excinfo.value)


def test_load_layered_env_allow_unknown(tmp_path: Path) -> None:
    """allow_unknown=True suppresses the fail-loud error."""
    _write_dotenv(tmp_path / ".env", "MYSTERY_KEY=value\n")
    snapshot = load_layered_env("test-bin", tmp_path, allow_unknown=True)
    # The blocked set still records the key for diagnostics.
    assert "MYSTERY_KEY" in snapshot.blocked_keys


def test_load_layered_env_blocks_lca_profile(tmp_path: Path) -> None:
    """LCA_PROFILE is forbidden even with allow_unknown=False (D5 lock)."""
    _write_dotenv(tmp_path / ".env", "LCA_PROFILE=dev\n")
    with pytest.raises(KernelError) as excinfo:
        load_layered_env("test-bin", tmp_path)
    assert "LCA_PROFILE" in str(excinfo.value)


def test_load_layered_env_allows_lca_prefix_keys(tmp_path: Path) -> None:
    """LCA_ prefix keys not in ambient are allowed."""
    _write_dotenv(tmp_path / ".env", "LCA_RUN_ID=abc123\n")
    snapshot = load_layered_env("test-bin", tmp_path)
    assert "LCA_RUN_ID" in snapshot.allowed_keys
    assert snapshot.dotenv["LCA_RUN_ID"] == "abc123"


def test_load_layered_env_missing_dotenv_returns_empty(tmp_path: Path) -> None:
    """Missing .env file → ambient-only snapshot."""
    snapshot = load_layered_env("test-bin", tmp_path)
    assert snapshot.dotenv == MappingProxyType({})
    assert snapshot.blocked_keys == frozenset()


def test_load_layered_env_blocks_bootstrap_name_not_in_ambient(tmp_path: Path) -> None:
    """BOOTSTRAP_NAMES key absent from ambient → blocked."""
    _write_dotenv(tmp_path / ".env", "SSL_CERT_FILE=/etc/ssl/ca.pem\n")
    with pytest.raises(KernelError) as excinfo:
        load_layered_env("test-bin", tmp_path)
    assert "SSL_CERT_FILE" in str(excinfo.value)


def test_load_layered_env_skips_comments_and_blanks(tmp_path: Path) -> None:
    """Reader tolerates # comments and blank lines."""
    _write_dotenv(
        tmp_path / ".env",
        "# This is a comment\n\nLCA_TEST=v\n   \n# more comments\n",
    )
    snapshot = load_layered_env("test-bin", tmp_path)
    assert snapshot.dotenv.get("LCA_TEST") == "v"


def test_load_layered_env_default_dir_is_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``dir=None`` resolves to Path.cwd() at call time."""
    monkeypatch.chdir(tmp_path)
    _write_dotenv(tmp_path / ".env", "LCA_TEST=cwd-default\n")
    snapshot = load_layered_env("test-bin")
    assert snapshot.dotenv.get("LCA_TEST") == "cwd-default"
