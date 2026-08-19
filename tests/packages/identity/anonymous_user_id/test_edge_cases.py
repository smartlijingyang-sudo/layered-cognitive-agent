"""测试并发创建和错误处理场景"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.packages.identity.anonymous_user_id import (
    AnonymousUserIdOptions,
    getOrCreateAnonymousUserId,
)
from lca.packages.identity.anonymous_user_id.index import _reset_memo


def test_concurrent_creation_with_corrupt_file():
    """测试并发创建时，winning 文件损坏的情况"""
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 模拟 FileExistsError 后，文件内容损坏
        original_write_text = Path.write_text

        def mock_write_text(self, content, encoding="utf-8"):
            if ".anonymous-user-id" in str(self):
                # 第一次写入成功（模拟并发 winner）
                original_write_text(self, "not-a-valid-uuid", encoding=encoding)
                raise FileExistsError()
            return original_write_text(self, content, encoding=encoding)

        with patch.object(Path, "write_text", side_effect=mock_write_text):
            # 应该能够处理损坏的文件并生成新的 UUID
            user_id = getOrCreateAnonymousUserId(options)
            assert user_id  # 应该返回一个有效的 UUID


def test_readonly_home_directory():
    """测试只读 home 目录的情况"""
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 模拟所有写入操作都失败
        def mock_mkdir(*args, **kwargs):
            raise OSError("Read-only file system")

        def mock_write(*args, **kwargs):
            raise OSError("Read-only file system")

        with patch.object(Path, "mkdir", side_effect=mock_mkdir):
            with patch.object(Path, "write_text", side_effect=mock_write):
                # 应该能够返回一个 UUID，即使无法持久化
                user_id = getOrCreateAnonymousUserId(options)
                assert user_id  # 应该返回一个有效的 UUID


def test_concurrent_creation_with_file_exists_error():
    """测试 FileExistsError 后成功读取 winner 的 UUID"""
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 先创建一个有效的文件
        file_path = Path(tmpdir) / ".anonymous-user-id"
        winner_uuid = "550e8400-e29b-41d4-a716-446655440000"
        file_path.write_text(winner_uuid)

        # 模拟 open 在 exclusive 模式下抛出 FileExistsError
        original_open = open

        def mock_open(file, mode="r", *args, **kwargs):
            if mode == "x":
                raise FileExistsError()
            return original_open(file, mode, *args, **kwargs)

        import builtins

        with patch.object(builtins, "open", side_effect=mock_open):
            # 应该能够读取 winner 的 UUID
            user_id = getOrCreateAnonymousUserId(options)
            assert user_id == winner_uuid


def test_file_already_exists_with_valid_uuid():
    """测试文件已存在且包含有效 UUID 的情况"""
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        # 先创建一个有效的文件
        file_path = Path(tmpdir) / ".anonymous-user-id"
        existing_uuid = "550e8400-e29b-41d4-a716-446655440000"
        file_path.write_text(existing_uuid)

        # 应该读取已存在的 UUID
        user_id = getOrCreateAnonymousUserId(options)
        assert user_id == existing_uuid


def test_concurrent_creation_winner_has_valid_uuid():
    """测试并发创建时，winner 有有效 UUID"""
    _reset_memo()

    with tempfile.TemporaryDirectory() as tmpdir:
        options = AnonymousUserIdOptions(env={"DSH_HOME": tmpdir})

        winner_uuid = "550e8400-e29b-41d4-a716-446655440000"

        # 模拟 FileExistsError 后，winner 已经写入了有效 UUID
        original_open = open
        call_count = [0]

        def mock_open(file, mode="r", *args, **kwargs):
            if mode == "x":
                call_count[0] += 1
                # 第一次调用 open('x') 时，模拟文件已存在
                if call_count[0] == 1:
                    # 写入 winner 的 UUID
                    Path(file).write_text(winner_uuid)
                    raise FileExistsError()
            return original_open(file, mode, *args, **kwargs)

        import builtins

        with patch.object(builtins, "open", side_effect=mock_open):
            user_id = getOrCreateAnonymousUserId(options)
            assert user_id == winner_uuid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
