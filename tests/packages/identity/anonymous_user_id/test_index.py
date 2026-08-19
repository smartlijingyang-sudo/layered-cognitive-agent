"""Tests for ``lca.packages.identity.anonymous_user_id.src.index``.

Exercises the anonymous user id public surface: file-based persistence,
memoization, UUID validation, and best-effort error handling.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lca.packages.identity.anonymous_user_id import index as sut

# ---------------------------------------------------------------------------
# UUID validation & constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_file_name_is_bare_dotfile(self) -> None:
        assert sut.ANONYMOUS_USER_ID_FILE_NAME == ".anonymous-user-id"

    def test_uuid_pattern_matches_canonical_v4(self) -> None:
        valid = "550e8400-e29b-41d4-a716-446655440000"
        assert re.match(sut._UUID_PATTERN.pattern, valid, re.IGNORECASE)

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "not-a-uuid",
            "550e8400-e29b-41d4-a716-44665544000",  # too short
            "550e8400-e29b-41d4-a716-4466554400000",  # too long
            "550e8400_e29b_41d4_a716_446655440000",  # wrong separators
            "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",  # non-hex
        ],
    )
    def test_uuid_pattern_rejects_invalid(self, value: str) -> None:
        assert sut._UUID_PATTERN.match(value) is None


# ---------------------------------------------------------------------------
# _resolve_dsh_home
# ---------------------------------------------------------------------------


class TestResolveDshHome:
    def test_uses_dsh_home_env(self) -> None:
        assert sut._resolve_dsh_home(None, {"DSH_HOME": "/tmp/test"}) == "/tmp/test"

    def test_falls_back_to_home_dot_dsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", "/home/testuser")
        result = sut._resolve_dsh_home(None, {})
        assert result.endswith(".dsh")

    def test_uses_custom_env_dict(self) -> None:
        result = sut._resolve_dsh_home(None, {"DSH_HOME": "/custom"})
        assert result == "/custom"


# ---------------------------------------------------------------------------
# _read_persisted_id
# ---------------------------------------------------------------------------


class TestReadPersistedId:
    def test_reads_valid_uuid(self, tmp_path: Path) -> None:
        file = tmp_path / ".anon"
        file.write_text("550e8400-e29b-41d4-a716-446655440000\n")
        assert sut._read_persisted_id(str(file)) == "550e8400-e29b-41d4-a716-446655440000"

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert sut._read_persisted_id(str(tmp_path / "missing")) is None

    def test_returns_none_when_file_corrupt(self, tmp_path: Path) -> None:
        file = tmp_path / ".anon"
        file.write_text("not-a-uuid\n")
        assert sut._read_persisted_id(str(file)) is None

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        file = tmp_path / ".anon"
        file.write_text("  550e8400-e29b-41d4-a716-446655440000  \n")
        assert sut._read_persisted_id(str(file)) == "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# getOrCreateAnonymousUserId
# ---------------------------------------------------------------------------


class TestGetOrCreateAnonymousUserId:
    @pytest.fixture(autouse=True)
    def _clear_memo(self) -> None:
        sut._reset_memo()
        yield
        sut._reset_memo()

    def test_creates_new_uuid_on_first_call(self, tmp_path: Path) -> None:
        options = sut.AnonymousUserIdOptions(env={"DSH_HOME": str(tmp_path)})
        result = sut.getOrCreateAnonymousUserId(options)
        # Should be a valid UUID
        assert sut._UUID_PATTERN.match(result)
        # File should exist
        file = tmp_path / sut.ANONYMOUS_USER_ID_FILE_NAME
        assert file.exists()
        assert file.read_text().strip() == result

    def test_returns_same_id_on_subsequent_call(self, tmp_path: Path) -> None:
        options = sut.AnonymousUserIdOptions(env={"DSH_HOME": str(tmp_path)})
        first = sut.getOrCreateAnonymousUserId(options)
        second = sut.getOrCreateAnonymousUserId(options)
        assert first == second

    def test_reads_existing_persisted_id(self, tmp_path: Path) -> None:
        existing_id = "550e8400-e29b-41d4-a716-446655440000"
        file = tmp_path / sut.ANONYMOUS_USER_ID_FILE_NAME
        file.write_text(f"{existing_id}\n")
        options = sut.AnonymousUserIdOptions(env={"DSH_HOME": str(tmp_path)})
        result = sut.getOrCreateAnonymousUserId(options)
        assert result == existing_id

    def test_overwrites_corrupt_file(self, tmp_path: Path) -> None:
        file = tmp_path / sut.ANONYMOUS_USER_ID_FILE_NAME
        file.write_text("not-a-uuid\n")
        counter = iter(lambda: "11111111-1111-1111-1111-111111111111", None)
        options = sut.AnonymousUserIdOptions(
            env={"DSH_HOME": str(tmp_path)},
            random_uuid=lambda: "11111111-1111-1111-1111-111111111111",
        )
        result = sut.getOrCreateAnonymousUserId(options)
        assert result == "11111111-1111-1111-1111-111111111111"
        assert file.read_text().strip() == result

    def test_handles_concurrent_creation_fileexists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a concurrent process creates the file first (EEXIST), we
        reread and adopt the winner's id."""
        file = tmp_path / sut.ANONYMOUS_USER_ID_FILE_NAME
        winner_id = "22222222-2222-2222-2222-222222222222"

        call_count = [0]
        original_mkdir = Path.mkdir

        def fake_mkdir(self: Path, *args: object, **kwargs: object) -> None:
            # First mkdir succeeds; second time we create the file to simulate
            # a concurrent winner.
            call_count[0] += 1
            if not file.exists():
                file.write_text(f"{winner_id}\n")
            original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)
        options = sut.AnonymousUserIdOptions(
            env={"DSH_HOME": str(tmp_path)},
            random_uuid=lambda: "33333333-3333-3333-3333-333333333333",
        )
        result = sut.getOrCreateAnonymousUserId(options)
        # Should have adopted the winner's id
        assert result == winner_id

    def test_handles_concurrent_with_corrupt_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a concurrent winner lands a corrupt file, we overwrite."""
        file = tmp_path / sut.ANONYMOUS_USER_ID_FILE_NAME

        original_open = open

        def fake_open(path: object, mode: str = "r", *args: object, **kwargs: object) -> object:
            if "x" in mode:
                file.write_text("corrupt-id\n")
                raise FileExistsError("simulated concurrent winner")
            return original_open(path, mode, *args, **kwargs)

        import builtins

        monkeypatch.setattr(builtins, "open", fake_open)
        options = sut.AnonymousUserIdOptions(
            env={"DSH_HOME": str(tmp_path)},
            random_uuid=lambda: "44444444-4444-4444-4444-444444444444",
        )
        result = sut.getOrCreateAnonymousUserId(options)
        # Should have overwritten the corrupt file
        assert result == "44444444-4444-4444-4444-444444444444"
        assert file.read_text().strip() == result

    def test_best_effort_on_readonly_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the home is unwritable, we still return a usable id."""
        readonly = tmp_path / "readonly"
        readonly.mkdir()

        def fail_write(*args: object, **kwargs: object) -> None:
            raise OSError("read-only filesystem")

        monkeypatch.setattr(Path, "write_text", fail_write)
        options = sut.AnonymousUserIdOptions(
            env={"DSH_HOME": str(readonly)},
            random_uuid=lambda: "55555555-5555-5555-5555-555555555555",
        )
        result = sut.getOrCreateAnonymousUserId(options)
        # Should still return a valid id (the fresh one we minted)
        assert result == "55555555-5555-5555-5555-555555555555"

    def test_custom_random_uuid(self, tmp_path: Path) -> None:
        custom_id = "66666666-6666-6666-6666-666666666666"
        options = sut.AnonymousUserIdOptions(
            env={"DSH_HOME": str(tmp_path)},
            random_uuid=lambda: custom_id,
        )
        result = sut.getOrCreateAnonymousUserId(options)
        assert result == custom_id

    def test_default_options(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DSH_HOME", str(tmp_path))
        sut._reset_memo()
        result = sut.getOrCreateAnonymousUserId()
        assert sut._UUID_PATTERN.match(result)


# ---------------------------------------------------------------------------
# _reset_memo
# ---------------------------------------------------------------------------


class TestResetMemo:
    def test_clears_memo(self, tmp_path: Path) -> None:
        options = sut.AnonymousUserIdOptions(env={"DSH_HOME": str(tmp_path)})
        sut.getOrCreateAnonymousUserId(options)
        assert len(sut._memo) > 0
        sut._reset_memo()
        assert len(sut._memo) == 0
